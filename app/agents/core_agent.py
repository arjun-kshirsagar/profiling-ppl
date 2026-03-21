import json
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.tools import TOOL_DESCRIPTIONS, TOOLS
from app.logger import logger
from app.models import EvaluationStage

StageCallback = Callable[[EvaluationStage], None]


class AgentStep(BaseModel):
    thought: str = Field(
        description="Reasoning about what to do next based on the goal and current state."
    )
    tool_name: str = Field(
        description="Name of the tool to use, or 'DONE' if the goal is achieved or impossible."
    )
    tool_inputs: dict = Field(
        default_factory=dict, description="Arguments for the chosen tool."
    )
    is_done: bool = Field(
        default=False, description="Set to true if the goal is achieved."
    )
    final_summary: str = Field(
        default="",
        description="The final comprehensive output/summary if is_done is true.",
    )


class AgenticProfileResearchAgent(BaseAgent):
    """
    Planner-driven orchestrator that uses the specialist pipeline stages as tools.
    The LLM controls the sequence, while state transitions remain deterministic.
    """

    STAGE_BY_TOOL = {
        "resolve_linkedin_seed": EvaluationStage.IDENTITY_RESOLUTION,
        "generate_queries": EvaluationStage.DATA_COLLECTION,
        "refine_queries": EvaluationStage.DATA_COLLECTION,
        "search_web": EvaluationStage.DATA_COLLECTION,
        "resolve_identity": EvaluationStage.IDENTITY_RESOLUTION,
        "disambiguate_personas": EvaluationStage.DECISION,
        "extract_signals_batch": EvaluationStage.SIGNAL_EXTRACTION,
        "score_sources_batch": EvaluationStage.SCORING,
        "generate_profile_summary": EvaluationStage.DECISION,
        "generate_follow_up_questions": EvaluationStage.DECISION,
    }

    def __init__(self, provider: str = "gemini"):
        super().__init__(provider=provider, max_retries=2, timeout_seconds=60)
        self.memory: List[Dict[str, Any]] = []
        self.state: Dict[str, Any] = {}

    async def run_loop(
        self,
        goal: str,
        context: dict,
        stage_callback: Optional[StageCallback] = None,
    ) -> Dict[str, Any]:
        logger.info("Starting agentic pipeline for goal: '%s'", goal)
        self.memory = [{"role": "system", "content": f"Initial context: {json.dumps(context)}"}]
        self.state = self._initialize_state(context)

        system_prompt = f"""
You are the orchestration brain for a profile intelligence engine.
Your goal is: {goal}

You must drive a real research workflow by choosing specialist tools stage by stage.
Do not jump straight to DONE unless the current state proves the task is impossible or complete.

Preferred workflow:
1. If a LinkedIn URL exists and the name is weak, resolve the LinkedIn seed.
2. Generate or refine search queries.
3. Execute search_web until you have enough results.
4. Run resolve_identity over the aggregated search results.
5. If multiple personas remain, run disambiguate_personas.
6. Run extract_signals_batch on the vetted sources.
7. Run score_sources_batch on the extracted sources.
8. If ambiguity remains unresolved, generate follow-up questions.
9. Generate the final profile summary from scored sources.

Rules:
- Be conservative with identity.
- Use the actual state, not assumptions.
- Prefer batching where the tool supports it.
- Only finish when summary, sources, and ambiguity handling are coherent.

Available Tools:
{json.dumps(TOOL_DESCRIPTIONS, indent=2)}
"""

        max_iterations = 14
        final_summary = ""

        for iteration in range(1, max_iterations + 1):
            logger.info("Agent Loop Iteration %d", iteration)
            user_prompt = (
                "Current state:\n"
                + json.dumps(self._state_snapshot(), indent=2)
                + "\n\nExecution memory:\n"
                + json.dumps(self.memory[-12:], indent=2)
                + "\n\nChoose the next tool call."
            )

            try:
                step_decision = await self.execute(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=AgentStep,
                )
            except Exception as exc:
                logger.exception("Agent loop planning error on iteration %d", iteration)
                self.memory.append(
                    {"role": "observation", "content": f"Planner exception: {exc}"}
                )
                break

            logger.info("Agent Thought: %s", step_decision.thought)

            if step_decision.is_done or step_decision.tool_name == "DONE":
                final_summary = step_decision.final_summary or self.state.get("summary", "")
                logger.info("Agent marked workflow complete.")
                break

            tool_name = step_decision.tool_name
            tool_inputs = step_decision.tool_inputs
            if tool_name not in TOOLS:
                err_msg = f"Error: Tool {tool_name} not found."
                logger.warning(err_msg)
                self.memory.append({"role": "observation", "content": err_msg})
                continue

            stage = self.STAGE_BY_TOOL.get(tool_name)
            if stage and stage_callback:
                stage_callback(stage)

            logger.info("Executing tool '%s' with args %s", tool_name, tool_inputs)
            observation = await self._execute_tool(tool_name, tool_inputs)
            self._apply_observation(tool_name, observation)

            self.memory.append(
                {
                    "role": "action",
                    "thought": step_decision.thought,
                    "action": tool_name,
                    "inputs": tool_inputs,
                }
            )
            self.memory.append({"role": "observation", "content": observation})

        if not self.state.get("summary") and self.state.get("final_sources"):
            self.state["summary"] = self._fallback_summary(self.state["final_sources"])

        if self.state.get("summary"):
            final_summary = self.state["summary"]
        elif not final_summary:
            final_summary = (
                "Agent loop terminated without a conclusive final summary after "
                "reaching max iterations or encountering an error."
            )

        return {
            "summary": final_summary,
            "sources": self.state.get("final_sources", []),
            "found_personas": self.state.get("found_personas", []),
            "follow_up_questions": self.state.get("follow_up_questions", []),
            "memory": self.memory,
            "state": self._state_snapshot(),
        }

    async def _execute_tool(self, tool_name: str, tool_inputs: Dict[str, Any]) -> Dict[str, Any]:
        tool_func = TOOLS[tool_name]
        try:
            result = await tool_func(**tool_inputs)
            return {"tool": tool_name, "inputs": tool_inputs, "result": result}
        except Exception as exc:
            logger.error("Tool execution failed for %s: %s", tool_name, exc)
            return {"tool": tool_name, "inputs": tool_inputs, "error": str(exc)}

    def _initialize_state(self, context: Dict[str, Any]) -> Dict[str, Any]:
        person_info = {
            "name": context.get("name") or "Unknown Candidate",
            "company": context.get("company"),
            "designation": context.get("designation"),
            "linkedin_url": context.get("linkedin_url"),
            "github_url": context.get("github_url"),
        }
        return {
            "person_info": person_info,
            "seed_result": None,
            "queries": [],
            "search_results": [],
            "valid_sources": [],
            "found_personas": [],
            "needs_disambiguation": False,
            "disambiguation_reason": None,
            "selected_persona_index": None,
            "extracted_sources": [],
            "final_sources": [],
            "follow_up_questions": [],
            "summary": "",
        }

    def _state_snapshot(self) -> Dict[str, Any]:
        return {
            "person_info": self.state.get("person_info", {}),
            "seed_result": self.state.get("seed_result"),
            "query_count": len(self.state.get("queries", [])),
            "queries": self.state.get("queries", []),
            "search_result_count": len(self.state.get("search_results", [])),
            "search_results_preview": self.state.get("search_results", [])[:8],
            "valid_source_count": len(self.state.get("valid_sources", [])),
            "valid_sources": self.state.get("valid_sources", []),
            "found_personas": self.state.get("found_personas", []),
            "needs_disambiguation": self.state.get("needs_disambiguation", False),
            "selected_persona_index": self.state.get("selected_persona_index"),
            "extracted_source_count": len(self.state.get("extracted_sources", [])),
            "final_source_count": len(self.state.get("final_sources", [])),
            "final_sources": self.state.get("final_sources", []),
            "follow_up_questions": self.state.get("follow_up_questions", []),
            "summary": self.state.get("summary", ""),
        }

    def _apply_observation(self, tool_name: str, observation: Dict[str, Any]) -> None:
        if "error" in observation:
            return

        result = observation.get("result") or {}
        if tool_name == "resolve_linkedin_seed":
            self.state["seed_result"] = result
            person_info = self.state["person_info"]
            if result.get("name") and (
                person_info.get("name") == "Unknown Candidate" or result.get("confidence", 0.0) >= 0.6
            ):
                person_info["name"] = result["name"]
            if result.get("possible_companies") and not person_info.get("company"):
                person_info["company"] = result["possible_companies"][0]
            if result.get("possible_roles") and not person_info.get("designation"):
                person_info["designation"] = result["possible_roles"][0]
            if result.get("linkedin_slug"):
                person_info["linkedin_slug"] = result["linkedin_slug"]
            return

        if tool_name in {"generate_queries", "refine_queries"}:
            self.state["queries"] = self._dedupe_queries(result.get("queries", []))
            return

        if tool_name == "search_web":
            merged = self.state.get("search_results", [])
            merged.extend(result.get("results", []))
            self.state["search_results"] = self._dedupe_results(merged)
            return

        if tool_name == "resolve_identity":
            self.state["valid_sources"] = result.get("valid_sources", [])
            self.state["found_personas"] = result.get("found_personas", [])
            self.state["needs_disambiguation"] = result.get("needs_disambiguation", False)
            self.state["disambiguation_reason"] = result.get("disambiguation_reason")
            return

        if tool_name == "disambiguate_personas":
            best_index = result.get("best_persona_index")
            if result.get("conclusive_match") and best_index is not None:
                self.state["selected_persona_index"] = best_index
                self.state["needs_disambiguation"] = False
                self.state["valid_sources"] = [
                    source
                    for source in self.state.get("valid_sources", [])
                    if source.get("persona_index") == best_index
                ]
            return

        if tool_name == "extract_signals_batch":
            self.state["extracted_sources"] = result.get("extracted_sources", [])
            return

        if tool_name == "score_sources_batch":
            scored = [
                source
                for source in result.get("final_sources", [])
                if source.get("confidence", 0.0) >= 0.35
            ]
            self.state["final_sources"] = scored
            return

        if tool_name == "generate_follow_up_questions":
            self.state["follow_up_questions"] = result.get("questions", [])
            return

        if tool_name == "generate_profile_summary":
            self.state["summary"] = result.get("summary", "")

    def _dedupe_queries(self, queries: List[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for query in queries:
            normalized = " ".join(query.split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
        return merged[:10]

    def _dedupe_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen_urls = set()
        for result in results:
            url = result.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            deduped.append(result)
        return deduped[:20]

    def _fallback_summary(self, final_sources: List[Dict[str, Any]]) -> str:
        top_sources = sorted(
            final_sources, key=lambda item: item.get("confidence", 0.0), reverse=True
        )[:3]
        if not top_sources:
            return "No sufficient data to generate summary."

        descriptions = []
        for source in top_sources:
            extracted = source.get("extracted_data", {})
            role = extracted.get("role")
            company = extracted.get("company")
            url = source.get("url", "")
            if role and company:
                descriptions.append(f"{role} at {company} ({url})")
            elif role:
                descriptions.append(f"{role} ({url})")
            else:
                descriptions.append(url)
        return "Likely profile signals found from: " + "; ".join(descriptions) + "."
