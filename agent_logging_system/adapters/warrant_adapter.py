"""Warrant adapter: monitor a book-grounded coding agent.

Warrant reasons from source material, generates code, and verifies citations.
Each of those is a distinct action shape worth tracking on its own terms — a
citation that fails to verify is a different signal than code that fails to
parse. This adapter exposes one logging method per action so the resulting
observation stream is legible at the domain level, not just as generic calls.
"""
from typing import Any

from .base_adapter import BaseAdapter
from agent_logging_system.observation import LATENCY_GENERATION


class WarrantAdapter(BaseAdapter):
    """Domain-specific logging surface for Warrant agents."""

    def wrap_agent(self, warrant_agent: Any) -> Any:
        """Return the agent unchanged for now; full wrapping hooks land at integration time.

        The wrapper would intercept Warrant's reason/generate/verify calls and
        route each through the log_* methods below. Kept a pass-through so the
        adapter is usable immediately via explicit log_* calls.
        """
        return warrant_agent

    def log_reasoning_step(
        self, agent_id: str, source: str, question: str,
        answer: str, confidence: float, latency_ms: float,
    ) -> None:
        """A reasoning step grounded in a source document.

        Generation latency: the duration reflects how much answer was produced,
        not a machine bottleneck, so it never feeds the latency alarm.
        """
        self.emit_observation(
            agent_id=agent_id,
            action="reason_about_source",
            input_data={"source": source, "question": question},
            output_data={"answer": answer, "confidence": confidence},
            latency_ms=latency_ms,
            confidence=confidence,
            latency_kind=LATENCY_GENERATION,
        )

    def log_code_generation(
        self, agent_id: str, prompt: str, code: str,
        syntax_valid: bool, latency_ms: float,
    ) -> None:
        """A code-generation step; invalid syntax is logged as a failure.

        Generation latency: longer output is expected, not pathological.
        """
        self.emit_observation(
            agent_id=agent_id,
            action="generate_code",
            input_data={"prompt": prompt},
            output_data={"code": code, "syntax_valid": syntax_valid},
            latency_ms=latency_ms,
            status="success" if syntax_valid else "failed",
            confidence=1.0 if syntax_valid else 0.5,
            latency_kind=LATENCY_GENERATION,
        )

    def log_citation_check(
        self, agent_id: str, citation: str, source: str,
        valid: bool, latency_ms: float,
    ) -> None:
        """A citation-verification step; an unverifiable citation is a failure."""
        self.emit_observation(
            agent_id=agent_id,
            action="verify_citation",
            input_data={"citation": citation, "source": source},
            output_data={"valid": valid},
            latency_ms=latency_ms,
            status="success" if valid else "failed",
            confidence=1.0,
        )
