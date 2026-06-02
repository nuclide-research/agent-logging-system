"""Base adapter: the seam between a host agent system and the monitor.

Subclass this to wire a specific framework (Warrant, an orchestrator, a custom
loop) into the LoggingAgent. The base handles timestamping and observation
construction so subclasses only describe *what their agent did* in domain terms.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agent_logging_system.logging_agent import LoggingAgent
from agent_logging_system.observation import Observation, LATENCY_MACHINE


def _utc_now_iso() -> str:
    """ISO8601 UTC timestamp with a trailing Z, matching Observation's contract."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class BaseAdapter(ABC):
    """Common plumbing for emitting observations into a LoggingAgent."""

    def __init__(self, logging_agent: LoggingAgent):
        self.logging_agent = logging_agent

    def emit_observation(
        self,
        agent_id: str,
        action: str,
        input_data: Any,
        output_data: Any,
        latency_ms: float,
        status: str = "success",
        confidence: float = 1.0,
        error_details: Optional[Dict[str, str]] = None,
        latency_kind: str = LATENCY_MACHINE,
    ) -> None:
        """Construct an Observation (stamped now) and feed it to the monitor."""
        obs = Observation(
            timestamp=_utc_now_iso(),
            agent_id=agent_id,
            action=action,
            input=input_data,
            output=output_data,
            latency_ms=latency_ms,
            status=status,
            confidence=confidence,
            error_details=error_details,
            latency_kind=latency_kind,
        )
        self.logging_agent.ingest(obs)

    def get_state(self) -> Dict[str, Any]:
        """Full system snapshot from the underlying monitor."""
        return self.logging_agent.get_system_state()

    @abstractmethod
    def wrap_agent(self, agent: Any) -> Any:
        """Wrap a host agent so its actions are observed. Implemented per framework."""
        raise NotImplementedError
