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
        Worker --> PSRA[ProfileSeedResolver]
        PSRA --> QA[QueryAgent]
        QA -->|Search| SS[SearchService]
        SS -->|Results| IA[IdentityAgent]
        IA -->|Ambiguous?| ADA[ActiveDisambiguation]
        ADA -->|Conclusive Match| SEA[SignalExtractionAgent]
        IA -->|Valid Sources| SEA
        SEA -->|Signals| CS[ConfidenceService]
        CS -->|Scores| SA[SummaryAgent]
        CS -->|Unresolved?| FUA[FollowUpAgent]
        SA -->|Final Report| Result
    end

    Result --> DB[(PostgreSQL)]
```

---

## 🤖 The Agent System

### 🧬 ProfileSeedResolverAgent
The **"Inceptor."** If a LinkedIn URL is provided, it resolves the initial profile to extract "seed" details like the correct name, company, and role, which helps anchor the rest of the search.

### 🔍 QueryAgent
The **"Strategist."** It generates and refines platform-specific search queries (e.g., using `site:github.com` or `site:linkedin.com`) to find the target's online presence. It handles **Iterative Refinement** on search failures.

### 🛡️ IdentityAgent
The **"Gatekeeper."** It categorizes search results into distinct personas and assigns `identity_match_score` based on how well each result aligns with the target's known name, company, and role.

### ⚖️ ActiveDisambiguationAgent
The **"Tie-breaker."** When multiple plausible personas are found (e.g., two "John Does" at the same company), it performs deeper reasoning on available data to find the conclusive match.

### ⛏️ SignalExtractionAgent
The **"Miner."** It extracts granular professional signals like current role, seniority, core skills, and past companies directly from search snippets without heavy scraping.

### 📈 ConfidenceService
The **"Validator."** It computes a final trust score for every source by weighting identity match, source type, and data extraction quality.

### 📝 SummaryAgent
The **"Editor."** It synthesizes all verified signals and high-confidence sources into a cohesive 3-5 sentence professional summary, highlighting major achievements and online footprint.

### 🤝 FollowUpAgent
The **"Concierge."** If the system cannot confidently resolve an identity due to ambiguity, it generates clarifying questions to help the user provide missing context.


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
