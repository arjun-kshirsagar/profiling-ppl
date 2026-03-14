import enum

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class EvaluationStatus(enum.Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class EvaluationStage(enum.Enum):
    IDENTITY_RESOLUTION = "IDENTITY_RESOLUTION"
    DATA_COLLECTION = "DATA_COLLECTION"
    SIGNAL_EXTRACTION = "SIGNAL_EXTRACTION"
    SCORING = "SCORING"
    DECISION = "DECISION"


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(200), nullable=True)
    linkedin_url = Column(String(500), nullable=True, unique=True)
    github_url = Column(String(500), nullable=True)
    twitter_url = Column(String(500), nullable=True)
    current_company = Column(String(200), nullable=True)
    current_role = Column(String(200), nullable=True)
    metadata_json = Column(JSON, nullable=True, default=dict)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evaluations = relationship("Evaluation", back_populates="person")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    status = Column(
        SQLEnum(EvaluationStatus), nullable=False, default=EvaluationStatus.QUEUED
    )
    stage = Column(SQLEnum(EvaluationStage), nullable=True)
    final_score = Column(Float, nullable=True)
    decision = Column(String(50), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Explainability fields
    summary = Column(Text, nullable=True)
    strengths = Column(JSON, nullable=True)
    weaknesses = Column(JSON, nullable=True)
    sources = Column(JSON, nullable=True, default=list)
    found_personas = Column(JSON, nullable=True, default=list)
    follow_up_questions = Column(JSON, nullable=True, default=list)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    person = relationship("Person", back_populates="evaluations")
