# ⚽ FootballAI — AI-Powered Tactical Assistant

An AI-driven football coaching platform that combines real player statistics with large language models (LLMs) to produce professional-grade tactical match analyses, training plans, and animated 2D tactical simulations.

---

## 🏗️ Architecture Overview

```
┌─────────────┐     REST / JSON      ┌──────────────┐
│  Next.js 14  │◄────────────────────►│  FastAPI      │
│  (Frontend)  │     port 3000        │  (Backend)    │
└─────────────┘                       └──────┬───────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
             ┌──────▼──────┐         ┌───────▼───────┐       ┌───────▼───────┐
             │  PostgreSQL  │         │     Redis      │       │   ChromaDB    │
             │  (Data)      │         │  (Task Queue)  │       │   (RAG)       │
             └─────────────┘         └───────┬───────┘       └──────────────┘
                                             │
                                     ┌───────▼───────┐
                                     │  LLM Workers   │
                                     │  (Gemini API)  │
                                     └───────────────┘
```

## 🚀 Features

- **Real Data Integration** — Fetches live player stats, team data, and league info from API-Football
- **AI Head Coach** — Holistic match analysis covering defense, midfield, attack, set pieces, and player roles
- **6 Specialist AI Coaches** — Defense coordinator, midfield coordinator, attack coordinator, set piece specialist, positioning analyst, match preparation expert
- **Tactical RAG System** — 3-level hierarchical retrieval from tactical knowledge documents (PDF/TXT/MD)
- **2D Tactical Simulations** — Animated frame-by-frame player movements on a virtual pitch
- **Match Chat** — Follow-up questions in the same session without re-analyzing
- **Dashboard** — Full CRUD for leagues, teams, players, and statistics
- **Match Analysis History** — Browse past analyses with full detail

---

## 📦 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | Python 3.11+, FastAPI, Uvicorn |
| **Database** | PostgreSQL 15+, SQLAlchemy 2.0 |
| **Task Queue** | Redis 5+ (async, via Docker) |
| **LLM** | Google Gemini 2.5 Flash (via LangChain) |
| **RAG / Vector DB** | ChromaDB, Gemini Embeddings |
| **Frontend** | Next.js 14, TypeScript, TailwindCSS |
| **UI Components** | Radix UI, Lucide React, GSAP, Sonner |
| **State Management** | TanStack Query (React Query) |
| **External API** | API-Football (api-sports.io) |

---

## 🔧 Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `DB_USER` | PostgreSQL username | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | `your_password` |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5433` |
| `DB_NAME` | Database name | `APIFOOTBALL` |
| `POOL_SIZE` | SQLAlchemy connection pool size | `4` |
| `MAX_OVERFLOW` | Max overflow connections | `20` |
| `FOOTBALL_API_KEY` | API-Football API key | `your_key_here` |
| `APIENDPOINT` | API-Football base URL | `https://v3.football.api-sports.io/` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSy...` |
| `GEMINI_EMBEDDING_MODEL` | Embedding model name | `models/gemini-embedding-001` |
| `RAG_DOCUMENTS_PATH` | Path to tactical documents folder | `/path/to/backend/rag_docs/` |
| `CHROMA_PERSIST_DIR` | ChromaDB storage path | `./chroma_db` |
| `RAG_CHUNK_SIZE` | Chunk size for text splitting (chars) | `800` |
| `RAG_CHUNK_OVERLAP` | Overlap between chunks (chars) | `120` |
| `RAG_TOP_K` | Number of chunks to retrieve | `6` |
| `RAG_EMBED_BATCH_SIZE` | Embedding batch size (rate-limit friendly) | `4` |
| `RAG_EMBED_DELAY_SEC` | Delay between embedding batches (seconds) | `3` |
| `RAG_EMBED_MAX_RETRIES` | Max retries on 429 errors | `12` |
| `RAG_EMBED_RETRY_BASE_SEC` | Base wait for exponential backoff | `10` |
| `RAG_EMBED_RETRY_MAX_SEC` | Max wait for exponential backoff | `180` |
| `DISABLE_EMBEDDED_LLM_WORKERS` | Set to `1` to disable embedded workers | `3` (worker count) |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `http://localhost:3000` |

### Frontend (`frontend/.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL (no trailing slash) | `http://127.0.0.1:8000` |

---

