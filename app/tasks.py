import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.core_agent import AgenticProfileResearchAgent
from app.celery_app import celery_app
from app.db import SessionLocal
from app.logger import logger
from app.models import Evaluation, EvaluationStage, EvaluationStatus


@celery_app.task(
    bind=True,
    name="app.tasks.run_evaluation_pipeline",
    max_retries=3,
    default_retry_delay=60,
)
def run_evaluation_pipeline(
    self,
    evaluation_id: int,
    goal: str = "Perform professional research.",
    input_data: dict = None,
):
    """
    Background task to run the full evaluation pipeline.
    """
    db: Session = SessionLocal()
    try:
        evaluation = db.query(Evaluation).get(evaluation_id)
        if not evaluation:
            logger.error(f"Evaluation {evaluation_id} not found")
            return

        person = evaluation.person
        evaluation.status = EvaluationStatus.IN_PROGRESS
        evaluation.started_at = datetime.utcnow()
        db.commit()

        # Use AgenticProfileResearchAgent to perform the end-to-end research
        research_agent = AgenticProfileResearchAgent()

        input_d = input_data or {}
        context = {
            "name": person.full_name or "Unknown Candidate",
            "company": person.current_company,
            "designation": person.current_role,
            "linkedin_url": person.linkedin_url,
            **input_d,
        }

        # We need an event loop for the async agents
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            _update_stage(db, evaluation, EvaluationStage.IDENTITY_RESOLUTION)

            # Run the full agentic pipeline
            logger.info(
                f"Triggering AgenticProfileResearchAgent for evaluation {evaluation_id} with goal: {goal}"
            )
            result = loop.run_until_complete(
                research_agent.run_loop(goal=goal, context=context)
            )

            # Store results back to database
            evaluation.summary = result.get("summary", "")
            evaluation.sources = result.get(
                "memory", []
            )  # We attach the agent's memory/traces instead of strict sources for now
            evaluation.found_personas = []
            evaluation.follow_up_questions = []

            db.commit()
        except Exception as e:
            logger.error(
                f"ProfileResearchAgent failed for evaluation {evaluation_id}: {e}"
            )
            evaluation.status = EvaluationStatus.FAILED
            db.commit()
            raise e
        finally:
            loop.close()

        evaluation.status = EvaluationStatus.COMPLETED
        evaluation.completed_at = datetime.utcnow()
        db.commit()

    except Exception as exc:
        logger.exception(f"Error in evaluation pipeline for ID {evaluation_id}")
        evaluation.status = EvaluationStatus.FAILED
        db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()


def _update_stage(db: Session, evaluation: Evaluation, stage: EvaluationStage):
    logger.info(f"Transitioning evaluation {evaluation.id} to stage {stage.value}")
    evaluation.stage = stage
    db.commit()
