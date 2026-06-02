from agent_logging_system.observation import (
    Observation, LATENCY_MACHINE, LATENCY_GENERATION,
)


def test_observation_creation():
    """Observation holds the required fields verbatim."""
    obs = Observation(
        timestamp="2026-06-02T14:32:00Z",
        agent_id="worker-001",
        action="api_call",
        input={"query": "CVE-2025-4364"},
        output={"count": 23},
        latency_ms=1240,
        status="success",
        confidence=0.92,
    )
    assert obs.timestamp == "2026-06-02T14:32:00Z"
    assert obs.agent_id == "worker-001"
    assert obs.latency_ms == 1240


def test_observation_with_error():
    """Observation can carry structured error detail on failure."""
    obs = Observation(
        timestamp="2026-06-02T14:32:05Z",
        agent_id="worker-002",
        action="computation",
        input={"data": [1, 2, 3]},
        output=None,
        latency_ms=5000,
        status="failed",
        confidence=0.0,
        error_details={"type": "TimeoutError", "message": "Computation exceeded timeout"},
    )
    assert obs.status == "failed"
    assert obs.error_details["type"] == "TimeoutError"


def test_observation_defaults():
    """Optional fields default sensibly for a minimal success observation."""
    obs = Observation(
        timestamp="2026-06-02T14:32:00Z",
        agent_id="worker-003",
        action="decision",
        input={"choice": "A"},
    )
    assert obs.output is None
    assert obs.latency_ms == 0.0
    assert obs.status == "success"
    assert obs.confidence == 1.0
    assert obs.error_details is None
    assert obs.latency_kind == LATENCY_MACHINE        # unclassified duration defaults to machine


def test_observation_generation_kind():
    """An observation can declare its latency as generation wall-clock."""
    obs = Observation(
        timestamp="2026-06-02T14:32:00Z",
        agent_id="explainer-001",
        action="explain_topic",
        input={"topic": "aveva pi"},
        output={"text": "..."},
        latency_ms=12000,
        latency_kind=LATENCY_GENERATION,
    )
    assert obs.latency_kind == LATENCY_GENERATION
