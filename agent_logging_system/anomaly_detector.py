"""Rule-based anomaly detection over agent state.

The OT analogue: the alarm engine in WinCC. Each rule is a threshold check on
the current state snapshot; when it trips, it emits a named alarm with a
severity and a suggested operator response. Rules are pure predicates so they
stay easy to read, test, and extend.
"""
from dataclasses import dataclass
from typing import Callable, List, Dict, Any


@dataclass
class AnomalyRule:
    """A single threshold check against an agent-state snapshot."""

    name: str
    check: Callable[[Dict[str, Any]], bool]     # True => anomaly present
    alert_level: str                            # HIGH | MEDIUM | LOW
    recommendation: str


class AnomalyDetector:
    """Evaluates registered rules against agent state."""

    def __init__(self):
        self.rules: List[AnomalyRule] = []

    def add_rule(self, rule: AnomalyRule) -> None:
        self.rules.append(rule)

    def detect(self, agent_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return one entry per tripped rule for this agent state.

        A rule that raises (e.g. a missing key on an unusual state shape) is
        skipped rather than allowed to take down the whole monitor — the
        monitor must be more reliable than the things it watches.
        """
        anomalies: List[Dict[str, Any]] = []
        for rule in self.rules:
            try:
                if rule.check(agent_state):
                    anomalies.append({
                        "name": rule.name,
                        "alert_level": rule.alert_level,
                        "recommendation": rule.recommendation,
                        "agent_id": agent_state.get("agent_id", "unknown"),
                    })
            except Exception:
                continue
        return anomalies
