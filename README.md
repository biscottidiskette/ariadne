# Ariadne

**LLM-assisted Incident Response platform for security analysts.**

Ariadne is a full-stack IR decision engine that ingests forensic artifacts, extracts indicators of compromise, builds an auto-populated attack timeline, and gives analysts an AI chat partner that understands the case context — all within a structured engagement workflow.

---

## Features

- **Engagement management** — create, track, and close IR engagements with full CRUD lifecycle
- **Artifact ingestion & parsing** — supports EVTX logs, Chainsaw JSON detections, EDR exports, SIEM results, and raw paste/IoC lists; auto-detected from filename
- **Automatic IoC extraction** — IPs, domains, hashes, and file paths extracted from every ingested artifact
- **Attack timeline** — structured event timeline built automatically from parsed artifacts; manually extensible
- **AI-powered case chat** — LLM chat interface with full case context injected into every prompt; streaming responses via Groq
- **AI suggestions** — anti-circular suggestion engine surfaces next investigative actions the analyst hasn't already taken
- **Playbook generation** — LLM generates a prioritised investigative playbook per engagement on demand
- **Analyst notes** — freeform markdown notes scoped per engagement

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS v4, TanStack Query, React Router v7 |
| Backend | Python 3.10+, FastAPI, SQLite |
| AI | Groq API (Llama 3.3 70B / Llama 3.1 8B) |
| Parsers | python-evtx, lxml, custom JSON/CSV parsers |

---

## Project Structure

```
ariadne/
├── backend/
│   ├── ai/                  # LLM controller and Groq client
│   ├── db/                  # SQLite connection, schema, and service layer
│   ├── models/              # Pydantic schemas
│   ├── parsers/             # Artifact parsers (EVTX, Chainsaw, EDR, SIEM, IoC)
│   ├── routes/              # FastAPI route modules
│   ├── main.py              # App entry point
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── api/             # Axios client
    │   ├── pages/           # EngagementList, EngagementWorkspace
    │   └── components/      # UI, chat, engagement, sidebar components
    ├── index.html
    └── package.json
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 20+
- A [Groq API key](https://console.groq.com)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env        # then add your GROQ_API_KEY
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`. Visit `/docs` for the interactive Swagger UI.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:5173`.

---

## Environment Variables

Copy `.env.example` to `backend/.env` and fill in the values:

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key |
| `DATABASE_URL` | SQLite database path (default: `./ariadne.db`) |
| `ENVIRONMENT` | `development` or `production` |

---

## License

MIT