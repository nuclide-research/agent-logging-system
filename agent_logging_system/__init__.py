"""Agent Logging System — operational discipline for multi-agent AI.

A dedicated logging/monitoring agent tracks worker agents with structured
observation, trend analysis, and anomaly detection. Inspired by industrial
OT/ICS shift-operations monitoring: watch the trend, catch degradation before
failure, keep a structured audit trail.
"""
from .observation import Observation, LATENCY_MACHINE, LATENCY_GENERATION
from .logging_agent import LoggingAgent

__all__ = ["Observation", "LoggingAgent", "LATENCY_MACHINE", "LATENCY_GENERATION"]
__version__ = "0.4.0"
