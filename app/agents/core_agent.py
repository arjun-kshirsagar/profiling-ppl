import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.tools import TOOL_DESCRIPTIONS, TOOLS
from app.logger import logger


class AgentStep(BaseModel):
    thought: str = Field(
        description="Reasoning about what to do next based on the goal and memory."
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
    Autonomous LLM agent loop that dynamically decides tools to use
    to achieve a high-level goal.
    """

    def __init__(self, provider: str = "gemini"):
        super().__init__(provider=provider, max_retries=2, timeout_seconds=60)
        self.memory: List[Dict[str, Any]] = []

    async def run_loop(self, goal: str, context: dict) -> Dict[str, Any]:
        """
        Runs the Plan -> Execute -> Observe loop until `is_done` or max iterations.
        """
        logger.info(f"Starting Agentic loop for goal: '{goal}'")
        self.memory.append(
            {"role": "system", "content": f"Context: {json.dumps(context)}"}
        )

        system_prompt = f"""
You are an autonomous AI Agent performing a task.
Your high-level goal is: {goal}

Available Tools:
{json.dumps(TOOL_DESCRIPTIONS, indent=2)}

You operate in a loop: plan -> execute tool -> observe -> repeat.
Review the memory of previous steps to decide your next action.
If you have enough information to fulfill the goal, set is_done=true and provide the final_summary.
Include references to URLs in the summary.
If you need more information, output the tool_name and tool_inputs to execute.
Ensure tool_name is exactly the name provided in Available Tools or 'DONE'.
"""

        max_iterations = 8
        iteration = 0
        final_summary = ""

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent Loop Iteration {iteration}")

            user_prompt = (
                "Memory of events so far:\n"
                + json.dumps(self.memory, indent=2)
                + "\n\nWhat is your next step?"
            )

            try:
                # 1. Plan / Decide Next Step
                step_decision = await self.execute(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=AgentStep,
                )

                logger.info(f"Agent Thought: {step_decision.thought}")

                if step_decision.is_done or step_decision.tool_name == "DONE":
                    final_summary = step_decision.final_summary
                    logger.info("Agent has completed the goal.")
                    break

                tool_name = step_decision.tool_name
                tool_inputs = step_decision.tool_inputs

                if tool_name not in TOOLS:
                    err_msg = f"Error: Tool {tool_name} not found."
                    logger.warning(err_msg)
                    self.memory.append({"role": "observation", "content": err_msg})
                    continue

                # 2. Execute Tool
                logger.info(f"Executing tool '{tool_name}' with args {tool_inputs}")
                tool_func = TOOLS[tool_name]
                try:
                    result = await tool_func(**tool_inputs)
                    observation = {
                        "tool": tool_name,
                        "inputs": tool_inputs,
                        "result": result,
                    }
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    observation = {
                        "tool": tool_name,
                        "inputs": tool_inputs,
                        "error": str(e),
                    }

                # 3. Update Memory
                self.memory.append(
                    {
                        "role": "action",
                        "thought": step_decision.thought,
                        "action": tool_name,
                    }
                )
                self.memory.append({"role": "observation", "content": observation})

            except Exception as e:
                logger.exception(f"Agent loop error on iteration {iteration}")
                self.memory.append(
                    {"role": "observation", "content": f"Agent Exception: {str(e)}"}
                )
                break

        if not final_summary:
            final_summary = (
                "Agent loop terminated without a conclusive final summary "
                "after reaching max iterations or encountering an error."
            )

        return {"summary": final_summary, "memory": self.memory}
