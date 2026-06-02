from agent_logging_system.logging_agent import LoggingAgent
from agent_logging_system.observation import Observation
from agent_logging_system.adapters.base_adapter import BaseAdapter
from agent_logging_system.adapters.warrant_adapter import WarrantAdapter


def _obs(agent_id, latency, status="success", ts="2026-06-02T14:32:00Z"):
    return Observation(ts, agent_id, "api_call", {}, {}, latency_ms=latency, status=status)


def test_logging_agent_ingest_and_analyze():
    """Observations flow into per-agent state retrievable from the system snapshot."""
    agent = LoggingAgent()
    for lat in (1000, 3000, 8000):
        agent.ingest(_obs("worker-001", lat))

    state = agent.get_system_state()
    assert "worker-001" in state["agents"]
    assert state["agents"]["worker-001"]["avg_latency"] > 3000


def test_logging_agent_latency_spike_is_anomaly():
    """A deviation from the agent's own baseline trips latency_high."""
    agent = LoggingAgent()
    for lat in (800, 900, 850, 1000, 9000, 9500, 9000):   # ~900 baseline, ~9000 spike
        agent.ingest(_obs("worker-001", lat))

    anomalies = agent.get_system_state()["anomalies"]
    assert any(a["name"] == "latency_high" for a in anomalies)


def test_logging_agent_uniform_high_latency_is_not_anomaly():
    """Consistently slow but steady is normal-for-this-agent, not an alarm.

    This is the explainer/teaching-turn case that v0.1 false-flagged: long
    outputs that were requested, not pathological. Baseline-relative semantics
    keep it quiet.
    """
    agent = LoggingAgent()
    for lat in (8000, 11000, 12000, 12000, 9000):
        agent.ingest(_obs("explainer-001", lat))

    anomalies = agent.get_system_state()["anomalies"]
    assert not any(a["name"] == "latency_high" for a in anomalies)


def test_logging_agent_single_observation_no_latency_alarm():
    """One sample cannot be a deviation from a baseline that does not exist yet.

    The planner/one-big-plan case that v0.1 false-flagged.
    """
    agent = LoggingAgent()
    agent.ingest(_obs("planner-001", 15000))

    anomalies = agent.get_system_state()["anomalies"]
    assert not any(a["name"] == "latency_high" for a in anomalies)


def test_logging_agent_microsecond_latency_never_trips():
    """Real machine latencies (microseconds) never trip on ratio alone.

    A 1us -> 50us jump is a 50x ratio but meaningless; the absolute floor guards
    it. This is the self-monitor case.
    """
    agent = LoggingAgent()
    for lat in (0.001, 0.001, 0.001, 0.001, 0.05, 0.05, 0.05):  # ms => 1us .. 50us
        agent.ingest(_obs("inner.ingest", lat))

    anomalies = agent.get_system_state()["anomalies"]
    assert not any(a["name"] == "latency_high" for a in anomalies)


def test_generation_latency_never_trips_even_on_spike():
    """A generation-kind spike cannot trip latency_high. The structural fix.

    Under v0.2 (baseline-relative on all-kinds latency), this 8000ms -> 30000ms
    generation series WOULD have tripped (a 3.75x deviation). Under v0.3 the
    generation kind never feeds the machine alarm, so it cannot trip at all.
    """
    from agent_logging_system.observation import LATENCY_GENERATION
    agent = LoggingAgent()
    for lat in (8000, 8000, 8000, 8000, 30000, 30000, 30000):
        agent.ingest(Observation(
            "2026-06-02T14:32:00Z", "explainer-001", "explain", {}, {},
            latency_ms=lat, status="success", latency_kind=LATENCY_GENERATION,
        ))

    anomalies = agent.get_system_state()["anomalies"]
    assert not any(a["name"] == "latency_high" for a in anomalies)


def test_machine_spike_trips_even_amid_generation_noise():
    """A real machine spike still fires even when the agent also does generation work."""
    from agent_logging_system.observation import LATENCY_GENERATION
    agent = LoggingAgent()
    # interleave big generation turns (should be ignored by the alarm) with a
    # machine series that ramps from ~900ms baseline to a 9000ms spike.
    machine_latencies = [800, 900, 850, 1000, 9000, 9500, 9000]
    for lat in machine_latencies:
        agent.ingest(_obs("mixed-001", lat))                       # machine (default)
        agent.ingest(Observation(
            "2026-06-02T14:32:00Z", "mixed-001", "explain", {}, {},
            latency_ms=25000, status="success", latency_kind=LATENCY_GENERATION,
        ))

    anomalies = agent.get_system_state()["anomalies"]
    assert any(a["name"] == "latency_high" for a in anomalies)


