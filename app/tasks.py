import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.profile_research_agent import ProfileResearchAgent
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
def run_evaluation_pipeline(self, evaluation_id: int):
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

        # Use ProfileResearchAgent to perform the end-to-end research
        research_agent = ProfileResearchAgent()

        # Determine inputs
        name = person.full_name or "Unknown Candidate"
        company = person.current_company
        designation = person.current_role

        # We need an event loop for the async agents
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            _update_stage(db, evaluation, EvaluationStage.IDENTITY_RESOLUTION)

            # Run the full agentic pipeline
            logger.info(
                f"Triggering ProfileResearchAgent for evaluation {evaluation_id}"
            )
            result = loop.run_until_complete(
                research_agent.research_profile(
                    name=name,
                    company=company,
                    designation=designation,
                    linkedin_url=person.linkedin_url,
                    max_search_results=10,
                )
            )

            # Store results back to database
            evaluation.summary = result.summary
            # We can store the structured sources in the evaluation or person metadata
            # For now, let's assume we store them in a JSON field if available,
            # but looking at models.py earlier, we might need to add it or use an existing one.
            # Evaluation has summary, strengths, weaknesses.

            # Update person info if found
            if not person.full_name and result.person.name:
                person.full_name = result.person.name

            # Store discovered URLs back to the person if not already present
            if result.sources:
                for source in result.sources:
                    if not person.linkedin_url and source.type == "linkedin_profile":
                        person.linkedin_url = source.url
                    if not person.github_url and source.type == "github_profile":
                        person.github_url = source.url

            # The result.sources contains FinalSourceData objects.
            # We might need to store them in a related table or JSON.
            # Assuming Evaluation has a 'sources' JSONB column or similar as implied by main.py line 273.
            evaluation.sources = [s.model_dump() for s in result.sources]
            evaluation.found_personas = [p.model_dump() for p in result.found_personas]
            evaluation.follow_up_questions = result.follow_up_questions

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
