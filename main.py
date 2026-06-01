import os
import json
import sqlite3
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import google.generativeai as genai
from dotenv import load_dotenv
import jwt
from passlib.context import CryptContext

load_dotenv()

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key and api_key != "your_actual_api_key_here":
    genai.configure(api_key=api_key)

app = FastAPI()
DB_FILE = "medvibe.db"

# JWT Config
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-medvibe-007")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    # Patients table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            token TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            complaint TEXT NOT NULL,
            department TEXT NOT NULL,
            urgency TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    
    # Inject default admin if not exists
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("admin", get_password_hash("admin123"), "Triage Nurse"))
        
    conn.commit()
    conn.close()

init_db()

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role not in ["Triage Nurse", "Attending Physician"]:
            raise HTTPException(status_code=401, detail="Unauthorized role access")
        return {"username": username, "role": role}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, role FROM users WHERE username = ?", (form_data.username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not verify_password(form_data.password, row[0]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username, "role": row[1]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    mode: str
    history: List[ChatMessage]

class PatientIn(BaseModel):
    name: str
    age: int
    complaint: str
    department: str
    token: Optional[str] = None

class PatientOut(BaseModel):
    token: str
    name: str
    age: int
    complaint: str
    department: str
    urgency: str
    summary: str
    wait_time_seconds: int = 0
    created_at: str
    status: str = 'ACTIVE'

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.get("/kiosk")
async def read_kiosk():
    return FileResponse('kiosk.html')

@app.get("/portal/{token}")
async def read_portal(token: str):
    return FileResponse('patient.html')

@app.get("/ping")
async def ping():
    return {"status": "ok"}

@app.get("/patients/{token}")
async def get_patient_by_token(token: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        p = dict(row)
        try:
            created_time = datetime.strptime(p["created_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            created_time = datetime.fromisoformat(p["created_at"])
        p["wait_time_seconds"] = int((datetime.now() - created_time).total_seconds())
        return p
    raise HTTPException(status_code=404, detail="Patient not found")

@app.post("/chat")
async def chat_with_gemini(req: ChatRequest):
    if req.mode == "kiosk":
        sys_inst = "You are the MedVibe Kiosk, a brutalist intake AI. Ask short, direct questions to determine the patient's name, age, department (General, Emergency, Cardiology, Orthopedics), and primary complaint. Once you have enough info, say '[READY]' and summarize the symptoms."
    elif req.mode == "refine":
        sys_inst = "You are the MedVibe Nurse Assistant. The nurse is refining a patient's symptoms. Ask 1 or 2 sharp follow-up questions to gather critical medical details, then say '[DONE]'."
    elif req.mode == "support":
        sys_inst = "You are the MedVibe Patient Support Bot. The patient is currently waiting. Be empathetic but very concise. Answer basic medical questions or provide reassurance."
    else:
        sys_inst = "You are a medical assistant."

    try:
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=sys_inst)
        
        formatted_history = []
        for msg in req.history[:-1]:
            r = "model" if msg.role == "assistant" else "user"
            formatted_history.append({"role": r, "parts": [msg.content]})
            
        chat = model.start_chat(history=formatted_history)
        last_msg = req.history[-1].content
        
        response = chat.send_message(last_msg)
        return {"response": response.text}
    except Exception as e:
        return {"response": "SYSTEM ERROR: " + str(e)}

@app.get("/analytics/department-loads")
async def get_department_loads(current_user: dict = Depends(get_current_user)):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT department, COUNT(*), 
                   SUM(CASE WHEN urgency = 'High' THEN 1 ELSE 0 END) as high_risk
            FROM patients 
            WHERE status = 'ACTIVE' 
            GROUP BY department
        """)
        stats = cursor.fetchall()
        return [
            {"department": r[0], "total": r[1], "critical": r[2]} 
            for r in stats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/analytics/wait-times")
async def get_wait_times(current_user: dict = Depends(get_current_user)):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT department,
                   AVG(strftime('%s', 'now') - strftime('%s', created_at)) as avg_wait_sec
            FROM patients
            WHERE status = 'ACTIVE'
            GROUP BY department
        """)
        stats = cursor.fetchall()
        return [
            {"department": r[0], "avg_wait_minutes": round(r[1] / 60, 1) if r[1] else 0} 
            for r in stats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/patients", response_model=List[PatientOut])
async def get_patients(current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE status = 'ACTIVE' ORDER BY created_at ASC")
    rows = cursor.fetchall()
    conn.close()
    
    patients = []
    now = datetime.now()
    for r in rows:
        p = dict(r)
        try:
            created_time = datetime.strptime(p["created_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            created_time = datetime.fromisoformat(p["created_at"])
            
        p["wait_time_seconds"] = int((now - created_time).total_seconds())
        patients.append(p)
    return patients

@app.post("/patients", response_model=PatientOut)
async def add_patient(patient: PatientIn, current_user: dict = Depends(get_current_user)):
    if patient.token:
        token_id = patient.token
    else:
        prefix = patient.department[:3].upper() if patient.department else "GEN"
        token_id = f"{prefix}-{os.urandom(2).hex().upper()}"
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM patients WHERE token = ?", (token_id,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        p = dict(existing)
        p["wait_time_seconds"] = 0
        return p

    prompt = f"""
    You are the MedVibe Neo-Brutalist Triage Engine. Analyze this patient complaint:
    "{patient.complaint}"
    
    Respond STRICTLY with a valid JSON object matching this schema:
    {{
        "urgency": "High" | "Medium" | "Low",
        "summary": "A short, brutalist-style clinical note in uppercase. Max 10 words."
    }}
    """
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        ai_data = json.loads(response.text)
    except Exception as e:
        ai_data = {
            "urgency": "Medium", 
            "summary": "AI TRIAGE FAILED. MANUAL REVIEW REQUIRED."
        }
    
    try:
        cursor.execute("""
            INSERT INTO patients (token, name, age, complaint, department, urgency, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (token_id, patient.name, patient.age, patient.complaint, patient.department, ai_data.get("urgency", "Medium"), ai_data.get("summary", "NO SUMMARY GENERATED."), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        
        cursor.execute("SELECT * FROM patients WHERE token = ?", (token_id,))
        new_row = cursor.fetchone()
        p = dict(new_row)
        p["wait_time_seconds"] = 0
        return p
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/kiosk-triage", response_model=PatientOut)
async def kiosk_add_patient(patient: PatientIn):
    prefix = patient.department[:3].upper() if patient.department else "GEN"
    token_id = f"{prefix}-{os.urandom(2).hex().upper()}"
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO patients (token, name, age, complaint, department, urgency, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (token_id, patient.name, patient.age, patient.complaint, patient.department, "Medium", "KIOSK AI INTAKE", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        
        cursor.execute("SELECT * FROM patients WHERE token = ?", (token_id,))
        new_row = cursor.fetchone()
        p = dict(new_row)
        p["wait_time_seconds"] = 0
        return p
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.put("/patients/{token}/escalate")
async def escalate_patient(token: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE token = ?", (token,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Patient not found")
        
    cursor.execute("UPDATE patients SET created_at = '1970-01-01 00:00:00' WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return {"status": "success", "token": token}

@app.delete("/patients")
async def clear_patients(current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE patients SET status = 'CLEARED' WHERE status = 'ACTIVE'")
    conn.commit()
    conn.close()
    return {"status": "success", "message": "All processed entries cleared"}
