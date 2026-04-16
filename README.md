# 🤖 AI Interview Scheduler

An AI-powered interview scheduling agent built with **FastAPI + SQLite + Google Gemini API**.

The AI acts as a friendly recruiter named **Alex** who chats with candidates, collects their availability, and books interview slots — all via natural text conversation.

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure your API key
Copy `.env.example` to `.env` and add your Gemini API key:
```bash
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY
```
Get your free key at: https://aistudio.google.com/app/apikey

### 3. Run the server
```bash
uvicorn app.main:app --reload
```

### 4. Open the app
- **Chat UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

---

## 📁 Project Structure
```
app/
├── main.py              # FastAPI entry point
├── database.py          # SQLite setup
├── schemas.py           # Pydantic models
├── routers/
│   ├── candidates.py    # Add/list candidates
│   ├── sessions.py      # Session management
│   └── chat.py          # AI conversation + slots
├── services/
│   ├── ai_service.py    # Gemini integration
│   └── scheduler.py     # Datetime utilities
└── static/
    └── index.html       # Chat frontend
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/candidates/` | Add a candidate |
| GET | `/candidates/` | List all candidates |
| POST | `/sessions/start` | Start scheduling session |
| GET | `/chat/{id}/greet` | Trigger AI greeting |
| POST | `/chat/{id}` | Send message to AI |
| GET | `/slots` | View all booked interviews |
| PUT | `/slots/{id}/cancel` | Cancel a slot |

---

## ☁️ Deploy to Render

1. Push code to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Set:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variable: `GEMINI_API_KEY`
5. Deploy ✅

---

## 💬 Sample Flow
1. Add a candidate (name, email, role)
2. Click their name → AI sends greeting
3. Candidate replies with availability
4. AI confirms a time → slot is saved in DB 🎉
