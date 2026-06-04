"""aimap monitor: replay an aimap JSON report through the logging system.

Usage:
    python examples/aimap_monitor.py <path-to-aimap-report.json>

Or against the bundled sample:
    python examples/aimap_monitor.py

The monitor breaks down:
  - Phase 1 (port_discovery): ports opened across the target corpus
  - Phase 2 (fingerprint):    service matches, error rate, confidence distribution
  - Phase 3 (per-enumerator): one lane per service type; catches enumerators
    with high "auth_unknown / no findings" rates (false-positive candidates)

Anomalies and recommendations come from the default rules — latency_high,
error_rate_high, queue_buildup — applied per lane. An enumerator with a high
"failed" rate (auth_unknown + no findings) will trip error_rate_high and
recommend investigate_failures. That is the signal to look at VisorCAS
false-positive signatures for that enumerator.
"""
import sys
import json
from pathlib import Path

from agent_logging_system import LoggingAgent
from agent_logging_system.adapters.aimap_adapter import AimapAdapter

_SAMPLE = Path(__file__).parent.parent / "tests" / "fixtures" / "aimap_sample.json"


def main() -> None:
    report_path = sys.argv[1] if len(sys.argv) > 1 else str(_SAMPLE)

    monitor = LoggingAgent()
    adapter = AimapAdapter(monitor)

    print(f"Ingesting: {report_path}")
    state = adapter.ingest_report(report_path)

    print("=" * 78)
    print("AIMAP REPORT  —  operational monitor view")
    print("=" * 78)

    print("\nPHASE LANES:")
    for agent_id, s in sorted(state["agents"].items()):
        total = s["total_observations"]
        errors = s["error_count"]
        err_rate = s["error_rate"]
        avg_lat = s["avg_latency"]
        print(f"\n  {agent_id}")
        print(f"    observations : {total}  (errors {errors}, {err_rate:.0%})")
        print(f"    avg latency  : {avg_lat:.0f} ms")

    print("\nANOMALIES:")
    if state["anomalies"]:
        for a in state["anomalies"]:
            print(f"  [{a['alert_level']:>8}]  {a['name']:<20}  {a['agent_id']}")
            print(f"             {a.get('recommendation', '')}")
    else:
        print("  none")

    print("\nRECOMMENDATIONS:")
    if state["recommendations"]:
        for r in state["recommendations"]:
            print(f"  [{r['priority']:>8}]  {r['action']:<24}  {r['agent_id']}")
    else:
        print("  none")

    print("\n" + "=" * 78)

    # Flag enumerators with >30% error rate as false-positive candidates.
    fp_candidates = [
        (aid, s) for aid, s in state["agents"].items()
        if aid.startswith("aimap.") and s["error_rate"] > 0.30 and s["total_observations"] >= 3
    ]
    if fp_candidates:
        print("\nFALSE-POSITIVE CANDIDATES  (>30% auth_unknown/no-findings rate):")
        for aid, s in sorted(fp_candidates, key=lambda x: -x[1]["error_rate"]):
            print(f"  {aid:<30}  {s['error_rate']:.0%} error rate  ({s['error_count']}/{s['total_observations']})")
        print("  -> review VisorCAS signatures for these enumerators")
    print()


if __name__ == "__main__":
    main()
