"""The monitoring agent itself — the control-room console.

Ties together the historian (StateModel), the alarm engine (AnomalyDetector),
and the response procedures (RecommendationEngine) behind one small surface:
ingest observations, then query the system state.

v0.2 changes (both driven by running the monitor on real data):
  - latency_high is now BASELINE-RELATIVE. It trips when an agent's recent
    latency is a sharp deviation from *its own* established normal, not when it
    crosses an absolute line. A consistently-slow-but-steady agent (a long
    teaching turn) no longer cries wolf; a 1000ms->9000ms spike still does.
    Guarded by a warmup (need history to deviate from) and an absolute floor
    (microsecond machine ops never trip on ratio alone).
  - get_system_state is INCREMENTAL. Ingest marks an agent dirty (O(1)); a scan
    re-evaluates only agents that changed since the last scan. A clean agent is
    never re-evaluated. ingest stays on the cheap hot path.
"""
from typing import Dict, Any, List, Set

from .observation import Observation
from .state_model import StateModel
from .anomaly_detector import AnomalyDetector, AnomalyRule
from .recommendations import RecommendationEngine

# --- default rule tuning (override by registering your own rules) -----------
LATENCY_DEVIATION_K = 3.0        # recent must exceed baseline by this factor
LATENCY_ABS_FLOOR_MS = 100.0     # ...and clear this absolute floor to matter
LATENCY_WARMUP = 4               # ...and the agent must have this many samples
ERROR_RATE_TRIP = 0.10
BACKLOG_MIN_OBSERVATIONS = 10


def _latency_spike(s: Dict[str, Any]) -> bool:
    """Trip when recent MACHINE latency is a sharp deviation from its baseline.

    Reads the machine-kind series only. Generation-kind durations are tracked
    elsewhere and structurally cannot reach this rule, so a long-but-expected
    output never trips it no matter how large. Within the machine series, all
    three guards must hold: enough history to have a baseline (warmup), a recent
    average above the absolute floor (so microsecond noise is ignored), and a
    recent average that exceeds the baseline by the deviation factor.
    """
    baseline = s.get("machine_baseline_latency", 0)
    recent = s.get("machine_recent_avg_latency", 0)
    return (
        s.get("machine_observations", 0) >= LATENCY_WARMUP
        and baseline > 0
        and recent > LATENCY_ABS_FLOOR_MS
        and recent > baseline * LATENCY_DEVIATION_K
    )


class LoggingAgent:
    """Public entry point for monitoring a fleet of worker agents."""

    def __init__(self):
        self.state_model = StateModel()
        self.anomaly_detector = AnomalyDetector()
        self.recommendation_engine = RecommendationEngine()

        # Incremental-scan bookkeeping: per-agent cache of {state, anomalies},
        # and the set of agents whose state changed since the last refresh.
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._dirty: Set[str] = set()

        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register the OT-inspired default alarm set."""

        # Latency deviation: an agent running hot relative to its OWN normal.
        self.anomaly_detector.add_rule(AnomalyRule(
            name="latency_high",
            check=_latency_spike,
            alert_level="HIGH",
            recommendation="Recent latency is a sharp deviation from this agent's baseline; throttle or investigate",
        ))

        # Error-rate climb.
        self.anomaly_detector.add_rule(AnomalyRule(
            name="error_rate_high",
            check=lambda s: s.get("error_rate", 0) > ERROR_RATE_TRIP,
            alert_level="MEDIUM",
            recommendation="Investigate failure root cause",
        ))

        # Silent backlog: lots of work, no errors — a healthy-looking agent that
        # may simply be a throughput bottleneck worth parallelizing.
        self.anomaly_detector.add_rule(AnomalyRule(
            name="queue_buildup",
            check=lambda s: (
                s.get("total_observations", 0) > BACKLOG_MIN_OBSERVATIONS
                and s.get("error_rate", 0) < 0.05
            ),
            alert_level="LOW",
            recommendation="Consider increasing worker parallelism",
        ))

    # --- ingest -----------------------------------------------------------
    def ingest(self, observation: Observation) -> None:
        """Record one observation. O(1): update state, mark the agent dirty."""
        self.state_model.ingest_observation(observation)
        self._dirty.add(observation.agent_id)

    # --- query ------------------------------------------------------------
    def get_agent_state(self, agent_id: str) -> Dict[str, Any]:
        """Current state of a single agent (always live, not cached)."""
        return self.state_model.get_agent_state(agent_id)

    def _refresh(self) -> None:
        """Re-evaluate only the agents that changed since the last refresh.

        This is the whole point of the dirty set: a clean agent's cached state
        and anomalies are reused verbatim, so a scan costs O(changed-agents x
        rules), not O(all-agents x rules).
        """
        for agent_id in self._dirty:
            state = self.state_model.get_agent_state(agent_id)
            self._cache[agent_id] = {
                "state": state,
                "anomalies": self.anomaly_detector.detect(state),
            }
        self._dirty.clear()

    def get_system_state(self) -> Dict[str, Any]:
        """Full fleet snapshot: per-agent state, tripped anomalies, recommendations."""
        self._refresh()

        agents = {aid: entry["state"] for aid, entry in self._cache.items()}
        anomalies: List[Dict[str, Any]] = []
        for entry in self._cache.values():
            anomalies.extend(entry["anomalies"])

        recommendations = self.recommendation_engine.generate(anomalies)

        return {
            "agents": agents,
            "anomalies": anomalies,
            "recommendations": recommendations,
        }

    # --- extend -----------------------------------------------------------
    def add_anomaly_rule(self, rule: AnomalyRule) -> None:
        """Register a custom rule and invalidate the cache so it applies to all agents."""
        self.anomaly_detector.add_rule(rule)
        # Every agent must be re-evaluated under the new rule set on the next scan.
        self._dirty.update(self.state_model.agents.keys())
