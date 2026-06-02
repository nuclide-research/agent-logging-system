from agent_logging_system.state_model import StateModel
from agent_logging_system.observation import Observation


def test_state_model_tracks_agent_status():
    """A single observation registers the agent and records its latency."""
    model = StateModel()
    obs = Observation(
        timestamp="2026-06-02T14:32:00Z",
        agent_id="worker-001",
        action="api_call",
        input={},
        output={},
        latency_ms=1000,
        status="success",
        confidence=0.95,
    )
    model.ingest_observation(obs)

    state = model.get_agent_state("worker-001")
    assert state["agent_id"] == "worker-001"
    assert state["status"] == "in_progress"
    assert state["recent_latency"] == [1000]


def test_state_model_tracks_trends():
    """Latency history accumulates and the full-window mean reflects it."""
    model = StateModel()
    for lat, conf in [(1000, 0.95), (3000, 0.90), (8000, 0.85)]:
        model.ingest_observation(Observation(
            "2026-06-02T14:32:00Z", "worker-001", "api_call", {}, {},
            latency_ms=lat, status="success", confidence=conf,
        ))

    state = model.get_agent_state("worker-001")
    assert state["recent_latency"] == [1000, 3000, 8000]
    assert state["avg_latency"] > 3000          # mean is 4000


def test_state_model_recent_window_reacts_to_spike():
    """recent_avg_latency tracks only the latest readings, so a spike shows."""
    model = StateModel()
    # Long healthy history, then a spike on the most recent three.
    for lat in [500, 500, 500, 500, 9000, 9000, 9000]:
        model.ingest_observation(Observation(
            "2026-06-02T14:32:00Z", "worker-001", "api_call", {}, {},
            latency_ms=lat, status="success",
        ))

    state = model.get_agent_state("worker-001")
    assert state["avg_latency"] < state["recent_avg_latency"]
    assert state["recent_avg_latency"] == 9000


def test_state_model_baseline_excludes_recent_window():
    """baseline_latency reflects older history, ignoring the recent spike."""
    model = StateModel()
    for lat in [1000, 1000, 1000, 1000, 9000, 9000, 9000]:
        model.ingest_observation(Observation(
            "2026-06-02T14:32:00Z", "w", "work", {}, {}, latency_ms=lat, status="success",
        ))
    s = model.get_agent_state("w")
    assert s["recent_avg_latency"] == 9000          # last 3
    assert s["baseline_latency"] < 2000             # the older 1000ms history
    assert s["recent_avg_latency"] > s["baseline_latency"] * 3   # a clear deviation


def test_state_model_baseline_zero_before_older_history():
    """With only a recent window's worth of samples there is no baseline yet."""
    model = StateModel()
    for lat in [5000, 5000, 5000]:                  # exactly RECENT_WINDOW samples
        model.ingest_observation(Observation(
            "2026-06-02T14:32:00Z", "w", "work", {}, {}, latency_ms=lat,
        ))
    assert model.get_agent_state("w")["baseline_latency"] == 0.0


def test_state_model_separates_latency_by_kind():
    """Machine and generation latencies are bucketed separately."""
    from agent_logging_system.observation import LATENCY_GENERATION
    model = StateModel()
    # two machine calls, one big generation turn
    model.ingest_observation(Observation("t", "w", "call", {}, {}, latency_ms=900))
    model.ingest_observation(Observation("t", "w", "call", {}, {}, latency_ms=1100))
    model.ingest_observation(Observation(
        "t", "w", "explain", {}, {}, latency_ms=12000, latency_kind=LATENCY_GENERATION,
    ))

    s = model.get_agent_state("w")
    assert s["machine_observations"] == 2
    assert s["generation_observations"] == 1
    assert s["total_observations"] == 3
    # the 12000ms generation turn must NOT pollute the machine series
    assert s["machine_recent_avg_latency"] == 1000     # mean of 900, 1100
    assert s["avg_latency"] > 4000                      # all-kinds display still includes it


def test_state_model_error_tracking():
    """Error and success counts drive the error rate."""
    model = StateModel()
    model.ingest_observation(Observation(
        "2026-06-02T14:32:00Z", "worker-001", "api_call", {}, {},
        latency_ms=1000, status="success",
    ))
    model.ingest_observation(Observation(
        "2026-06-02T14:32:05Z", "worker-001", "api_call", {}, {},
        latency_ms=5000, status="failed",
    ))

    state = model.get_agent_state("worker-001")
    assert state["error_count"] == 1
    assert state["error_rate"] == 0.5


def test_state_model_history_is_bounded():
    """Retained history never exceeds max_history."""
    model = StateModel(max_history=5)
    for i in range(20):
        model.ingest_observation(Observation(
            "2026-06-02T14:32:00Z", "worker-001", "api_call", {}, {},
            latency_ms=float(i), status="success",
        ))
    state = model.get_agent_state("worker-001")
    assert len(state["recent_latency"]) == 5
    assert state["total_observations"] == 20    # count is cumulative, history is bounded


def test_state_model_unknown_agent():
    """Querying an unseen agent returns an explicit unknown status."""
    model = StateModel()
    state = model.get_agent_state("nobody")
    assert state["status"] == "unknown"
