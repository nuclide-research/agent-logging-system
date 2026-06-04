# agent-logging-system

[![tests](https://img.shields.io/github/actions/workflow/status/nuclide-research/agent-logging-system/tests.yml?label=tests)](https://github.com/nuclide-research/agent-logging-system/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![python](https://img.shields.io/badge/python-3.9%2B-blue)

OT-inspired operational monitor for multi-agent AI: a logging agent watches your worker agents, tracks each one's trend against its own baseline, trips named alarms on deviation, and maps each alarm to a concrete action.

The design is borrowed from industrial control rooms. AVEVA PI holds every sensor reading. WinCC raises an alarm when a value drifts. IBM Maximo maps an alarm to a maintenance procedure. An operator reads the trend, not the snapshot, and catches a failing pump bearing weeks before it seizes from a slow climb in vibration. A fleet of AI agents needs that discipline. This tool maps the control room onto the agents: one `Observation` per action, a rolling-window `StateModel` that tracks trends per agent, an `AnomalyDetector` that trips on baseline deviation, and a `RecommendationEngine` that names the fix. Standard library only. No hard dependencies.

## Install

```bash
git clone https://github.com/nuclide-research/agent-logging-system
cd agent-logging-system
pip install -e .            # editable install from source
# or for dev work with tests:
pip install -e ".[dev]"
```

Python 3.9 or later. No runtime dependencies beyond the standard library.

Current version: `0.4.0`

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

## Components

| Component | OT analogue | Responsibility |
|-----------|-------------|----------------|
| `Observation` | one sensor reading | structured unit a worker emits: timestamp, agent_id, action, input, output, latency_ms, status, confidence, latency_kind |
| `StateModel` | historian + operator model | rolling window (20 obs), trends, error rate, machine vs generation latency counts |
| `AnomalyDetector` | WinCC alarm engine | evaluates threshold rules over state snapshot |
| `RecommendationEngine` | operator response procedure | maps alarm name to concrete action |
| `LoggingAgent` | control-room console | `ingest` + `get_system_state`; incremental scan |
| `adapters/` | wiring to the plant | bind into an orchestrator, coding agent, or custom loop |

## Observation schema

```python
Observation(
    timestamp: str,          # ISO8601, e.g. "2026-06-02T14:32:00Z"
    agent_id: str,           # unique agent identifier
    action: str,             # api_call, computation, decision, error, ...
    input: Any,              # input to the action
    output: Any = None,      # output of the action
    latency_ms: float = 0.0, # duration in ms (meaning set by latency_kind)
    status: str = "success", # success | retry | failed | timeout
    confidence: float = 1.0, # 0.0 to 1.0
    error_details: Optional[Dict[str, str]] = None,
    latency_kind: str = "machine",  # "machine" | "generation"
)
```

## Latency kinds

`latency_ms` carries two different quantities, distinguished by `latency_kind`:

| kind | what it is | high means | feeds `latency_high` alarm? |
|------|-----------|-----------|---------------------------|
| `"machine"` (default) | execution time of a call | pathological, contended | yes |
| `"generation"` | wall-clock of producing a large output | usually expected | no, ever |

Mixing them is a type error. A 9s API call that should take 1s and a 9s explanation meant to be long are not the same event. A duration tagged `generation` can never trip the machine alarm at any magnitude. `"machine"` is the default: an unclassified duration is treated as alarmable.

```python
from agent_logging_system import Observation, LATENCY_GENERATION

Observation(
    timestamp="...", agent_id="explainer-001", action="explain",
    input={...}, output={...}, latency_ms=12000,
    latency_kind=LATENCY_GENERATION,   # 12s is fine; never alarms
)
```

## Default rules

Three rules ship:

| Rule | Level | Trips when | Recommends |
|------|-------|-----------|-----------|
| `latency_high` | HIGH | machine-kind recent avg exceeds agent's own baseline by 3x, above a 100ms floor, after 4-sample warmup | `throttle_input` |
| `error_rate_high` | MEDIUM | error rate over 10% | `investigate_failures` |
| `queue_buildup` | LOW | over 10 observations and error rate under 5% | signal only |

`latency_high` is baseline-relative: it compares each agent against its own established normal, not a fixed line. A steady-but-slow agent does not cry wolf. A 1000ms to 9000ms jump still trips.

## `get_system_state` output

```python
{
    "agents": {
        "worker-001": {
            "agent_id": "worker-001",
            "status": "in_progress",
            "avg_latency": 1200.0,
            "recent_avg_latency": 1200.0,
            "baseline_latency": 0.0,
            "machine_recent_avg_latency": 1200.0,
            "machine_baseline_latency": 0.0,
            "machine_observations": 1,
            "generation_observations": 0,
            "error_count": 0,
            "error_rate": 0.0,
            "total_observations": 1,
            ...
        }
    },
    "anomalies": [
        {
            "name": "latency_high",
            "alert_level": "HIGH",
            "recommendation": "...",
            "agent_id": "worker-001"
        }
    ],
    "recommendations": [
        {
            "action": "throttle_input",
            "priority": "HIGH",
            "reason": "...",
            "agent_id": "worker-001"
        }
    ]
}
```

## Adapters

Subclass `BaseAdapter` to wire a host system into the monitor. Two ship:

**`OrchestratorAdapter`** for an O->S->H subagent fan-out. Dispatches log per lane (`retrieval.sonnet`, `execution.haiku`) as machine latency; a lane builds a baseline and a slow batch trips. The orchestrator's synthesis turn logs as generation latency; a long integration never alarms.

```python
from agent_logging_system import LoggingAgent
from agent_logging_system.adapters import OrchestratorAdapter

orch = OrchestratorAdapter(LoggingAgent())
orch.log_fanout(orch.EXECUTION, [("shard 1", 480), ("shard 2", 9000)])  # machine, per lane
orch.log_synthesis(18000)                                               # generation, never alarms
print(orch.get_state()["anomalies"])
```

**`WarrantAdapter`** for a book-grounded coding agent. Reasoning steps and code generation log as generation latency. Citation checks log as machine latency: a slow citation lookup is a real signal.

## Custom rules

```python
from agent_logging_system.anomaly_detector import AnomalyRule

logger.add_anomaly_rule(AnomalyRule(
    name="confidence_collapse",
    check=lambda s: s.get("error_rate", 0) > 0.25,
    alert_level="HIGH",
    recommendation="Pause agent and review recent inputs",
))
```

## Performance

`ingest` is O(1): update state, mark the agent dirty. `get_system_state` re-evaluates only agents that changed since the last scan.

| Operation | Cost |
|-----------|------|
| `ingest` | ~2 us |
| `get_system_state` | ~15 to 27 us for 5 agents |

## Tests

```bash
pytest
```

Seven test files cover the logging agent, observation schema, anomaly detector, state model, and orchestrator adapter.

## Examples

```bash
python examples/basic_multi_agent.py        # three agents degrading at different rates
python examples/warrant_integration.py      # Warrant adapter: reasoning, code, citation logs
python examples/orchestrator_integration.py # O->S->H fan-out: slow lane alarms, long synthesis does not
python examples/session_replay.py           # replay a session transcript through the monitor
python examples/self_monitor.py             # the monitor watching itself, with real perf timings
```

## What agent-logging-system is not

agent-logging-system is not a tracer, a profiler, or a logging framework. It does not capture stack frames, record every line of output, or send data to an external collector. It holds no persistent state: no database, no file on disk. It receives `Observation` structs your code constructs, evaluates rules over rolling per-agent windows, and returns a plain dict. It stops there.

## License

MIT. Part of the NuClide toolchain. Contact: [nuclide-research.com](https://nuclide-research.com)
