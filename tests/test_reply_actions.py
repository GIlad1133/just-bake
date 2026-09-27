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


def test_free_text_without_a_reply_target_is_unclear_not_dropped():
    """Was 'ignored' and silently discarded until 27/09. Now it earns an ack."""
    out = classify_reply({"text": "סתם הודעה", "reply_to": None})
    assert out["kind"] == "unclear"


def test_empty_command_payload_is_unclear_not_dropped():
    assert classify_reply({"text": "/fact", "reply_to": None})["kind"] == "unclear"


def test_thumbs_up_is_positive_feedback():
    out = classify_reply({"reaction": "\U0001F44D", "reply_to": 42})
    assert out["kind"] == "good" and out["target"] == 42


def test_thumbs_down_is_negative_feedback():
    assert classify_reply({"reaction": "\U0001F44E", "reply_to": 42})["kind"] == "bad"


def test_skip_does_not_pollute_the_training_set():
    """'אני לא מגיב לזה כרגע' was stored as a professional answer on 27/09."""
    assert classify_reply({"text": "/skip", "reply_to": 42})["kind"] == "skip"


def test_nothing_is_ever_silently_dropped():
    """Three messages were lost on 27/09 because unrecognised input was discarded
    while the offset advanced past it. Every branch must be actionable."""
    for event in ({"text": "just typing", "reply_to": None},
                  {"text": "/whatever", "reply_to": None},
                  {"text": "", "reply_to": None},
                  {"text": "/fact", "reply_to": None},
                  {"reaction": "\U0001F914", "reply_to": 42}):
        out = classify_reply(event)
        assert out["kind"] == "unclear", out
        assert out.get("why"), "an unclear verdict must say why, so the ack can explain"
