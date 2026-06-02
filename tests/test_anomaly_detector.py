from agent_logging_system.anomaly_detector import AnomalyDetector, AnomalyRule
from agent_logging_system.recommendations import RecommendationEngine


def test_anomaly_detector_latency_threshold():
    """A latency rule trips when the state exceeds its threshold."""
    detector = AnomalyDetector()
    detector.add_rule(AnomalyRule(
        name="latency_high",
        check=lambda s: s["avg_latency"] > 5000,
        alert_level="HIGH",
        recommendation="Increase timeout or throttle input rate",
    ))

    anomalies = detector.detect({"agent_id": "worker-001", "avg_latency": 8000, "error_rate": 0.0})
    assert len(anomalies) == 1
    assert anomalies[0]["name"] == "latency_high"
    assert anomalies[0]["alert_level"] == "HIGH"


def test_anomaly_detector_error_rate():
    """An error-rate rule trips on an elevated rate."""
    detector = AnomalyDetector()
    detector.add_rule(AnomalyRule(
        name="error_rate_high",
        check=lambda s: s["error_rate"] > 0.1,
        alert_level="MEDIUM",
        recommendation="Investigate failures",
    ))

    anomalies = detector.detect({"agent_id": "worker-002", "avg_latency": 1000, "error_rate": 0.15})
    assert len(anomalies) == 1
    assert anomalies[0]["name"] == "error_rate_high"


def test_anomaly_detector_multiple_rules():
    """Independent rules trip independently on the same state."""
    detector = AnomalyDetector()
    detector.add_rule(AnomalyRule("latency_high", lambda s: s["avg_latency"] > 5000, "HIGH", "Increase timeout"))
    detector.add_rule(AnomalyRule("error_rate_high", lambda s: s["error_rate"] > 0.1, "MEDIUM", "Investigate"))

    anomalies = detector.detect({"agent_id": "worker-003", "avg_latency": 8000, "error_rate": 0.15})
    assert len(anomalies) == 2


def test_anomaly_detector_skips_raising_rule():
    """A rule that raises on a malformed state is skipped, not fatal."""
    detector = AnomalyDetector()
    detector.add_rule(AnomalyRule("needs_key", lambda s: s["missing"] > 1, "HIGH", "n/a"))
    detector.add_rule(AnomalyRule("always", lambda s: True, "LOW", "ok"))

    anomalies = detector.detect({"agent_id": "worker-004"})
    assert len(anomalies) == 1
    assert anomalies[0]["name"] == "always"


def test_recommendation_engine():
    """Known anomalies map to concrete, actionable recommendations."""
    engine = RecommendationEngine()
    anomalies = [
        {"name": "latency_high", "alert_level": "HIGH", "recommendation": "Throttle input", "agent_id": "w1"},
        {"name": "error_rate_high", "alert_level": "MEDIUM", "recommendation": "Investigate", "agent_id": "w2"},
    ]
    recs = engine.generate(anomalies)
    assert len(recs) == 2
    assert recs[0]["action"] == "throttle_input"
    assert recs[1]["action"] == "investigate_failures"


def test_recommendation_engine_ignores_unknown():
    """An anomaly with no mapped action yields no recommendation."""
    engine = RecommendationEngine()
    recs = engine.generate([{"name": "queue_buildup", "alert_level": "LOW", "agent_id": "w3"}])
    assert recs == []
