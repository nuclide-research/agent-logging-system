from agent_logging_system import LoggingAgent, Observation


def test_multi_agent_monitoring():
    """Walk an agent through normal -> latency spike, and a second into errors."""
    logging_agent = LoggingAgent()

    # Phase 1: normal operation on worker-001 -> no anomalies.
    for i in range(3):
        logging_agent.ingest(Observation(
            f"2026-06-02T14:32:{i:02d}Z", "worker-001", "api_call",
            {"id": i}, {"result": "ok"}, latency_ms=1000 + i * 100, status="success",
        ))
    assert logging_agent.get_system_state()["anomalies"] == []

    # Phase 2: latency spike on worker-001 -> latency_high trips on recent window.
    for i in range(3, 6):
        logging_agent.ingest(Observation(
            f"2026-06-02T14:33:{i:02d}Z", "worker-001", "api_call",
            {"id": i}, {"result": "ok"}, latency_ms=8000, status="success",
        ))
    anomalies = logging_agent.get_system_state()["anomalies"]
    assert any(a["name"] == "latency_high" for a in anomalies)

    # Phase 3: a second agent accrues errors.
    for i in range(6, 9):
        status = "failed" if i % 2 == 0 else "success"
        logging_agent.ingest(Observation(
            f"2026-06-02T14:34:{i:02d}Z", "worker-002", "computation",
            {"data": i}, None if status == "failed" else {"result": "ok"},
            latency_ms=5000, status=status,
        ))
    state = logging_agent.get_system_state()
    assert state["agents"]["worker-002"]["error_rate"] > 0


def test_recommendations_are_actionable():
    """Every emitted recommendation has the full actionable shape.

    Uses a latency *spike* (low baseline then a jump): under v0.2 baseline-
    relative semantics, a uniform-high series is normal-for-the-agent and would
    not trip, so a deviation is what produces the recommendation.
    """
    logging_agent = LoggingAgent()
    for i, lat in enumerate((800, 900, 850, 1000, 9000, 9500, 9000)):
        logging_agent.ingest(Observation(
            f"2026-06-02T14:35:{i:02d}Z", "worker-003", "api_call",
            {}, {}, latency_ms=lat, status="success",
        ))

    recs = logging_agent.get_system_state()["recommendations"]
    assert len(recs) > 0
    for rec in recs:
        assert "action" in rec and "priority" in rec and "reason" in rec and "agent_id" in rec
        assert rec["action"] in ("throttle_input", "investigate_failures", "check_dependencies")
