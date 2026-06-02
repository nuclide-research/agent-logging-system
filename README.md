# Agent Logging System

Operational discipline for multi-agent AI systems. A dedicated logging/monitoring agent watches worker agents with structured observation, trend analysis, and rule-based anomaly detection — modeled on industrial OT/ICS shift-operations monitoring.

The core idea, borrowed from a control-room operator: you do not stare at one live number. You watch the *trend*, you keep a structured log, and you catch a bearing going bad from the vibration creep weeks before it seizes. Same discipline, applied to a fleet of agents.

## Quick start

```python
from agent_logging_system import LoggingAgent, Observation

logger = LoggingAgent()

logger.ingest(Observation(
    timestamp="2026-06-02T14:32:00Z",
    agent_id="worker-001",
    action="api_call",
    input={"query": "example"},
    output={"result": "ok"},
    latency_ms=1200,
    status="success",
    confidence=0.95,
))

state = logger.get_system_state()
print(state["anomalies"])
print(state["recommendations"])
```

## Architecture

```
Worker agents emit Observations
        |
        v
   LoggingAgent  (the control-room console)
        |-- StateModel            : rolling per-agent state + trends (the historian)
        |-- AnomalyDetector       : rule-based threshold checks      (the alarm engine)
        +-- RecommendationEngine  : anomaly -> actionable verb        (the response procedure)
        |
        v
   get_system_state() -> { agents, anomalies, recommendations }
```

| Component | OT analogue | Responsibility |
|-----------|-------------|----------------|
| `Observation` | one sensor reading | structured unit a worker emits |
| `StateModel` | historian + operator's running model | rolling window, trends, error rate |
| `AnomalyDetector` | WinCC alarm engine | evaluate threshold rules over state |
| `RecommendationEngine` | operator response procedure | map an alarm to a concrete action |
| `LoggingAgent` | the console | one surface: `ingest` then query |
| `adapters/` | wiring to the plant | bind into Warrant, an orchestrator, etc. |

## Default rules

| Rule | Trips when | Level | Recommends |
|------|-----------|-------|-----------|
| `latency_high` | recent-window avg latency is a sharp deviation from the agent's own baseline (>3x, above a 100ms floor, after a 4-sample warmup) | HIGH | `throttle_input` |
| `error_rate_high` | error rate > 10% | MEDIUM | `investigate_failures` |
| `queue_buildup` | >10 observations and error rate < 5% | LOW | (signal only) |

`latency_high` is **baseline-relative**, not absolute, and applies **only to machine-kind latency** (see below). It compares the recent window against the agent's *own* established normal, so an agent that is consistently slow-but-steady (a heavy batch job) does not cry wolf, while a `1000ms -> 9000ms` spike still trips. This is the OT lesson turned into code: a boiler at 200F is fine, a cooling tower at 200F is an emergency — the same number means different things against different baselines. Two guards keep it honest: a warmup (you cannot detect deviation from a single sample) and an absolute floor (a `1us -> 50us` machine blip is a 50x ratio but meaningless).

### Latency kinds (the schema-level fix)

`latency_ms` means two different things depending on `latency_kind`:

| kind | what it is | high means | feeds `latency_high`? |
|------|-----------|-----------|----------------------|
| `"machine"` (default) | execution time of a call | pathological (slow, contended) | **yes** |
| `"generation"` | wall-clock of producing a deliberately large output | usually expected | **no, ever** |

This is the root-cause fix beneath baseline-relativity. Conflating the two is a type error wearing a number's clothing: a 9s API call that should take 1s and a 9s teaching turn that was *meant* to be long are not the same event. Tagging an observation `latency_kind="generation"` makes it **structurally impossible** for that duration to trip the machine-latency alarm, regardless of magnitude or how it deviates from its own history. Machine is the default so an unclassified duration is treated as alarmable rather than silently ignored.

```python
from agent_logging_system import Observation, LATENCY_GENERATION

Observation(
    timestamp="...", agent_id="explainer-001", action="explain",
    input={...}, output={...}, latency_ms=12000,
    latency_kind=LATENCY_GENERATION,   # 12s is fine; never alarms
)
```

### Why these rules look the way they do

Both the latency semantics and the scan design came from **running the monitor on real data** — first on a real session transcript, then on the monitor itself. The session replay exposed that an absolute latency threshold false-flags intentionally-long outputs; the self-monitor (real `perf_counter` timings) confirmed the rule is silent on genuine machine latencies and measured the scan cost model below. Testing on real streams did not just validate the tool, it corrected its design.

## Performance

`get_system_state` is **incremental**. `ingest` is O(1) and only marks the agent dirty; a scan re-evaluates *only* the agents that changed since the last scan, so a clean agent is never re-checked. Measured cost (self-monitor, real timings):

| Operation | Cost | Scaling |
|-----------|------|---------|
| `ingest` | ~2 us | O(1) |
| `get_system_state` | ~15-27 us (5 agents) | O(changed agents x rules) |

The takeaway for fleet scale: ingest freely on every event; the scan only pays for what actually changed.

## Usage patterns

**Standalone** — construct a `LoggingAgent`, `ingest()` observations, query `get_system_state()`.

**Via adapter** — subclass `BaseAdapter` to log in domain terms. Two ship in the box:

- `WarrantAdapter` — book-grounded coding agent (reasoning/code-gen as `generation`, citation checks as `machine`).
- `OrchestratorAdapter` — an O->S->H subagent fan-out. Subagent dispatches are logged per **lane** (`retrieval.sonnet`, `execution.haiku`) as `machine` latency, so a lane accumulates a baseline and a slow batch trips; the orchestrator's synthesis turn is `generation`, so a long integration never alarms.

```python
from agent_logging_system import LoggingAgent
from agent_logging_system.adapters import OrchestratorAdapter

orch = OrchestratorAdapter(LoggingAgent())
orch.log_fanout(orch.EXECUTION, [("shard 1", 480), ("shard 2", 9000)])  # machine, per-lane
orch.log_synthesis(18000)                                               # generation, never alarms
print(orch.get_state()["anomalies"])
```

**Custom rules**

```python
from agent_logging_system.anomaly_detector import AnomalyRule

logger.add_anomaly_rule(AnomalyRule(
    name="confidence_collapse",
    check=lambda s: s.get("error_rate", 0) > 0.25,
    alert_level="HIGH",
    recommendation="Pause agent and review recent inputs",
))
```

## Tests

```bash
pytest          # from the project root
```

## Examples

```bash
python examples/basic_multi_agent.py        # three agents degrading at different rates
python examples/warrant_integration.py      # Warrant adapter logging reasoning/code/citations
python examples/orchestrator_integration.py # O->S->H fan-out: slow lane alarms, long synthesis does not
python examples/session_replay.py           # replay a real session transcript through the monitor
python examples/self_monitor.py             # the monitor watching the monitor, real perf timings
```

## Design principles

1. **Trend over snapshot** — degradation is a slope, not a point. Watch the recent window.
2. **Actionable over descriptive** — an alarm names the problem; a recommendation names the fix.
3. **The monitor outlives what it watches** — a rule that raises is skipped, never fatal.
4. **Extensible by default** — rules and adapters are the seams; the core stays small.
5. **Zero hard dependencies** — standard library only; drops into any system.
