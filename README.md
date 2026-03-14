# 🚀 Profile Intelligence Engine

A powerful, search-first agentic engine designed to discover, verify, and summarize professional profiles from the open web.

Built with **multi-agent orchestration**, this engine autonomously navigates search results to identify the correct professional identity and synthesizes information from diverse sources into a cohesive intelligence report—all without direct scraping.

---

## 🌟 Core Philosophy

Traditional profile extraction relies on brittle scrapers and direct platform integrations. **Profile Intelligence Engine** moves beyond this by treating the web as a knowledge graph.

It utilizes specialized agents to:
1.  **Refine intent**: If a search is ambiguous or yields no results, the agent iterates on the query.
2.  **Verify Identity**: Using OSINT patterns to separate "Amit Sharma (Infosys)" from "Amit Sharma (Blogger)".
3.  **Synthesize Snippets**: Extracting high-value signals from search metadata and snippets, avoiding the overhead and blocks of full-page scraping.

---

## 🛠️ Technology Stack

- **API Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous, High Performance)
- **Task Orchestration**: [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/)
- **Database**: [PostgreSQL](https://www.postgresql.org/) + [SQLAlchemy](https://www.sqlalchemy.org/)
- **Search Infrastructure**: [DuckDuckGo](https://duckduckgo.com/) (via `ddgs`) + [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview)
- **LLM Intelligence**: [Groq](https://groq.com/) (Llama 3), [OpenAI](https://openai.com/), [Gemini](https://deepmind.google/technologies/gemini/), & [Anthropic](https://www.anthropic.com/)

---

## 📂 Architecture

```mermaid
graph TD
    User([User]) -->|POST /v1/evaluations| API[FastAPI Server]
    API -->|Queue Task| Broker[Redis]
    Broker -->|Execute| Worker[Celery Worker]

    subgraph "Agentic Orchestrator (ProfileResearchAgent)"
        Worker --> QA[QueryAgent]
        QA -->|Generate Queries| SS[SearchService]
        SS -->|Fetch Snippets| IA[IdentityAgent]
        IA -->|Verify Matches| CL[ConfidenceService]
        CL -->|Iterate if Weak| QA
        IA -->|Synthesize| SA[SummaryAgent]
        SA -->|Final Report| Result
    end

    Result --> DB[(PostgreSQL)]
```

---

## 🤖 The Agent System

### 🔍 QueryAgent
Optimizes search queries based on the input person's name, company, and role. It handles **Iterative Refinement**: if the first batch of results is poor, it generates fallback boolean search strategies to find "hidden" profiles.

### 🛡️ IdentityAgent
The "Gatekeeper." It analyzes search resultsContext to determine if they actually belong to the target person. It assigns match confidence based on name overlap, professional context, and platform trust.

### 📝 SummaryAgent
The "Editor." It merges verified search snippets and metadata into a cohesive 3-5 sentence professional summary, highlighting current roles, past achievements, and online footprint.

### ⚖️ ConfidenceService
Uses weighted heuristics to calculate a final trust score for every source identified, ensuring only reliable information makes it into the summary.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL
- Redis

### Installation

1. **Install dependencies**:
   ```bash
   poetry install
   ```

2. **Configure Environment**:
   Create a `.env` file based on the available settings:
   ```env
   DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/profile_engine
   CELERY_BROKER_URL=redis://localhost:6379/0

   # LLM Keys
   GROQ_API_KEY=your_key
   OPENAI_API_KEY=your_key
   GEMINI_API_KEY=your_key

   # Optional: Google Search API
   GOOGLE_CSE_API_KEY=your_key
   GOOGLE_CSE_CX=your_cx
   ```

3. **Database Migrations**:
   ```bash
   poetry run alembic upgrade head
   ```

---

## 📡 API Reference

### Create Evaluation Job
`POST /v1/evaluations`
Accepts `linkedin_url` or `name_company` inputs to trigger a background agentic research task.

### Get Job Status
`GET /v1/evaluations/{id}`
Returns the current stage (**Identity Resolution**, **Synthesis**, etc.) and final status.

### Get Profile Intelligence
`GET /v1/profiles/{id}`
Returns the full synthesized report, including the professional summary and verified source URLs with confidence scores.

---

## 🧪 Development & Testing

We use a search-first test suite. To test the full orchestrator pipeline without a browser:

```bash
poetry run python test_orchestrator.py
```

---

## 📜 License
MIT
