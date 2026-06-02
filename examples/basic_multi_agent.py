"""Multi-agent monitoring demo.

Three worker agents degrade at different rates. The monitor watches the stream
and surfaces the control-room view: per-agent state, tripped alarms, and the
operator's recommended response.

Run: python examples/basic_multi_agent.py
"""
from datetime import datetime, timedelta, timezone

from agent_logging_system import LoggingAgent, Observation


def simulate_multi_agent_workload() -> None:
    logging_agent = LoggingAgent()

    # Each agent has a healthy baseline latency and a step at which it degrades.
    agents = {
        "researcher": {"normal_latency": 1500, "degradation_start": 5},
        "coder": {"normal_latency": 800, "degradation_start": 3},
        "reviewer": {"normal_latency": 600, "degradation_start": 8},
    }

    base = datetime.now(timezone.utc)
    for step in range(12):
        ts = (base + timedelta(seconds=step * 5)).replace(microsecond=0).isoformat()
        for name, cfg in agents.items():
            if step >= cfg["degradation_start"]:
                latency = cfg["normal_latency"] + (step - cfg["degradation_start"]) * 1000
            else:
                latency = cfg["normal_latency"]
            status = "failed" if (step > 8 and step % 2 == 0) else "success"
            logging_agent.ingest(Observation(
                timestamp=ts,
                agent_id=f"{name}-001",
                action="process",
                input={"step": step},
                output=None if status == "failed" else {"step": step, "result": "ok"},
                latency_ms=latency,
                status=status,
                confidence=0.9 if status == "success" else 0.0,
            ))

    state = logging_agent.get_system_state()

    print("=" * 80)
    print("MULTI-AGENT MONITORING REPORT")
    print("=" * 80)

    print("\nAGENT STATES:")
    for agent_id, s in state["agents"].items():
        print(f"\n  {agent_id}:")
        print(f"    Status:             {s['status']}")
        print(f"    Avg Latency:        {s['avg_latency']:.0f}ms")
        print(f"    Recent Avg Latency: {s['recent_avg_latency']:.0f}ms")
        print(f"    Error Rate:         {s['error_rate']:.1%}")
        print(f"    Observations:       {s['total_observations']}")

    print("\nANOMALIES DETECTED:")
    if state["anomalies"]:
        for a in state["anomalies"]:
            print(f"  [{a['alert_level']:>6}] {a['name']:<16} (agent: {a['agent_id']})")
    else:
        print("  None")

    print("\nRECOMMENDATIONS:")
    if state["recommendations"]:
        for r in state["recommendations"]:
            print(f"  [{r['priority']:>6}] {r['action']:<22} (agent: {r['agent_id']})")
            print(f"           reason: {r['reason']}")
    else:
        print("  None")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    simulate_multi_agent_workload()
