# Agent Logging System

Operational monitoring for multi-agent AI. A logging agent watches your worker agents. It tracks each one's trend, raises an alarm when a signal drifts from its own normal, and says what to do about it.

The design is borrowed from industrial control rooms. That story is below. It is also why the tool works the way it does.

## Where this came from

A power plant runs on three systems. AVEVA PI is the historian: it records every sensor reading, dozens a second, and keeps years of it. Siemens WinCC is the operator console: it shows the live state and raises an alarm when a value crosses a limit. IBM Maximo holds the maintenance history and schedules what to fix next.

An operator does not watch one live number. They read the trend. They keep a written log and hand it off at shift change. They catch a failing pump bearing weeks before it seizes. They read it in a slow climb of vibration and a few degrees of extra heat.

A fleet of AI agents needs that discipline and rarely has it. This tool maps the control room onto the agents:

| Component | Control room | Responsibility |
|-----------|--------------|----------------|
| `Observation` | one sensor reading | the structured unit a worker emits |
| `StateModel` | the historian and the operator's running model | rolling window, trends, error rate |
| `AnomalyDetector` | the WinCC alarm engine | evaluate threshold rules over state |
| `RecommendationEngine` | the operator's response procedure | map an alarm to a concrete action |
| `LoggingAgent` | the console | one surface: `ingest`, then query |
| `adapters/` | the wiring to the plant | bind into an orchestrator, a coding agent, anything |

One control-room rule became a feature. A threshold has to be relative to normal for that signal. A boiler at 200F is fine. A cooling tower at 200F is an emergency. Same number, different baseline. So the latency alarm compares each agent against its own history, not a fixed line.

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

## Default rules

| Rule | Trips when | Level | Recommends |
|------|-----------|-------|-----------|
| `latency_high` | recent machine latency is a sharp deviation from the agent's own baseline (over 3x, above a 100ms floor, after a 4-sample warmup) | HIGH | `throttle_input` |
| `error_rate_high` | error rate over 10% | MEDIUM | `investigate_failures` |
| `queue_buildup` | over 10 observations and error rate under 5% | LOW | signal only |

`latency_high` is baseline-relative and watches machine-kind latency only (see below). It compares the recent window against the agent's own established normal. An agent that runs slow but steady, like a heavy batch job, does not cry wolf. A jump from 1000ms to 9000ms still trips. Two guards keep it honest. The first is a warmup. You cannot judge a deviation from a single sample. The second is an absolute floor. A 1us to 50us blip is a 50x ratio and means nothing.

### Latency kinds

`latency_ms` means two different things, set by `latency_kind`:

| kind | what it is | high means | feeds `latency_high`? |
|------|-----------|-----------|----------------------|
| `"machine"` (default) | execution time of a call | pathological, slow or contended | yes |
| `"generation"` | wall-clock of producing a long output | usually expected | no, ever |

This is the root-cause fix beneath baseline-relativity. Mixing the two is a type error wearing a number's clothing. A 9s API call that should take 1s and a 9s explanation that was meant to be long are not the same event. Tagging an observation `latency_kind="generation"` makes it structurally impossible for that duration to trip the machine alarm, at any size. Machine is the default, so the monitor treats an unclassified duration as alarmable.

```python
from agent_logging_system import Observation, LATENCY_GENERATION

Observation(
    timestamp="...", agent_id="explainer-001", action="explain",
    input={...}, output={...}, latency_ms=12000,
    latency_kind=LATENCY_GENERATION,   # 12s is fine; never alarms
)
```

## Performance

`get_system_state` is incremental. `ingest` is O(1) and only marks the agent dirty. A scan re-evaluates only the agents that changed since the last scan, so a clean agent is never re-checked. Measured cost, from the self-monitor with real timings:

| Operation | Cost | Scaling |
|-----------|------|---------|
| `ingest` | about 2 us | O(1) |
| `get_system_state` | about 15 to 27 us for 5 agents | O(changed agents x rules) |

The rule for a large fleet: ingest every event. The scan only pays for what changed.

## Usage patterns

**Standalone.** Construct a `LoggingAgent`, `ingest()` observations, query `get_system_state()`.

**Via adapter.** Subclass `BaseAdapter` to log in domain terms. Two ship in the box.

- `WarrantAdapter` is for a book-grounded coding agent. Reasoning and code generation log as `generation`. Citation checks log as `machine`.
- `OrchestratorAdapter` is for an O->S->H subagent fan-out. Dispatches log per lane (`retrieval.sonnet`, `execution.haiku`) as `machine` latency, so a lane builds a baseline and a slow batch trips. The orchestrator's synthesis turn logs as `generation`, so a long integration never alarms.

```python
from agent_logging_system import LoggingAgent
from agent_logging_system.adapters import OrchestratorAdapter

orch = OrchestratorAdapter(LoggingAgent())
orch.log_fanout(orch.EXECUTION, [("shard 1", 480), ("shard 2", 9000)])  # machine, per-lane
orch.log_synthesis(18000)                                               # generation, never alarms
print(orch.get_state()["anomalies"])
```

**Custom rules.**

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
python examples/warrant_integration.py      # Warrant adapter logging reasoning, code, citations
python examples/orchestrator_integration.py # O->S->H fan-out: a slow lane alarms, a long synthesis does not
python examples/session_replay.py           # replay a real session transcript through the monitor
python examples/self_monitor.py             # the monitor watching the monitor, with real perf timings
```

## How it was built

Built in one sitting, then pointed at real data. The data rewrote it twice.

Version 0.1 used a fixed latency threshold. The tests passed. Then it ran against a transcript of the session that built it and raised two false alarms. The monitor flagged long explanations as slow. The threshold was wrong.

Version 0.2 made the alarm baseline-relative, comparing each agent to its own normal. The false alarms went away. The real signals stayed.

Then the monitor ran on itself, with real timings. Its own method calls took microseconds and never tripped. That exposed the real mistake. The latency field had carried two different meanings under one name. Execution time and output wall-clock are not the same quantity.

Version 0.3 split them in the schema. A duration tagged `generation` can no longer reach the machine alarm, at any size.

Version 0.4 added the orchestrator adapter. It watches a subagent fan-out one lane at a time.

Every version got better by running against something real. Harder reasoning did not do it. That is what the control room teaches. Trust the trend you measured, not the spec sheet.

## Design principles

1. **Trend over snapshot.** Degradation is a slope, not a point. Watch the recent window.
2. **Actionable over descriptive.** An alarm names the problem. A recommendation names the fix.
3. **The monitor outlives what it watches.** A rule that raises is skipped, never fatal.
4. **Extensible by default.** Rules and adapters are the seams. The core stays small.
5. **No hard dependencies.** Standard library only. It drops into any system.
