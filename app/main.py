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
    logger.info(f"POST /v1/evaluations - received request: {payload.input_type}")

    # 1. Create/Find Person record
    person = None
    if payload.input_type == "linkedin_url" and payload.input_value:
        person = (
            db.query(Person).filter(Person.linkedin_url == payload.input_value).first()
        )
    elif payload.input_type == "github_url" and payload.input_value:
        person = (
            db.query(Person).filter(Person.github_url == payload.input_value).first()
        )
    elif payload.input_type == "name_company" and payload.name:
        # Search by name and company
        query = db.query(Person).filter(Person.full_name == payload.name)
        if payload.company:
            query = query.filter(Person.current_company == payload.company)
        if payload.designation:
            query = query.filter(Person.current_role == payload.designation)
        person = query.first()

    if not person:
        person = Person(
            full_name=payload.name,
            current_company=payload.company,
            current_role=payload.designation,
            linkedin_url=(
                payload.input_value if payload.input_type == "linkedin_url" else None
            ),
            github_url=(
                payload.input_value if payload.input_type == "github_url" else None
            ),
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
    run_evaluation_pipeline.delay(evaluation.id)

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
    sources_data = evaluation.sources or []
    found_personas = evaluation.found_personas or []

    return ComprehensiveProfileResponse(
        person={
            "name": person.full_name or "Unknown",
            "company": person.current_company,
        },
        sources=sources_data,
        summary=evaluation.summary or "",
        total_sources=len(sources_data),
        found_personas=found_personas,
        follow_up_questions=evaluation.follow_up_questions or [],
    )
