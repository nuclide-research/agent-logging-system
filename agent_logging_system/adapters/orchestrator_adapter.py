"""Orchestrator adapter: monitor an O->S->H subagent fan-out.

Models the canonical orchestration pattern: an orchestrator (Opus/Sonnet)
delegates scoped work to subagent lanes (Sonnet retrieval, Haiku execution),
then integrates the results in a final synthesis turn.

The modelling decisions that make this useful:

  - Agents are LANES, not subagent instances. A single subagent is dispatched
    once and would never reach the latency warmup, so its latency could never be
    judged. Grouping dispatches by lane (retrieval.sonnet, execution.haiku) lets
    the lane accumulate a baseline across many dispatches, so a dispatch that is
    a sharp deviation from the lane's normal actually trips.

  - Dispatches are MACHINE latency. A subagent call is execution time: a lane
    suddenly running slow is a real, alarmable problem.

  - Synthesis is GENERATION latency. The orchestrator integrating a long answer
    is expected to take a while; it must never trip the latency alarm.

Per-lane error_rate and queue_buildup come for free from the default rules: a
failing lane raises error_rate_high, and a lane carrying heavy volume raises
queue_buildup ("consider more parallelism") which is exactly the orchestration
signal you want.
"""
from typing import Any, Iterable, Optional, Sequence, Tuple

from .base_adapter import BaseAdapter
from agent_logging_system.observation import LATENCY_GENERATION


class OrchestratorAdapter(BaseAdapter):
    """Domain-specific logging surface for an orchestrator + subagent fleet."""

    # Default lane names matching the canonical O->S->H tiers. Override freely;
    # any string is a valid lane.
    RETRIEVAL = "retrieval.sonnet"
    EXECUTION = "execution.haiku"
    ORCHESTRATOR = "orchestrator"

    def wrap_agent(self, orchestrator: Any) -> Any:
        """Pass-through for now; explicit log_* calls work today.

        A full wrap would intercept the orchestrator's dispatch and synthesis
        calls and route them through the methods below.
        """
        return orchestrator

    def log_subagent_dispatch(
        self,
        lane: str,
        task: str,
        latency_ms: float,
        status: str = "success",
        tier: Optional[str] = None,
        tokens: Optional[int] = None,
    ) -> None:
        """One subagent execution, attributed to its lane (machine latency)."""
        output: dict = {"ok": status == "success"}
        if tokens is not None:
            output["tokens"] = tokens
        self.emit_observation(
            agent_id=lane,
            action="subagent_dispatch",
            input_data={"task": task, "tier": tier or lane},
            output_data=output,
            latency_ms=latency_ms,
            status=status,
            # machine kind (default): a slow dispatch is a real signal
        )

    def log_fanout(
        self,
        lane: str,
        dispatches: Iterable[Sequence],
    ) -> None:
        """Log a batch of parallel dispatches to one lane.

        Each item is (task, latency_ms) or (task, latency_ms, status). This is
        the parallel-coverage case: N subagents fanned out across one lane.
        """
        for d in dispatches:
            task, latency = d[0], d[1]
            status = d[2] if len(d) > 2 else "success"
            self.log_subagent_dispatch(lane, task, latency, status=status)

    def log_synthesis(
        self,
        latency_ms: float,
        status: str = "success",
        agent_id: Optional[str] = None,
    ) -> None:
        """The orchestrator's integration turn (generation latency, never alarms)."""
        self.emit_observation(
            agent_id=agent_id or self.ORCHESTRATOR,
            action="synthesize",
            input_data={"role": "integration"},
            output_data={"ok": status == "success"},
            latency_ms=latency_ms,
            status=status,
            latency_kind=LATENCY_GENERATION,
        )