## 🛠️ Installation & Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ & npm
- PostgreSQL 15+
- Docker (for Redis)
- [Gemini API key](https://aistudio.google.com/app/apikey) (free tier works)
- [API-Football key](https://www.api-football.com/)

### 1. Start Redis

```bash
docker run -d --name redis-football -p 6379:6379 redis:latest

# Verify:
docker exec -it redis-football redis-cli ping
# → PONG
```

### 2. Set Up PostgreSQL

```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create the database
CREATE DATABASE "APIFOOTBALL";
\q
```

### 3. Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Configure environment (edit values as needed)
cp .env.example .env  # or create manually — see table above

# Initialize database tables
python main.py
# → "DB initialized!"

# (Optional) Index tactical documents for RAG
python rag_ingest.py
python rag_ingest.py --stats  # verify

# Start the server
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 4. Frontend Setup

```bash
cd frontend

npm install

# Configure environment
echo 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8000' > .env

npm run dev
```

### 5. Populate Data

Use the Swagger UI at `http://localhost:8000/docs` or curl:

```bash
# Fetch leagues
curl "http://localhost:8000/leagues/fetch_and_upsert?season=2024"

# Fetch teams for a league (e.g., Turkish Super Lig = 203)
curl "http://localhost:8000/teams/fetch_and_upsert?league_id=203&season=2024"

# Fetch players and stats
curl "http://localhost:8000/players/fetch_and_upsert?team_id=645&season=2024"
curl "http://localhost:8000/playerstats/fetch_and_upsert?team_id=645&season=2024&league_id=203"
curl "http://localhost:8000/teamstats/fetch_and_upsert?team_id=645&season=2024&league_id=203"
```

---

## 📡 API Endpoints

### Data Ingestion
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/leagues/fetch_and_upsert` | Fetch & save leagues |
| GET | `/teams/fetch_and_upsert` | Fetch & save teams |
| GET | `/players/fetch_and_upsert` | Fetch & save players |
| GET | `/playerstats/fetch_and_upsert` | Fetch & save player stats |
| GET | `/teamstats/fetch_and_upsert` | Fetch & save team stats |

### AI Coaching
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/coach/head-coach` | Full holistic match analysis |
| POST | `/coach/defense` | Defense-only analysis |
| POST | `/coach/offense` | Offense-only analysis |
| POST | `/coach/set-piece` | Set piece planning |
| POST | `/coach/positioning` | Player positioning & roles |
| POST | `/coach/preparation` | Match day preparation |
| POST | `/coach/training` | Training drill suggestions |
| POST | `/coach/match-chat` | Follow-up chat in session |
| POST | `/coach/generate-simulations/{id}` | Generate all simulation types |
| POST | `/coach/generate-custom-simulations/{id}` | Generate specific sim type |

### RAG (Knowledge Base)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/rag/stats` | ChromaDB collection stats |
| POST | `/rag/query` | Tactical Q&A from knowledge base |
| POST | `/rag/ingest` | Index new documents |

### Dashboard CRUD
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/PATCH/DELETE | `/rest/leagues` | League management |
| GET/PATCH/DELETE | `/rest/teams` | Team management |
| GET/PATCH/DELETE | `/rest/players` | Player management |
| PATCH | `/rest/players/{id}/statistics` | Update player stats |
| GET/DELETE | `/rest/match-analyses` | Analysis history |
| GET/DELETE | `/rest/simulations` | Simulation management |

---

## 📂 Project Structure

```
apifootball/
├── backend/
│   ├── app.py                 # FastAPI application & all endpoints
│   ├── main.py                # Database initializer
│   ├── database.py            # SQLAlchemy engine & session
│   ├── model.py               # ORM models (8 tables)
│   ├── api_client.py          # External API client + DB data reader
│   ├── llm_client.py          # LLM factory (Gemini via LangChain)
│   ├── llm_models.py          # AI coaching staff (7 specialists + head coach)
│   ├── redis_orchestrator.py  # Redis task queue publisher
│   ├── coach_session.py       # Chat session manager (Redis)
│   ├── rag_ingest.py          # Hierarchical RAG indexing system
│   ├── requirements.txt       # Python dependencies
│   ├── .env                   # Environment configuration
│   ├── rag_docs/              # Tactical documents (PDF/TXT/MD)
│   └── chroma_db/             # ChromaDB persistent storage
│
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js pages
│   │   │   ├── page.tsx              # Dashboard
│   │   │   ├── match-analysis/       # Match analysis page
│   │   │   └── simulation/           # Simulation viewer
│   │   ├── components/
│   │   │   ├── tactical/             # Simulation engine
│   │   │   ├── shell/                # Layout components
│   │   │   └── ui/                   # UI primitives
│   │   └── lib/                      # API client, utilities
│   ├── package.json
│   └── .env
│
├── README.md
└── MEDIUM_ARTICLE.txt
```

---

## 📝 License

This project is for educational and portfolio purposes.

