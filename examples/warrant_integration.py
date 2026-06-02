"""Warrant integration demo.

Shows the WarrantAdapter logging the three Warrant action shapes — reasoning,
code generation, citation check — and reading back the monitor's view.

Run: python examples/warrant_integration.py
"""
from agent_logging_system import LoggingAgent
from agent_logging_system.adapters.warrant_adapter import WarrantAdapter


def main() -> None:
    logging_agent = LoggingAgent()
    warrant = WarrantAdapter(logging_agent)

    warrant.log_reasoning_step(
        agent_id="warrant-001",
        source="python_best_practices.md",
        question="What are best practices for error handling?",
        answer="Use specific exceptions, provide context, log errors.",
        confidence=0.92,
        latency_ms=1200,
    )
    warrant.log_code_generation(
        agent_id="warrant-001",
        prompt="Write a function to validate email addresses",
        code="import re\ndef validate_email(e): return re.match(r'^[^@]+@[^@]+\\.[^@]+$', e)",
        syntax_valid=True,
        latency_ms=800,
    )
    warrant.log_citation_check(
        agent_id="warrant-001",
        citation="Best practices recommend specific exceptions",
        source="python_best_practices.md",
        valid=True,
        latency_ms=150,
    )

    state = warrant.get_state()
    print("System State")
    print(f"  Agents:          {list(state['agents'].keys())}")
    print(f"  Anomalies:       {state['anomalies']}")
    print(f"  Recommendations: {state['recommendations']}")

    s = logging_agent.get_agent_state("warrant-001")
    print("\nWarrant Agent State")
    print(f"  Status:       {s['status']}")
    print(f"  Avg Latency:  {s['avg_latency']:.1f}ms")
    print(f"  Observations: {s['total_observations']}")
    print(f"  Error Count:  {s['error_count']}")


if __name__ == "__main__":
    main()
