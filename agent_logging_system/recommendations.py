"""Turn tripped anomalies into actionable recommendations.

The OT analogue: the operator's response procedure. An alarm tells you
*something is wrong*; the procedure tells you *what to do about it*. We map each
known anomaly name to a concrete verb (throttle_input, investigate_failures,
check_dependencies) so downstream code or a human can act without re-deriving
intent. Unknown anomalies are passed over silently rather than guessed at.
"""
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class Recommendation:
    """An actionable instruction derived from an anomaly."""

    action: str                                 # throttle_input, investigate_failures, ...
    reason: str
    priority: str                               # HIGH | MEDIUM | LOW


class RecommendationEngine:
    """Maps anomaly names to concrete, actionable recommendations."""

    # anomaly name -> action template
    ACTION_MAP: Dict[str, Dict[str, str]] = {
        "latency_high": {
            "action": "throttle_input",
            "priority": "HIGH",
            "reason": "Recent latency exceeds threshold; reduce input rate or raise timeout",
        },
        "error_rate_high": {
            "action": "investigate_failures",
            "priority": "MEDIUM",
            "reason": "Error rate exceeds acceptable threshold; inspect failure root cause",
        },
        "blocked_too_long": {
            "action": "check_dependencies",
            "priority": "MEDIUM",
            "reason": "Agent blocked beyond threshold duration; verify upstream dependency",
        },
    }

    def generate(self, anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []
        for anomaly in anomalies:
            template = self.ACTION_MAP.get(anomaly["name"])
            if template is None:
                continue
            rec = dict(template)
            rec["agent_id"] = anomaly.get("agent_id", "unknown")
            recommendations.append(rec)
        return recommendations
