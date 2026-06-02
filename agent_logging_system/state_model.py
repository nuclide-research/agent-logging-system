"""Real-time state of every tracked agent.

The OT analogue: the historian's rolling buffer plus the operator's running
mental model. We keep a bounded window of recent observations per agent so we
can reason about *trend* (is latency climbing?) not just lifetime average.
A lifetime average hides a recent spike the same way an hourly aggregate on
AVEVA PI hides a 30-second pressure excursion — so we expose both a full-window
mean and a short recent-window mean.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .observation import Observation, LATENCY_GENERATION

# How many recent observations define "right now" for the trip-rule average.
RECENT_WINDOW = 3


@dataclass
class AgentState:
    """Mutable state accumulated for a single agent."""

    agent_id: str
    status: str = "idle"                        # idle | in_progress | blocked | failed
    elapsed_time_sec: float = 0.0
    recent_latency: List[float] = field(default_factory=list)        # all kinds, for display
    recent_machine_latency: List[float] = field(default_factory=list)  # machine-kind only, feeds the alarm
    recent_status: List[str] = field(default_factory=list)
    error_count: int = 0
    success_count: int = 0
    total_observations: int = 0
    machine_count: int = 0                       # observations whose latency is machine-kind
    generation_count: int = 0                    # observations whose latency is generation-kind
    blocked_since: Optional[float] = None
    current_task: Optional[str] = None

    @property
    def avg_latency(self) -> float:
        """Mean latency across the full retained window."""
        if not self.recent_latency:
            return 0.0
        return sum(self.recent_latency) / len(self.recent_latency)

    @property
    def recent_avg_latency(self) -> float:
        """Mean latency across only the last RECENT_WINDOW observations.

        This is the value trip-rules should watch: it reacts to a fresh spike
        instead of being dragged down by a long tail of healthy history.
        """
        window = self.recent_latency[-RECENT_WINDOW:]
        if not window:
            return 0.0
        return sum(window) / len(window)

    @property
    def baseline_latency(self) -> float:
        """Mean latency of the *older* history, excluding the recent window.

        This is the agent's established normal: what it ran at before whatever
        is happening right now. A trip-rule compares recent_avg_latency against
        this baseline so "anomaly" means *deviation from this agent's own normal*,
        not crossing some absolute line. Returns 0.0 until there is older history
        to form a baseline from (the warmup case).
        """
        older = self.recent_latency[:-RECENT_WINDOW]
        if not older:
            return 0.0
        return sum(older) / len(older)

    @property
    def machine_recent_avg_latency(self) -> float:
        """recent_avg_latency restricted to machine-kind observations.

        This, not the all-kinds figure, is what the latency alarm watches: a
        generation-kind duration can never contribute here, so it can never trip
        the alarm regardless of magnitude.
        """
        window = self.recent_machine_latency[-RECENT_WINDOW:]
        if not window:
            return 0.0
        return sum(window) / len(window)

    @property
    def machine_baseline_latency(self) -> float:
        """baseline_latency restricted to machine-kind observations."""
        older = self.recent_machine_latency[:-RECENT_WINDOW]
        if not older:
            return 0.0
        return sum(older) / len(older)

    @property
    def error_rate(self) -> float:
        if self.total_observations == 0:
            return 0.0
        return self.error_count / self.total_observations


class StateModel:
    """Maintains the running state of all tracked agents."""

    def __init__(self, max_history: int = 20):
        self.agents: Dict[str, AgentState] = {}
        self.max_history = max_history          # retained observations per agent

    def ingest_observation(self, obs: Observation) -> None:
        """Fold one observation into the agent's running state."""
        agent = self.agents.setdefault(obs.agent_id, AgentState(agent_id=obs.agent_id))

        agent.total_observations += 1
        agent.status = "in_progress"

        agent.recent_latency.append(obs.latency_ms)
        if len(agent.recent_latency) > self.max_history:
            agent.recent_latency.pop(0)

        # Bucket latency by kind. Anything not explicitly "generation" counts as
        # machine: a monitor should default an unclassified duration to
        # alarmable, never silently drop a real spike on a typo.
        if obs.latency_kind == LATENCY_GENERATION:
            agent.generation_count += 1
        else:
            agent.machine_count += 1
            agent.recent_machine_latency.append(obs.latency_ms)
            if len(agent.recent_machine_latency) > self.max_history:
                agent.recent_machine_latency.pop(0)

        agent.recent_status.append(obs.status)
        if len(agent.recent_status) > self.max_history:
            agent.recent_status.pop(0)

        if obs.status == "failed":
            agent.error_count += 1
        elif obs.status == "success":
            agent.success_count += 1

    def get_agent_state(self, agent_id: str) -> Dict[str, Any]:
        """Snapshot one agent's state as a plain dict (rule-engine friendly)."""
        if agent_id not in self.agents:
            return {"agent_id": agent_id, "status": "unknown"}

        agent = self.agents[agent_id]
        return {
            "agent_id": agent.agent_id,
            "status": agent.status,
            "elapsed_time_sec": agent.elapsed_time_sec,
            "recent_latency": list(agent.recent_latency),
            "avg_latency": agent.avg_latency,
            "recent_avg_latency": agent.recent_avg_latency,
            "baseline_latency": agent.baseline_latency,
            "machine_recent_avg_latency": agent.machine_recent_avg_latency,
            "machine_baseline_latency": agent.machine_baseline_latency,
            "machine_observations": agent.machine_count,
            "generation_observations": agent.generation_count,
            "error_count": agent.error_count,
            "error_rate": agent.error_rate,
            "total_observations": agent.total_observations,
        }

    def get_all_agents(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot every tracked agent."""
        return {agent_id: self.get_agent_state(agent_id) for agent_id in self.agents}