def test_logging_agent_query():
    """A single agent can be queried directly."""
    agent = LoggingAgent()
    agent.ingest(Observation("2026-06-02T14:32:00Z", "worker-001", "compute", {}, {}, latency_ms=500))

    s = agent.get_agent_state("worker-001")
    assert s["status"] == "in_progress"
    assert s["avg_latency"] == 500


def test_logging_agent_custom_rule():
    """A user-registered rule fires alongside the defaults."""
    agent = LoggingAgent()
    from agent_logging_system.anomaly_detector import AnomalyRule
    agent.add_anomaly_rule(AnomalyRule(
        name="low_confidence_proxy",
        check=lambda s: s.get("total_observations", 0) >= 2,
        alert_level="LOW",
        recommendation="custom",
    ))
    agent.ingest(_obs("worker-009", 100))
    agent.ingest(_obs("worker-009", 100))

    names = {a["name"] for a in agent.get_system_state()["anomalies"]}
    assert "low_confidence_proxy" in names


def test_incremental_scan_skips_clean_agents():
    """A clean agent is never re-evaluated; only dirty agents pay rule cost.

    Proven with a counting rule (no stopwatch): the rule appends on every
    evaluation, so the call count reveals exactly which agents were re-checked.
    """
    from agent_logging_system.anomaly_detector import AnomalyRule
    calls = []
    agent = LoggingAgent()
    # never fires; just records each evaluation
    agent.add_anomaly_rule(AnomalyRule(
        name="counter",
        check=lambda s: bool(calls.append(s["agent_id"])) and False,
        alert_level="LOW",
        recommendation="n/a",
    ))

    for aid in ("a", "b", "c"):
        agent.ingest(_obs(aid, 100))

    agent.get_system_state()
    after_first = len(calls)
    assert after_first == 3                 # each of a, b, c evaluated once

    agent.get_system_state()                # no new ingest -> no re-evaluation
    assert len(calls) == after_first

    agent.ingest(_obs("a", 100))            # only 'a' is now dirty
    agent.get_system_state()
    assert len(calls) == after_first + 1    # only 'a' re-evaluated


def test_add_rule_invalidates_cache():
    """Registering a rule forces re-evaluation of already-seen agents."""
    from agent_logging_system.anomaly_detector import AnomalyRule
    agent = LoggingAgent()
    agent.ingest(_obs("a", 100))
    agent.get_system_state()                # builds cache for 'a' under default rules

    calls = []
    agent.add_anomaly_rule(AnomalyRule(
        name="counter",
        check=lambda s: bool(calls.append(1)) and False,
        alert_level="LOW",
        recommendation="n/a",
    ))
    agent.get_system_state()                # must re-evaluate 'a' under the new rule
    assert len(calls) >= 1


def test_incremental_result_matches_expected():
    """The incremental path still surfaces the spike anomaly and its recommendation."""
    agent = LoggingAgent()
    for lat in (800, 900, 850, 1000, 9000, 9500, 9000):
        agent.ingest(_obs("w1", lat))

    state = agent.get_system_state()
    assert any(a["name"] == "latency_high" for a in state["anomalies"])
    assert any(r["action"] == "throttle_input" for r in state["recommendations"])


def test_base_adapter_interface():
    """BaseAdapter exposes the integration surface."""
    adapter = WarrantAdapter(LoggingAgent())     # concrete subclass; base is abstract
    assert isinstance(adapter, BaseAdapter)
    assert hasattr(adapter, "wrap_agent")
    assert hasattr(adapter, "emit_observation")
    assert hasattr(adapter, "get_state")


def test_warrant_adapter_monitors_reasoning():
    """WarrantAdapter routes a reasoning step into the monitor."""
    logging_agent = LoggingAgent()
    adapter = WarrantAdapter(logging_agent)

    adapter.log_reasoning_step(
        agent_id="warrant-001",
        source="some_book.md",
        question="What does section 3 say?",
        answer="Section 3 discusses X",
        confidence=0.95,
        latency_ms=2500,
    )

    s = logging_agent.get_agent_state("warrant-001")
    assert s["avg_latency"] == 2500


def test_warrant_adapter_failed_citation_counts_as_error():
    """An unverifiable citation is recorded as a failure."""
    logging_agent = LoggingAgent()
    adapter = WarrantAdapter(logging_agent)

    adapter.log_citation_check("warrant-001", "claim", "book.md", valid=False, latency_ms=150)

    s = logging_agent.get_agent_state("warrant-001")
    assert s["error_count"] == 1
