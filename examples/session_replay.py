"""Replay THIS Claude Code session through the monitor.

Honesty contract:
  - REAL: the action sequence, the role that performed each action, and the
    status of each call. The two failures encoded here genuinely happened this
    session (a first example run that hit ModuleNotFoundError before the
    editable install, and a memory-file edit whose match string was stale).
  - ESTIMATED: latency_ms. There is no per-turn wall-clock, so these are
    representative magnitudes (big generations high, file writes low). They are
    labelled as estimates and should be read as such.

The point: feed a real event stream into the monitor and see what it surfaces.

Run: python examples/session_replay.py
"""
from datetime import datetime, timedelta, timezone

from agent_logging_system import LoggingAgent, Observation, LATENCY_GENERATION, LATENCY_MACHINE

# Roles whose latency is generation wall-clock (producing a deliberately large
# output), not machine execution time. These structurally cannot trip the
# latency alarm no matter how long they run.
GENERATION_ROLES = {"explainer", "planner"}

# (role, action, latency_ms_estimate, status) in the order they occurred.
SESSION = [
    # explainer: the OT teaching turns. These were the heaviest generations of
    # the session, so they carry the highest estimated latency.
    ("explainer", "explain_shift_walkthrough", 8000, "success"),
    ("explainer", "explain_aveva_pi", 11000, "success"),
    ("explainer", "explain_wincc", 12000, "success"),
    ("explainer", "explain_maximo", 12000, "success"),
    ("explainer", "explain_better_architecture", 9000, "success"),

    # planner: the writing-plans skill. One big single generation.
    ("planner", "write_implementation_plan", 15000, "success"),

    # memory: reads/writes to the memory store. The first BUILT-status edit
    # FAILED on a stale match string, then succeeded after a re-read.
    ("memory", "save_format_feedback", 300, "success"),
    ("memory", "edit_built_status", 250, "failed"),   # REAL failure: string not found
    ("memory", "read_memory_file", 150, "success"),
    ("memory", "edit_description", 200, "success"),

    # builder: the actual build. 21 file writes + test/example/install runs.
    ("builder", "mkdir_tree", 120, "success"),
    ("builder", "write___init__", 200, "success"),
    ("builder", "write_observation", 250, "success"),
    ("builder", "write_state_model", 400, "success"),
    ("builder", "write_anomaly_detector", 300, "success"),
    ("builder", "write_recommendations", 280, "success"),
    ("builder", "write_logging_agent", 420, "success"),
    ("builder", "write_adapters_init", 150, "success"),
    ("builder", "write_base_adapter", 320, "success"),
    ("builder", "write_warrant_adapter", 350, "success"),
    ("builder", "write_tests_init", 100, "success"),
    ("builder", "write_test_observation", 260, "success"),
    ("builder", "write_test_state_model", 380, "success"),
    ("builder", "write_test_anomaly_detector", 340, "success"),
    ("builder", "write_test_logging_agent", 360, "success"),
    ("builder", "write_test_integration", 300, "success"),
    ("builder", "write_pytest_ini", 110, "success"),
    ("builder", "write_example_basic", 330, "success"),
    ("builder", "write_example_warrant", 300, "success"),
    ("builder", "write_readme", 380, "success"),
    ("builder", "write_examples_readme", 150, "success"),
    ("builder", "run_pytest", 1500, "success"),
    ("builder", "run_example_basic", 900, "failed"),   # REAL failure: ModuleNotFoundError
    ("builder", "write_pyproject", 220, "success"),
    ("builder", "pip_install_editable", 4000, "success"),
    ("builder", "run_example_basic_retry", 1200, "success"),
    ("builder", "run_example_warrant", 1100, "success"),
    ("builder", "verify_import_neutral_cwd", 800, "success"),
]


def replay() -> None:
    monitor = LoggingAgent()
    base = datetime.now(timezone.utc)

    for i, (role, action, latency, status) in enumerate(SESSION):
        ts = (base + timedelta(seconds=i)).replace(microsecond=0).isoformat()
        kind = LATENCY_GENERATION if role in GENERATION_ROLES else LATENCY_MACHINE
        monitor.ingest(Observation(
            timestamp=ts,
            agent_id=f"{role}-001",
            action=action,
            input={"seq": i},
            output=None if status == "failed" else {"ok": True},
            latency_ms=latency,
            status=status,
            confidence=0.0 if status == "failed" else 0.95,
            latency_kind=kind,
        ))

    state = monitor.get_system_state()

    print("=" * 78)
    print("SESSION REPLAY  —  this conversation, fed through the monitor")
    print("  (action sequence + status: REAL | latency: estimated magnitudes)")
    print("=" * 78)

    print("\nROLE STATES:")
    for agent_id, s in sorted(state["agents"].items()):
        print(f"\n  {agent_id}")
        print(f"    observations:       {s['total_observations']}")
        print(f"    errors:             {s['error_count']}  (rate {s['error_rate']:.1%})")
        print(f"    avg latency:        {s['avg_latency']:.0f}ms  (lifetime)")
        print(f"    recent avg latency: {s['recent_avg_latency']:.0f}ms  (last 3)")

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
            print(f"           {r['reason']}")
    else:
        print("  none")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    replay()
