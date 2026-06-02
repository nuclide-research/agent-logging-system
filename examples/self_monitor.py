"""Run the monitoring system on the monitoring system.

A meta-monitor observes an inner-monitor's own method calls. Unlike the session
replay, EVERYTHING here is real: the action sequence AND the latency, measured
with time.perf_counter on actual method execution. This is the monitor watching
itself do its job.

Levels:
  inner  : a LoggingAgent doing ordinary work (ingesting a workload)
  meta   : a LoggingAgent timing every inner.ingest / inner.get_system_state
  (monitor^3): we time meta.get_system_state once at the end, just to show it composes

Run: python examples/self_monitor.py
"""
import time
from datetime import datetime, timezone

from agent_logging_system import LoggingAgent, Observation

_seq = 0


def _ts() -> str:
    global _seq
    _seq += 1
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat() + f"#{_seq}"


def timed_ingest(meta: LoggingAgent, inner: LoggingAgent, obs: Observation) -> None:
    """Run inner.ingest, measure it, and record a real observation on the meta-monitor."""
    t0 = time.perf_counter()
    inner.ingest(obs)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    meta.ingest(Observation(
        timestamp=_ts(), agent_id="inner.ingest", action="ingest",
        input={"for": obs.agent_id}, output={"ok": True},
        latency_ms=dt_ms, status="success",
    ))


def timed_state(meta: LoggingAgent, inner: LoggingAgent) -> dict:
    """Run inner.get_system_state, measure it, record it on the meta-monitor."""
    t0 = time.perf_counter()
    state = inner.get_system_state()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    meta.ingest(Observation(
        timestamp=_ts(), agent_id="inner.get_system_state", action="scan",
        input={"agents": len(state["agents"])}, output={"anomalies": len(state["anomalies"])},
        latency_ms=dt_ms, status="success",
    ))
    return state


def main() -> None:
    inner = LoggingAgent()
    meta = LoggingAgent()

    # Drive a realistic inner workload: 5 simulated worker agents, 250 ingests,
    # with a full inner scan every 50 ingests (so the scan path is exercised too).
    inner_agents = ["alpha", "beta", "gamma", "delta", "epsilon"]
    for i in range(250):
        wa = inner_agents[i % len(inner_agents)]
        # vary latency so the inner monitor has real trends to compute over
        latency = 500 + (i % 7) * 400
        status = "failed" if (i % 37 == 0) else "success"
        timed_ingest(meta, inner, Observation(
            timestamp=_ts(), agent_id=f"{wa}-001", action="work",
            input={"i": i}, output=None if status == "failed" else {"ok": True},
            latency_ms=latency, status=status,
        ))
        if i % 50 == 49:
            timed_state(meta, inner)

    inner_state = inner.get_system_state()
    meta_state = meta.get_system_state()

    print("=" * 78)
    print("SELF-MONITOR  —  the monitor watching the monitor  (all values REAL)")
    print("=" * 78)

    print("\n[ INNER ]  what the inner monitor concluded about its 5 workers:")
    print(f"    workers tracked: {len(inner_state['agents'])}")
    print(f"    alarms:          {[a['name'] + ':' + a['agent_id'] for a in inner_state['anomalies']]}")

    print("\n[ META ]  what the meta monitor measured about the inner monitor:")
    for agent_id, s in sorted(meta_state["agents"].items()):
        print(f"\n  {agent_id}")
        print(f"    calls measured:     {s['total_observations']}")
        print(f"    avg latency:        {s['avg_latency']*1000:.2f} microseconds")
        print(f"    recent avg latency: {s['recent_avg_latency']*1000:.2f} microseconds")
        print(f"    error rate:         {s['error_rate']:.1%}")

    print("\n[ META ]  alarms the meta monitor raised on the inner monitor:")
    if meta_state["anomalies"]:
        for a in meta_state["anomalies"]:
            print(f"    [{a['alert_level']:>6}] {a['name']:<16} {a['agent_id']}")
    else:
        print("    none")

    # monitor^3: time the meta monitor's own scan, just to show it composes.
    t0 = time.perf_counter()
    meta.get_system_state()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    print(f"\n[ MONITOR^3 ]  meta.get_system_state() itself took {dt_ms*1000:.2f} microseconds")
    print("    (a third monitor could watch this number; the abstraction composes cleanly)")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
