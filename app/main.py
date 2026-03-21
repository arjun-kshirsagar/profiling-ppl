from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.logger import logger
from app.models import Evaluation, EvaluationStatus, Person
from app.schemas import (
    ComprehensiveProfileResponse,
    EvaluationStatusEnum,
    EvaluationStatusResponse,
    JobInput,
    JobResponse,
)
from app.tasks import run_evaluation_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wait for database to be ready and seed default config if needed."""
    yield


app = FastAPI(title="Profile Intelligence Engine", version="0.3.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@app.post("/v1/evaluations", response_model=JobResponse)
async def create_evaluation_job(
    payload: JobInput, db: Session = Depends(get_db)
) -> JobResponse:
    # 1. Create/Find Person record
    person = None
    input_data = payload.input_data or {}
    linkedin_url = input_data.get("linkedin_url")
    github_url = input_data.get("github_url")
    name = input_data.get("name")
    company = input_data.get("company")
    designation = input_data.get("designation")

    # Construct the goal dynamically in the backend
    goal = "Perform comprehensive professional research based on provided context."
    if linkedin_url:
        goal = f"Identify and summarize the professional background for the LinkedIn profile: {linkedin_url}."
    elif name and company:
        goal = f"Research the professional experience and achievements of {name} at {company}."
    elif name:
        goal = f"Discover and synthesize a professional profile for {name}."

    logger.info(f"POST /v1/evaluations - Generated Goal: {goal}")

    if linkedin_url:
        person = db.query(Person).filter(Person.linkedin_url == linkedin_url).first()
    elif github_url:
        person = db.query(Person).filter(Person.github_url == github_url).first()
    elif name:
        query = db.query(Person).filter(Person.full_name == name)
        if company:
            query = query.filter(Person.current_company == company)
        if designation:
            query = query.filter(Person.current_role == designation)
        person = query.first()

    if not person:
        person = Person(
            full_name=name,
            current_company=company,
            current_role=designation,
            linkedin_url=linkedin_url,
            github_url=github_url,
        )
        db.add(person)
        db.flush()  # To get the ID for evaluation

    # 2. Create Evaluation record
    evaluation = Evaluation(
        person_id=person.id,
        status=EvaluationStatus.QUEUED,
        stage=None,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    # 3. Push background job
    run_evaluation_pipeline.delay(evaluation.id, goal, input_data)

    return JobResponse(
        evaluation_id=evaluation.id,
        status=EvaluationStatusEnum(evaluation.status.value),
    )


@app.get("/v1/evaluations/{evaluation_id}", response_model=EvaluationStatusResponse)
async def get_evaluation_status(evaluation_id: int, db: Session = Depends(get_db)):
    evaluation = db.query(Evaluation).get(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Calculate stage progress mapping
    stages = [
        "IDENTITY_RESOLUTION",
        "DATA_COLLECTION",
        "SIGNAL_EXTRACTION",
        "SCORING",
        "DECISION",
    ]
    current_stage_value = evaluation.stage.value if evaluation.stage else None
    progress = {}

    found_current = False
    for s in stages:
        if evaluation.status == EvaluationStatus.COMPLETED:
            progress[s] = "COMPLETED"
        elif evaluation.status == EvaluationStatus.FAILED:
            progress[s] = "FAILED"
        elif current_stage_value == s:
            progress[s] = "IN_PROGRESS"
            found_current = True
        elif not found_current:
            progress[s] = "COMPLETED"
        else:
            progress[s] = "PENDING"

    return EvaluationStatusResponse(
        evaluation_id=evaluation.id,
        status=evaluation.status.value,
        stage=current_stage_value,
        summary=evaluation.summary,
        progress=progress,
    )


@app.get("/v1/profiles/{evaluation_id}", response_model=ComprehensiveProfileResponse)
async def get_comprehensive_profile(evaluation_id: int, db: Session = Depends(get_db)):
    evaluation = db.query(Evaluation).get(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    person = evaluation.person
    sources_raw = evaluation.sources or []
    found_personas = evaluation.found_personas or []

    # Check if 'sources' contains agent memory traces (identifiable by 'role' field)
    sources = []
    agent_memory = []
    if sources_raw and isinstance(sources_raw[0], dict) and "role" in sources_raw[0]:
        agent_memory = sources_raw
    else:
        sources = sources_raw

    return ComprehensiveProfileResponse(
        person={
            "name": person.full_name or "Unknown",
            "company": person.current_company,
        },
        sources=sources,
        agent_memory=agent_memory,
        summary=evaluation.summary or "",
        total_sources=len(sources),
        found_personas=found_personas,
        follow_up_questions=evaluation.follow_up_questions or [],
    )
