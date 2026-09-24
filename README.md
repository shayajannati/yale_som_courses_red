<p align="center">
  <img src="docs/handsome-dan.svg" alt="A row of seven rainbow-colored Handsome Dan bulldogs in Yale-blue bandanas" width="720">
</p>

<h1 align="center">Yale SOM Course Explorer</h1>

<p align="center">
  Browse every Yale School of Management course as a card, or ask the AI course assistant a question in plain English.
</p>

---

## What it does

- **Course catalog.** All 234 Yale SOM courses show up as glass-style cards with the course number, title, instructor, meeting time, room, session, units and description. Each card has its own Handsome Dan bulldog, and every course gets a different rainbow coat color.
- **Search and filter.** Type in the search box to filter by title, number, professor or day. You can also click a category chip such as Core, Finance or Marketing.
- **Course assistant chat.** Click **Ask the course assistant** in the bottom-right corner. The assistant is an AI agent with two tools:
  - `search_courses` does semantic search over the course database. The LLM reads the whole catalog and ranks courses by meaning, so a question like "courses about persuading customers" finds *Mastering Influence & Persuasion* even though the words don't match.
  - `web_search` is OpenAI's built-in web search. The agent uses it for anything the course data doesn't cover, such as faculty news, rankings or research.

  Under each reply you'll see which tools the agent used.
- **Audit trail.** The app appends every agent run to `output/audit_trail.json`. Each entry records the time, the question, the model's reasoning summary, each tool call with its arguments and a short result, and why the run stopped.

## Tech stack

| Part | Tools |
|---|---|
| Frontend | React 19, Vite, TypeScript, `react-markdown` |
| Backend | FastAPI, uvicorn |
| Agent | PydanticAI (`pydantic-ai-slim[openai]`) on the OpenAI Responses API |
| Model | `gpt-5.6-luna` through the [Portkey](https://portkey.ai) gateway |
| Data | `data/yale_som_classes.json` (catalog) and `data/yale_som.db` (SQLite, used by the agent) |

## Project layout

```
.
├── .env.example            # copy to .env and add your key
├── data/
│   ├── yale_som_classes.json
│   └── yale_som.db         # SQLite course table used by the agent
├── backend/
│   ├── main.py             # FastAPI app: /api/health, /api/courses, /api/chat
│   ├── agent.py            # PydanticAI agent, web search, audit trail
│   ├── tools.py            # search_courses (LLM semantic search over yale_som.db)
│   ├── models.py           # Pydantic models (CourseSearchResult, AgentResult, ...)
│   ├── prompts/prompt.md   # agent system prompt
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── index.css       # glassmorphism styles
│   │   └── components/
│   │       ├── CourseCard.tsx
│   │       ├── ChatPanel.tsx
│   │       └── HandsomeDan.tsx
│   └── render-dan.mjs      # regenerates docs/handsome-dan.svg
├── docs/handsome-dan.svg
└── output/audit_trail.json
```

## Setup

You need **Python 3.12+**, **Node.js 20+** and a **Portkey API key**.

**1. API key.** Copy `.env.example` to `.env` and fill in your key:

```
PORTKEY_API_KEY=your-portkey-api-key-here
```

The backend reads `.env` from the project folder or from the folder one level up. Never commit your real `.env`. It's already in `.gitignore`.

**2. Course database.** `data/yale_som.db` is included in the repo, so there's nothing to download. The catalog cards load from `data/yale_som_classes.json`, and the agent's `search_courses` tool reads the `courses` table in the database.

**3. Backend dependencies.** Run these in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**4. Frontend dependencies:**

```powershell
cd frontend
npm install
```

## Running the app

Open **two terminals**.

**Terminal 1, backend.** Start this one first:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --port 8000
```

**Terminal 2, frontend:**

```powershell
cd frontend
npm run dev
```

Then open **http://127.0.0.1:5173**. The API docs are at **http://127.0.0.1:8000/docs**.

> If the page says "Could not load courses", the backend isn't running yet. Start it and refresh.

## API

| Method | Route | What it does |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/courses?q=...` | All courses, with an optional text filter |
| `POST` | `/api/chat` | `{"message": "..."}` returns `{"reply": "...", "tools_used": [...]}` |

## Notes

- **Cost.** `search_courses` makes its own LLM call on every search, and web questions can take several search rounds. The agent allows up to 20 model requests per question. To use a different model, change `MODEL_NAME` in `backend/agent.py` and `backend/tools.py`.
- **Handsome Dan image.** The mascot is an original SVG React component with `furColor`, `bandanaColor` and `size` props. If you edit the component, regenerate the image at the top of this README:

  ```powershell
  cd frontend
  node render-dan.mjs
  ```
