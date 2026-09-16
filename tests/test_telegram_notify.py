from src.telegram_notify import format_alert, should_notify


def test_alert_shows_path_and_both_scores():
    text = format_alert(
        post={"text": "מחפש 60 כדורי בצק", "url": "https://fb.com/p/1"},
        result={"lead_score": 10, "lead_path": "order", "score": 3, "answer": "היי מאיר"},
        group_name="הטאבון הביתי")
    assert "10" in text
    assert "הזמנה" in text
    assert "הטאבון הביתי" in text


def test_answer_is_wrapped_in_code_for_tap_to_copy():
    text = format_alert(
        post={"text": "x", "url": "u"},
        result={"lead_score": 9, "lead_path": "order", "score": 4, "answer": "התשובה"},
        group_name="g")
    assert "<code>התשובה</code>" in text


def test_html_special_characters_are_escaped():
    """An unescaped < or & in a post makes Telegram reject the whole message."""
    text = format_alert(
        post={"text": "עלות < 100 & עוד", "url": "u"},
        result={"lead_score": 8, "lead_path": "event", "score": 5, "answer": "a & b"},
        group_name="g")
    assert "&lt;" in text and "&amp;" in text
    assert "< 100 &" not in text


def test_long_post_is_truncated():
    text = format_alert(
        post={"text": "א" * 900, "url": "u"},
        result={"lead_score": 8, "lead_path": "order", "score": 5, "answer": "a"},
        group_name="g")
    assert len(text) < 1200


def test_missing_answer_does_not_crash():
    text = format_alert(
        post={"text": "x", "url": "u"},
        result={"lead_score": 7, "lead_path": "none", "score": 2, "answer": None},
        group_name="g")
    assert isinstance(text, str)


def test_notify_on_high_lead():
    assert should_notify(lead_score=7, expertise_score=1, notified_at="") is True


def test_notify_on_high_expertise():
    assert should_notify(lead_score=0, expertise_score=9, notified_at="") is True


def test_no_notify_below_both_thresholds():
    assert should_notify(lead_score=6, expertise_score=8, notified_at="") is False


def test_no_notify_when_already_notified():
    assert should_notify(lead_score=10, expertise_score=10, notified_at="16/09/2026 11:00") is False


def test_blank_notified_at_is_still_eligible():
    assert should_notify(lead_score=10, expertise_score=0, notified_at="   ") is True
