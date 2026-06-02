"""Orchestrator integration demo: monitor an O->S->H subagent fan-out.

Simulates one orchestration cycle:
  - a retrieval lane (Sonnet) fans out 3 Explore subagents, all healthy
  - an execution lane (Haiku) fans out many parse/transform subagents; one batch
    of them runs slow (a real machine-latency spike for that lane)
  - the orchestrator integrates everything in a long synthesis turn (generation)

What the monitor should conclude:
  - execution lane: latency_high (the slow batch) and/or queue_buildup (volume)
  - retrieval lane: quiet
  - orchestrator synthesis: quiet, despite being the longest single duration

Run: python examples/orchestrator_integration.py
"""
from agent_logging_system import LoggingAgent
from agent_logging_system.adapters.orchestrator_adapter import OrchestratorAdapter


def main() -> None:
    monitor = LoggingAgent()
    orch = OrchestratorAdapter(monitor)

    # Retrieval lane: 3 Explore subagents fan out, all healthy (~1.2s).
    orch.log_fanout(orch.RETRIEVAL, [
        ("grep auth patterns", 1200),
        ("map data flow", 1300),
        ("find config files", 1100),
    ])

    # Execution lane: many Haiku transforms at a ~500ms baseline, then a slow
    # batch that is still in flight (the most recent dispatches). 11 clean
    # dispatches total, with the slowdown current.
    orch.log_fanout(orch.EXECUTION, [
        ("parse finding 1", 480),
        ("parse finding 2", 520),
        ("parse finding 3", 500),
        ("parse finding 4", 510),
        ("parse finding 5", 490),
        ("parse finding 6", 540),
        ("parse finding 7", 505),
        ("parse finding 8", 515),
        ("normalize batch A", 8800),     # slow, and current
        ("normalize batch B", 9200),     # slow, and current
        ("normalize batch C", 9000),     # slow, and current
    ])

    # Orchestrator integrates everything: the single longest duration, but expected.
    orch.log_synthesis(18000)

    state = monitor.get_system_state()

    print("=" * 78)
    print("ORCHESTRATION CYCLE  —  O->S->H fan-out under the monitor")
    print("=" * 78)

    print("\nLANES:")
    for lane, s in sorted(state["agents"].items()):
        kind = "generation" if s["generation_observations"] else "machine"
        print(f"\n  {lane}   [{kind}]")
        print(f"    dispatches:         {s['total_observations']}  "
              f"(errors {s['error_count']}, {s['error_rate']:.0%})")
        if s["machine_observations"]:
            print(f"    machine recent avg: {s['machine_recent_avg_latency']:.0f}ms")
            print(f"    machine baseline:   {s['machine_baseline_latency']:.0f}ms")
        else:
            print(f"    generation avg:     {s['avg_latency']:.0f}ms  (never alarms)")

    print("\nALARMS:")
    if state["anomalies"]:
        for a in state["anomalies"]:
            print(f"  [{a['alert_level']:>6}] {a['name']:<16} {a['agent_id']}")
    else:
        print("  none")

    print("\nRECOMMENDED RESPONSE:")
    if state["recommendations"]:
        for r in state["recommendations"]:
            print(f"  [{r['priority']:>6}] {r['action']:<22} {r['agent_id']}")
    else:
        print("  none")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
