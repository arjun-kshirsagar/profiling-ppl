

# 1️⃣ What Is He Actually Testing?

## 🧠 1. Problem Framing Ability

He wants to see:

* Can you define what “top 1%” means?
* Can you convert a vague idea into a structured system?
* Can you define measurable evaluation criteria?

Most people will jump into scraping code.

Top engineers will ask:

* What signals define quality?
* What sources are reliable?
* What is the scoring framework?
* How do we avoid noise?

This is a thinking test.

---

## 🏗 2. System Design Skills

He wants to see if you can design something like:

```
Input: LinkedIn URL / Name + Company
→ Data Collection Layer
→ Signal Extraction Layer
→ Scoring Engine
→ Decision Engine
→ Explainable Output
```

He’s testing:

* Can you architect a pipeline?
* Can you think in modules?
* Can you separate ingestion from evaluation?

This is backend maturity.

---

## 🔎 3. Data Intelligence

Scraping is trivial.

Understanding **what matters** is hard.

Example signals he may expect:

| Signal            | Why it matters     |
| ----------------- | ------------------ |
| GitHub activity   | Builder mindset    |
| Publications      | Thought leadership |
| Conference talks  | Authority          |
| Startup exits     | Execution proof    |
| Media mentions    | Credibility        |
| YC-backed company | Validation         |

He wants to see:

* Do you understand what “elite” looks like?
* Can you quantify reputation?

This is product + intelligence thinking.

---

## ⚙️ 4. Tradeoff Thinking

He may check if you understand:

* Scraping vs Google Search API
* Noise vs Precision
* False positives vs False negatives
* Manual moderation vs automated scoring

This is senior-level thinking.

---

## 🧩 5. Explainability

Very important.

If your system rejects someone, can you explain why?

Example:

> Score: 72/100
> Missing: Public speaking presence, no open-source contributions

If you don’t build explainability → it’s just a black box.

He will notice that.

---

# 2️⃣ Why This Assignment Is Clever

He’s testing if you think like:

* A scraper developer ❌
  or
* A founder engineer building a high-signal network ✅

Huge difference.

---

# 3️⃣ Given *Your* Background (Be Strategic Here)

Arjun, this is perfect for you.

You:

* Think about system design
* Care about distributed systems
* Like deep architecture
* Want to become a serious backend engineer

This assignment is basically:

> “Design a reputation intelligence engine.”

This is MUCH more interesting than scraping.

If you build this properly:

* It becomes a portfolio project
* It becomes a startup idea
* It aligns with your long-term thinking

---

# 4️⃣ What He Is Probably Scoring You On

If I had to rank:

1. Clarity of thinking
2. Structured architecture
3. Signal selection logic
4. Evaluation design
5. Clean code (secondary)
6. Scraping ability (least important)

---

# 5️⃣ The Core Question You Must Answer

Before writing a single line of code, you must define:

> What makes someone “Top 1%”?

Until you define this, you cannot build anything.

---




---

# 🔥 High-Level Architecture

```
Input (LinkedIn URL / Name + Company)
        ↓
1️⃣ Identity Resolution Layer
        ↓
2️⃣ Data Collection Layer
        ↓
3️⃣ Signal Extraction Layer
        ↓
4️⃣ Scoring Engine
        ↓
5️⃣ Decision Engine
        ↓
6️⃣ Explainability Engine
        ↓
Output: Admit / Reject + Breakdown
```

We will build this in controlled phases.

---

# 🧱 PHASE 0 — Define The Objective (DO THIS FIRST)

Before code, define:

### 🎯 What are we evaluating?

Example definition:

> “Top 1% = high-signal builders with strong execution, visibility, and credibility.”

Now convert that into measurable categories:

| Category                           | Weight |
| ---------------------------------- | ------ |
| Execution (companies built, roles) | 30%    |
| Public credibility (press, talks)  | 20%    |
| Technical depth (GitHub, papers)   | 25%    |
| Influence (followers, engagement)  | 15%    |
| Recognition (awards, YC, etc.)     | 10%    |

Don’t code until this is written.

This document alone separates average from serious engineers.

---

# 🧩 PHASE 1 — Identity Resolution Layer

### Goal:

Convert input → canonical person identity.

### Input options:

* LinkedIn URL
* Name + company
* Name + Twitter
* Email (optional future)

### Implementation (MVP approach):

For now:

* Accept LinkedIn URL
* Extract:

  * Name
  * Current role
  * Company
  * Headline

Store in DB:

```python
class Person(Base):
    id
    full_name
    linkedin_url
    current_company
    current_role
    raw_profile_json
```

Later:
Use Google Search API to resolve:

* GitHub
* Twitter
* Personal website
* Crunchbase
* News articles

But don’t overbuild yet.

---

# 🌐 PHASE 2 — Data Collection Layer

