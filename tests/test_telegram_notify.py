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
    assert should_notify(lead_score=5, expertise_score=8, notified_at="") is False


def test_lead_six_alerts():
    """Calibration 27/09: a Sukkot event organiser needing 10 pizzas scored 6.
    She never said 'looking for a supplier', so the rubric gave 6 — but she needed
    one. The threshold follows need, not phrasing."""
    assert should_notify(lead_score=6, expertise_score=0, notified_at="") is True


def test_no_notify_when_already_notified():
    assert should_notify(lead_score=10, expertise_score=10, notified_at="16/09/2026 11:00") is False


def test_blank_notified_at_is_still_eligible():
    assert should_notify(lead_score=10, expertise_score=0, notified_at="   ") is True


from src.telegram_notify import send_alert


def test_send_returns_message_id(mocker):
    post = mocker.patch("src.telegram_notify.requests.post")
    post.return_value.status_code = 200
    post.return_value.json.return_value = {"ok": True, "result": {"message_id": 42}}

    mid = send_alert("tok", "123", "hello", "https://fb.com/p/1", "https://dash")
    assert mid == 42

    body = post.call_args.kwargs["json"]
    assert body["chat_id"] == "123"
    assert body["parse_mode"] == "HTML"
    buttons = body["reply_markup"]["inline_keyboard"][0]
    assert all("url" in b for b in buttons), "URL buttons only — no callbacks, no listener"


def test_send_failure_returns_none_and_does_not_raise(mocker):
    """A Telegram outage must never break the scrape or lose the sheet row."""
    post = mocker.patch("src.telegram_notify.requests.post")
    post.return_value.status_code = 403
    post.return_value.text = "bot can't initiate conversation"
    assert send_alert("tok", "123", "hi", "u", "d") is None


def test_send_network_error_returns_none(mocker):
    mocker.patch("src.telegram_notify.requests.post", side_effect=OSError("boom"))
    assert send_alert("tok", "123", "hi", "u", "d") is None


from src.telegram_notify import ping_healthcheck, send_plain


def test_ping_is_a_no_op_when_url_unset(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    ping_healthcheck("")
    get.assert_not_called()


def test_ping_failure_is_swallowed(mocker):
    mocker.patch("src.telegram_notify.requests.get", side_effect=OSError("down"))
    ping_healthcheck("https://hc-ping.com/abc")  # must not raise


def test_ping_appends_fail_suffix(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    ping_healthcheck("https://hc-ping.com/abc", suffix="/fail")
    assert get.call_args.args[0] == "https://hc-ping.com/abc/fail"


def test_send_plain_posts_text(mocker):
    post = mocker.patch("src.telegram_notify.requests.post")
    post.return_value.status_code = 200
    post.return_value.json.return_value = {"result": {"message_id": 7}}
    assert send_plain("tok", "1", "סיכום יומי") == 7


from src.telegram_notify import fetch_replies


def _update(uid, from_id, text, reply_to=None):
    msg = {"message_id": uid + 100, "from": {"id": from_id}, "text": text}
    if reply_to:
        msg["reply_to_message"] = {"message_id": reply_to}
    return {"update_id": uid, "message": msg}


def test_only_the_owner_chat_is_accepted(mocker):
    """The bot username is public — anyone can press Start and send messages."""
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _update(1, 314244953, "מהבעלים"),
        _update(2, 999999999, "/fact גבינה חינם"),
    ]}
    replies, next_offset = fetch_replies("tok", "314244953", 0)
    assert len(replies) == 1
    assert replies[0]["text"] == "מהבעלים"
    assert next_offset == 3, "offset must advance past ignored updates too"


def test_offset_unchanged_when_queue_is_empty(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": []}
    replies, next_offset = fetch_replies("tok", "1", 57)
    assert replies == []
    assert next_offset == 57


def test_reply_target_is_extracted(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _update(5, 314244953, "התשובה שלי", reply_to=42)]}
    replies, _ = fetch_replies("tok", "314244953", 0)
    assert replies[0]["reply_to"] == 42


def test_network_failure_returns_empty_and_keeps_offset(mocker):
    mocker.patch("src.telegram_notify.requests.get", side_effect=OSError("down"))
    replies, next_offset = fetch_replies("tok", "1", 12)
    assert replies == []
    assert next_offset == 12


def _reaction(uid, user_id, emoji, on_message):
    return {"update_id": uid, "message_reaction": {
        "message_id": on_message, "user": {"id": user_id},
        "new_reaction": [{"type": "emoji", "emoji": emoji}]}}


def test_reactions_are_returned_with_their_target(mocker):
    """Reactions only arrive when the bot is an admin in the chat, which is why
    alerts go to a group rather than a 1:1 chat."""
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _reaction(1, 314244953, "\U0001F44D", 42)]}
    events, _ = fetch_replies("tok", "314244953", 0)
    assert events[0]["reaction"] == "\U0001F44D"
    assert events[0]["reply_to"] == 42


def test_reactions_from_other_people_are_ignored(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _reaction(1, 999999999, "\U0001F44D", 42)]}
    events, next_offset = fetch_replies("tok", "314244953", 0)
    assert events == []
    assert next_offset == 2


def test_reactions_are_requested_explicitly(mocker):
    """Telegram does not send message_reaction unless allowed_updates names it."""
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": []}
    fetch_replies("tok", "1", 0)
    assert "message_reaction" in get.call_args.kwargs["params"]["allowed_updates"]


def test_auth_is_on_the_sender_not_the_chat(mocker):
    """In a group the destination chat id is negative and is NOT the sender id."""
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _update(1, 314244953, "from Gilad in the group")]}
    events, _ = fetch_replies("tok", "314244953", 0)   # owner id, not -5305503048
    assert len(events) == 1


def test_expertise_eight_alerts():
    """Calibration 04/10: 'יש לי בצקים במקפיא כמה זמן לפני צריכים להוציא' scored
    expertise 8 — a customer holding his product, asking the question he knows
    best — and missed a threshold of 9 by one point. Historically 8 is 84 posts
    per 86 days against 17 at 9, so this is the band that carries the volume."""
    assert should_notify(lead_score=0, expertise_score=8, notified_at="") is True


def test_expertise_seven_still_quiet():
    assert should_notify(lead_score=0, expertise_score=7, notified_at="") is False
