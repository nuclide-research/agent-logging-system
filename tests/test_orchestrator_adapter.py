from agent_logging_system import LoggingAgent
from agent_logging_system.adapters.orchestrator_adapter import OrchestratorAdapter


def test_dispatch_is_machine_synthesis_is_generation():
    """Subagent dispatches are machine-kind; synthesis is generation-kind."""
    la = LoggingAgent()
    adapter = OrchestratorAdapter(la)

    adapter.log_subagent_dispatch(adapter.EXECUTION, "parse json", 500)
    adapter.log_synthesis(12000)

    execution = la.get_agent_state(adapter.EXECUTION)
    orchestrator = la.get_agent_state(adapter.ORCHESTRATOR)

    assert execution["machine_observations"] == 1
    assert execution["generation_observations"] == 0
    assert orchestrator["generation_observations"] == 1
    assert orchestrator["machine_observations"] == 0


def test_lane_latency_spike_trips():
    """A dispatch that deviates sharply from its lane's baseline trips latency_high."""
    adapter = OrchestratorAdapter(LoggingAgent())
    # retrieval lane normally ~1s, then a 9s spike
    for lat in (1000, 1100, 950, 1050, 9000, 9500, 9000):
        adapter.log_subagent_dispatch(adapter.RETRIEVAL, "find refs", lat)

    anomalies = adapter.get_state()["anomalies"]
    assert any(
        a["name"] == "latency_high" and a["agent_id"] == adapter.RETRIEVAL
        for a in anomalies
    )


def test_synthesis_never_trips_even_on_long_output():
    """A long synthesis turn is expected and must never trip the latency alarm."""
    adapter = OrchestratorAdapter(LoggingAgent())
    for lat in (8000, 8000, 8000, 8000, 40000, 40000, 40000):
        adapter.log_synthesis(lat)

    anomalies = adapter.get_state()["anomalies"]
    assert not any(a["name"] == "latency_high" for a in anomalies)


def test_lane_error_rate_trips():
    """A failing lane raises error_rate_high for that lane."""
    adapter = OrchestratorAdapter(LoggingAgent())
    for i in range(10):
        status = "failed" if i % 3 == 0 else "success"   # 4/10 fail = 40%
        adapter.log_subagent_dispatch(adapter.EXECUTION, "task", 500, status=status)

    anomalies = adapter.get_state()["anomalies"]
    assert any(
        a["name"] == "error_rate_high" and a["agent_id"] == adapter.EXECUTION
        for a in anomalies
    )


def test_fanout_helper_logs_each_dispatch():
    """log_fanout records every dispatch in the batch under the lane."""
    la = LoggingAgent()
    adapter = OrchestratorAdapter(la)
    adapter.log_fanout(adapter.EXECUTION, [
        ("shard 1", 400),
        ("shard 2", 450),
        ("shard 3", 420, "failed"),
    ])

    state = la.get_agent_state(adapter.EXECUTION)
    assert state["total_observations"] == 3
    assert state["error_count"] == 1


def test_heavy_lane_raises_queue_buildup():
    """A lane carrying heavy clean volume raises queue_buildup (parallelism hint)."""
    adapter = OrchestratorAdapter(LoggingAgent())
    adapter.log_fanout(adapter.EXECUTION, [(f"shard {i}", 300) for i in range(15)])

    anomalies = adapter.get_state()["anomalies"]
    assert any(
        a["name"] == "queue_buildup" and a["agent_id"] == adapter.EXECUTION
        for a in anomalies
    )