This should be modular.

Create separate collectors:

```
collectors/
    linkedin_collector.py
    github_collector.py
    twitter_collector.py
    web_search_collector.py
```

Each collector returns:

```python
{
  "source": "github",
  "raw_data": {...},
  "confidence": 0.92
}
```

Key rule:

👉 Collectors ONLY collect.
👉 They do NOT score.
👉 They do NOT evaluate.

Separation of concerns = maturity.

---

## Example Collector (GitHub)

Using Google Search API:

Search:

```
"Arjun MK" + "GitHub"
```

Extract:

* Repo count
* Stars
* Followers
* Contribution frequency

Store raw.

---

# 🧠 PHASE 3 — Signal Extraction Layer

Now we convert raw data → structured signals.

Example:

From GitHub raw:

```json
{
  "repo_count": 42,
  "total_stars": 380,
  "followers": 120
}
```

Extract signals:

```python
{
  "open_source_score": 78,
  "consistency_score": 64,
  "technical_depth_score": 82
}
```

Do NOT mix this with scoring engine.

Signal extraction = feature engineering.

---

# 📊 PHASE 4 — Scoring Engine

Now define a proper scoring system.

Example:

```python
class ScoringEngine:

    def compute_score(self, signals):
        score = (
            signals.execution * 0.3 +
            signals.technical_depth * 0.25 +
            signals.public_credibility * 0.2 +
            signals.influence * 0.15 +
            signals.recognition * 0.1
        )
        return score
```

Important:

Make this configurable.

Use a JSON config:

```json
{
  "execution": 0.3,
  "technical_depth": 0.25
}
```

This shows system maturity.

---

# ⚖️ PHASE 5 — Decision Engine

This is simple logic.

Example:

```python
if score >= 80:
    decision = "ADMIT"
elif score >= 65:
    decision = "MANUAL_REVIEW"
else:
    decision = "REJECT"
```

Make thresholds configurable.

---

# 🧾 PHASE 6 — Explainability Engine

This is where you impress him.

Return:

```json
{
  "final_score": 76,
  "decision": "MANUAL_REVIEW",
  "breakdown": {
    "execution": 82,
    "technical_depth": 90,
    "influence": 40,
    "recognition": 20
  },
  "strengths": [
    "Strong open-source footprint",
    "High technical leadership"
  ],
  "weaknesses": [
    "Low public speaking visibility",
    "Limited press mentions"
  ]
}
```

This turns your system from toy → product.

---

# 🏗 Suggested Tech Stack (For You)

Since you're building async systems already:

* FastAPI (API layer)
* PostgreSQL (store signals + results)
* Celery + Redis (background scraping)
* Google Search API (initial data collection)
* BeautifulSoup (light parsing if needed)

This fits your current skillset perfectly.

---

# 🧠 Important Engineering Signals He Will Notice

If you:

✔ Separate ingestion from evaluation
✔ Make scoring configurable
✔ Add explainability
✔ Design modular collectors
✔ Think about rate limiting & retries
✔ Add async background jobs

He’ll know you think beyond CRUD apps.

---

# 🚀 Step-by-Step Execution Plan (Practical)

### Week 1 — Core Pipeline

* Define scoring framework
* Build DB models
* Build dummy collectors (hardcoded data)
* Build scoring engine
* Build decision engine
* Return explainable output

No scraping yet.

---

### Week 2 — Real Data

* Integrate Google Search API
* Add GitHub extraction
* Add news presence scoring
* Add influence scoring

---

### Week 3 — Polishing

* Add async job queue
* Add caching
* Add rate limiting
* Add audit logs
* Add manual review override

---

# ⚠️ What NOT To Do

❌ Don’t build Selenium scrapers immediately
❌ Don’t over-optimize scraping
❌ Don’t build UI first
❌ Don’t hardcode scoring logic in random places

---

# 🎯 The Real Goal

He doesn’t want a scraper.

He wants to see if you can design:

> A structured, intelligent decision system.

That’s backend maturity.

---


---

# 🎯 First: What Type of System Is This?

This is an **asynchronous evaluation pipeline**.

Why?

Because:

* Data collection takes time
* External APIs are slow
* Scraping may fail
* You need retries

So we design:

* Request → create evaluation job
* Background workers process
* Client polls for result

Exactly how serious systems are built.

---

# 🏗 High-Level API Structure

```
/v1
  /evaluations
  /persons
  /signals
  /config
  /health
```

We’ll go one by one.

---

# 1️⃣ Create Evaluation Job

## POST /v1/evaluations

### Purpose

Start evaluation of a person.

### Request Body

```json
{
  "input_type": "linkedin_url",
  "input_value": "https://linkedin.com/in/johndoe",
  "priority": "normal"
}
```

Later you can support:

* name + company
* github_url
* email

