"""The structured unit a worker agent emits.

This is the OT analogue of a single sensor reading on the historian: one
timestamped data point with quality/status metadata attached. Everything
downstream (state, trends, anomalies) is built from a stream of these.
"""
from dataclasses import dataclass
from typing import Any, Optional, Dict

# latency_kind values. The distinction is load-bearing: these two quantities are
# different types that happen to share a unit (ms), and conflating them is what
# made the v0.1 latency alarm cry wolf.
LATENCY_MACHINE = "machine"        # execution time of a call; HIGH is BAD (slow, contended)
LATENCY_GENERATION = "generation"  # wall-clock of producing an output; HIGH is often EXPECTED


@dataclass
class Observation:
    """A single structured observation emitted by a worker agent."""

    timestamp: str                              # ISO8601, e.g. "2026-06-02T14:32:00Z"
    agent_id: str                               # unique agent identifier
    action: str                                 # api_call, computation, decision, error, ...
    input: Any                                  # input to the action (query, data, prompt)
    output: Any = None                          # output of the action
    latency_ms: float = 0.0                     # duration in milliseconds (see latency_kind)
    status: str = "success"                     # success | retry | failed | timeout
    confidence: float = 1.0                     # confidence in the result, 0.0-1.0
    error_details: Optional[Dict[str, str]] = None  # error metadata when status != success
    # What latency_ms MEANS. "machine" = execution time (a spike is pathological,
    # feeds the latency alarm). "generation" = wall-clock of an intentionally
    # large output (a long value is expected, never feeds the latency alarm).
    # Defaults to "machine": the conservative choice for a monitor is to treat an
    # unclassified duration as alarmable rather than silently ignore a real spike.
    latency_kind: str = LATENCY_MACHINE
