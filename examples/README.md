# Examples

## basic_multi_agent.py

Three worker agents (`researcher`, `coder`, `reviewer`) degrade at different
steps. Demonstrates real-time monitoring of multiple agents, recent-window
latency detection, error-rate tracking, and recommendation generation.

```bash
python examples/basic_multi_agent.py
```

## warrant_integration.py

Integrates the monitor with a Warrant (book-grounded coding) agent via
`WarrantAdapter`. Logs the three Warrant action shapes — reasoning, code
generation, citation check — then prints the system and per-agent state.

```bash
python examples/warrant_integration.py
```

## orchestrator_integration.py

Monitors an O->S->H subagent fan-out via `OrchestratorAdapter`. A retrieval lane
and an execution lane fan out; the execution lane hits a current slowdown and
trips `latency_high` + `queue_buildup`, while the orchestrator's 18s synthesis
turn (the longest single duration) stays silent because it is generation-kind.

```bash
python examples/orchestrator_integration.py
```

## session_replay.py

Replays a real session transcript through the monitor. Action sequence and
status are real; latency is estimated. Generation-kind turns (teaching, planning)
cannot trip the latency alarm; machine-kind turns (builds, edits) can.

```bash
python examples/session_replay.py
```

## self_monitor.py

The monitor watching the monitor, with real `perf_counter` timings. A meta
monitor measures an inner monitor's `ingest` and `get_system_state` costs;
`monitor^3` shows the abstraction composes.

```bash
python examples/self_monitor.py
```
