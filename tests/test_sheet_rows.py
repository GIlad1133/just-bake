import pytest
from src.sheet_rows import COMMUNITY_HEADERS, build_row


def test_build_row_places_values_by_header_name():
    row = build_row({"post_url": "https://fb.com/p/1", "status": "pending", "score": 7})
    assert len(row) == len(COMMUNITY_HEADERS)
    assert row[COMMUNITY_HEADERS.index("post_url")] == "https://fb.com/p/1"
    assert row[COMMUNITY_HEADERS.index("status")] == "pending"
    assert row[COMMUNITY_HEADERS.index("score")] == 7


def test_build_row_defaults_missing_columns_to_empty_string():
    row = build_row({"post_url": "u"})
    assert row[COMMUNITY_HEADERS.index("question_type")] == ""
    assert row[COMMUNITY_HEADERS.index("my_answer")] == ""


def test_build_row_rejects_unknown_column():
    with pytest.raises(KeyError, match="typo_column"):
        build_row({"typo_column": "x"})


def test_headers_contain_the_four_new_columns():
    for col in ("lead_score", "lead_path", "notified_at", "tg_message_id"):
        assert col in COMMUNITY_HEADERS


from src.community_monitor import build_noise_row


def test_noise_row_writes_noise_to_status_not_question_type():
    """Regression: 200 existing rows have question_type="noise" and empty status."""
    post = {"url": "https://fb.com/p/9", "facebookUrl": "https://fb.com/groups/1",
            "text": "טאבון למכירה", "user": {"name": "דני"}, "time": "2026-09-16"}
    row = build_noise_row(post, reason="למכירה")

    assert row[COMMUNITY_HEADERS.index("status")] == "noise"
    assert row[COMMUNITY_HEADERS.index("question_type")] == ""
    assert row[COMMUNITY_HEADERS.index("score")] == -1
    assert row[COMMUNITY_HEADERS.index("score_reason")] == "למכירה"
    assert row[COMMUNITY_HEADERS.index("lead_score")] == 0
