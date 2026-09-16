from src.community_monitor import classify_reply


def test_free_text_reply_to_an_alert_is_an_answer():
    out = classify_reply({"text": "היי מאיר, אם פתח תקווה בכיוון שלך", "reply_to": 42})
    assert out["kind"] == "answer"
    assert out["target"] == 42


def test_fact_command_is_extracted():
    out = classify_reply({"text": "/fact שמרים יבשים = שליש מהטריים", "reply_to": None})
    assert out["kind"] == "fact"
    assert out["payload"] == "שמרים יבשים = שליש מהטריים"


def test_template_command_names_its_path():
    out = classify_reply({"text": "/order תבדוק גאוגרפיה קודם", "reply_to": None})
    assert out["kind"] == "template"
    assert out["path"] == "order"
    assert out["payload"] == "תבדוק גאוגרפיה קודם"


def test_bad_marks_scoring_wrong():
    out = classify_reply({"text": "/bad", "reply_to": 42})
    assert out["kind"] == "bad"
    assert out["target"] == 42


def test_free_text_without_a_reply_target_is_ignored():
    out = classify_reply({"text": "סתם הודעה", "reply_to": None})
    assert out["kind"] == "ignored"


def test_empty_command_payload_is_ignored():
    assert classify_reply({"text": "/fact", "reply_to": None})["kind"] == "ignored"
