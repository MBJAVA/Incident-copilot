from __future__ import annotations

from incident_copilot.conversation import build_incident_context


def test_follow_up_keeps_initial_report_and_question() -> None:
    messages = [
        {"role": "user", "content": "Consumer lag is rising."},
        {"role": "assistant", "response": {
            "clarifying_questions": ["Which service and environment are affected?"]
        }},
        {"role": "user", "content": "checkout-worker in production"},
    ]

    context = build_incident_context(messages)

    assert context.startswith("Latest user update:\ncheckout-worker in production")
    assert "Initial incident report:\nConsumer lag is rising." in context
    assert "Assistant asked:\n- Which service and environment are affected?" in context
    assert "User follow-up:\ncheckout-worker in production" in context


def test_single_message_keeps_pasted_json_intact() -> None:
    alert_json = '{"alert_id":"PAY-QUEUE-LAG","service":"checkout-worker"}'

    assert build_incident_context([{"role": "user", "content": alert_json}]) == alert_json