### Response (Immediately)

```json
{
  "evaluation_id": "eval_12345",
  "status": "QUEUED",
  "estimated_time_seconds": 45
}
```

---

### What Happens Internally

1. Create `Person` (if not exists)
2. Create `Evaluation` record
3. Push background job to Celery
4. Return immediately

---

# 2️⃣ Get Evaluation Status

## GET /v1/evaluations/{evaluation_id}

### Response While Running

```json
{
  "evaluation_id": "eval_12345",
  "status": "IN_PROGRESS",
  "progress": {
    "identity_resolution": "COMPLETED",
    "data_collection": "IN_PROGRESS",
    "signal_extraction": "PENDING",
    "scoring": "PENDING"
  }
}
```

### Response When Done

```json
{
  "evaluation_id": "eval_12345",
  "status": "COMPLETED",
  "result": {
    "final_score": 78,
    "decision": "MANUAL_REVIEW",
    "breakdown": {
      "execution": 82,
      "technical_depth": 90,
      "influence": 40,
      "recognition": 20
    },
    "strengths": [
      "Strong open-source footprint"
    ],
    "weaknesses": [
      "Low media presence"
    ]
  }
}
```

This endpoint is critical.

---

# 3️⃣ Get Person Profile (Resolved Data)

## GET /v1/persons/{person_id}

Purpose:
View normalized data collected about a person.

### Response

```json
{
  "person_id": "person_123",
  "full_name": "John Doe",
  "linkedin_url": "...",
  "github_url": "...",
  "twitter_url": "...",
  "current_role": "Founder",
  "current_company": "Stealth AI",
  "collected_sources": [
    "linkedin",
    "github",
    "google_search"
  ]
}
```

This is useful for debugging.

---

# 4️⃣ Get Extracted Signals

## GET /v1/evaluations/{evaluation_id}/signals

Purpose:
Inspect feature engineering layer.

```json
{
  "execution_score": 82,
  "technical_depth_score": 90,
  "influence_score": 40,
  "recognition_score": 20,
  "raw_features": {
    "github_stars": 420,
    "media_mentions": 2,
    "conference_talks": 0
  }
}
```

This endpoint impresses serious engineers.

Why?

Because it shows transparency.

---

# 5️⃣ Get Scoring Configuration

## GET /v1/config/scoring

```json
{
  "weights": {
    "execution": 0.3,
    "technical_depth": 0.25,
    "public_credibility": 0.2,
    "influence": 0.15,
    "recognition": 0.1
  },
  "thresholds": {
    "admit": 80,
    "manual_review": 65
  }
}
```

---

# 6️⃣ Update Scoring Config (Admin)

## PUT /v1/config/scoring

```json
{
  "weights": {
    "execution": 0.4,
    "technical_depth": 0.2
  }
}
```

Make this admin-protected.

This shows configurability.

---

# 7️⃣ Re-run Evaluation

## POST /v1/evaluations/{evaluation_id}/rerun

Useful when:

* Data sources changed
* Scoring logic updated
* Manual override required

---

# 8️⃣ Manual Override (Very Mature Feature)

## POST /v1/evaluations/{evaluation_id}/override

```json
{
  "decision": "ADMIT",
  "reason": "Investor referral"
}
```

This shows real-world thinking.

---

# 9️⃣ List Evaluations (Admin Dashboard)

## GET /v1/evaluations?status=COMPLETED&min_score=70

Response:

```json
{
  "total": 128,
  "results": [
    {
      "evaluation_id": "eval_1",
      "name": "John Doe",
      "score": 85,
      "decision": "ADMIT"
    }
  ]
}
```

---

# 🔟 Health Check

## GET /v1/health

```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "worker": "active"
}
```

Shows production awareness.

---

# 🧠 Now Let’s Define States Properly

Evaluation Status Enum:

```
QUEUED
IN_PROGRESS
FAILED
COMPLETED
CANCELLED
MANUAL_REVIEW
```

Progress Stages:

```
IDENTITY_RESOLUTION
DATA_COLLECTION
SIGNAL_EXTRACTION
SCORING
DECISION
```

Store stage-wise timestamps.

---

# 🗄 Suggested Database Tables

### persons

* id
* full_name
* linkedin_url
* github_url
* twitter_url
* metadata_json

### evaluations

* id
* person_id
* status
* final_score
* decision
* started_at
* completed_at

### signals

* id
* evaluation_id
* execution_score
* technical_depth_score
* influence_score
* recognition_score
* raw_features_json

### scoring_config

* version
* weights_json
* thresholds_json

---

# 🔥 What Will Impress Him

If your API:

✔ Is async
✔ Has clear separation of concerns
✔ Has explainability endpoints
✔ Has configuration endpoints
✔ Has manual override
✔ Has proper state management

He will immediately see you think at a systems level.

---


