from app.agents.signal_extraction_agent import (
    SignalExtractionAgent,
    SignalExtractionResult,
)


class InfoExtractionAgent(SignalExtractionAgent):
    async def extract_info(
        self, text: str, target_name: str | None = None
    ) -> SignalExtractionResult:
        return await self.extract_signals(
            title="",
            snippet=text,
            url="",
            target_name=target_name,
        )
