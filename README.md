# MedVibe 🏥⚡

MedVibe is a high-speed, AI-powered **Omnichannel Emergency Room Triage Terminal** designed for chaotic healthcare environments. Built with a strict lightweight architecture (FastAPI + HTML/JS/Tailwind) and an aggressive "Neo-Brutalist" aesthetic, it prioritizes speed, readability, and resilience over pretty gradients.

## 🚀 Key Features

*   **🧠 AI-Powered Triage (Gemini 1.5-Flash):** Nurses type or speak a patient's complaint, and the AI instantly categorizes urgency (High/Medium/Low) and generates a concise clinical summary.
*   **📡 Bulletproof Offline Resilience:** If the hospital network drops, MedVibe doesn't freeze. It caches patient intakes locally in the browser and automatically bulk-syncs them via a SQLite Write-Ahead Logging (WAL) queue the second the network returns.
*   **🚨 Live Kanban Board & Strobe Alerts:** A real-time sorting mat for patients. Critical cases that wait too long trigger physical "strobe and judder" screen animations to demand attention.
*   **📊 Dual-Mode Metrics Engine:** A toggle flips the UI from the intake terminal into an administrative dashboard, featuring Neo-Brutalist charts that track hospital load by department in real time.
*   **🔐 JWT Security:** The core terminal is locked behind a strict Operator Auth Wall, ensuring patient data remains secure.
*   **🖨️ Hardware PDF Reports:** One-click hardcopy report generation using `html2canvas` and `jsPDF` to print out high-contrast triage blueprints.

## 🤖 The Omnichannel AI Experience

MedVibe features three distinct touchpoints powered by a unified AI backend:
1.  **The Secure Nurse Terminal:** Nurses can use the inline `[AI REFINE]` chat widget to generate medical follow-up questions to tighten vague complaints.
2.  **The Self-Triage Kiosk:** A massive, full-screen public kiosk where patients talk directly to the AI, which auto-generates their token and pushes it to the secure queue.
3.  **The Mobile Patient Portal:** A QR-code-accessed mobile dashboard where patients can view their live wait time and chat with an empathetic support bot while they wait.

## 🏗️ Tech Stack

*   **Backend:** Python 3.11, FastAPI, Uvicorn, SQLite (WAL Mode)
*   **Frontend:** Vanilla JS, HTML5, TailwindCSS (CDN), Chart.js
*   **AI Engine:** Google Generative AI (`gemini-1.5-flash`)
*   **Security:** JSON Web Tokens (JWT), Passlib (Bcrypt)
*   **Infrastructure:** Docker, Docker Compose

## 🛠️ Quick Start (Docker)

The fastest way to deploy MedVibe is via Docker.

1.  **Clone the repo:**
    ```bash
    git clone https://github.com/ShreyasVavley/Medvibe.git
    cd Medvibe
    ```

2.  **Set your API Key:**
    Create a `.env` file in the root directory:
    ```env
    GEMINI_API_KEY=your_google_gemini_api_key_here
    JWT_SECRET=your_secure_secret_key
    ```

3.  **Spin up the container:**
    ```bash
    docker-compose up -d --build
    ```

4.  **Access the interfaces:**
    *   Secure Terminal: `http://localhost:8000` *(Login: admin / admin123)*
    *   Public Kiosk: `http://localhost:8000/kiosk`
    *   Patient Portal: `http://localhost:8000/portal/<TOKEN_ID>`

## 💻 Local Development (Without Docker)

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Run the Uvicorn server:
    ```bash
    uvicorn main:app --reload
    ```

## 🎨 Design Philosophy
The UI follows a **Neo-Brutalist** methodology. 
No rounded corners. No drop shadows. No smooth easing curves. 
We use thick 3px black borders, pure primary colors (Cobalt Blue, Danger Red, Warning Yellow), and monospace fonts. In a high-stress emergency room, "pretty and smooth" UI causes cognitive fatigue. MedVibe's interface acts like physical, industrial machinery—it is impossible to misread or misclick.

---
*Built for the future of rapid healthcare intake.*
