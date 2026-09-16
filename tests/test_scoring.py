import pytest
from src.community_monitor import parse_score_response


def test_parses_two_axis_response():
    raw = ('{"lead_score": 10, "lead_path": "order", "lead_reason": "רוצה לקנות 60 כדורים",'
           ' "score": 3, "score_reason": "בקשת רכש", "answer": "היי מאיר",'
           ' "tags": ["בצק"], "question_type": "where_to_buy", "post_type": "question",'
           ' "image_description": null}')
    out = parse_score_response(raw)
    assert out["lead_score"] == 10
    assert out["lead_path"] == "order"
    assert out["score"] == 3


def test_strips_markdown_fences():
    raw = '```json\n{"lead_score": 0, "lead_path": "none", "score": 2}\n```'
    out = parse_score_response(raw)
    assert out["lead_score"] == 0
    assert out["lead_path"] == "none"


def test_malformed_response_returns_safe_defaults():
    out = parse_score_response("not json at all")
    assert out["lead_score"] == 0
    assert out["score"] == 0
    assert out["lead_path"] == "none"
    assert out["answer"] is None


def test_out_of_range_scores_are_clamped():
    out = parse_score_response('{"lead_score": 99, "score": -5, "lead_path": "order"}')
    assert out["lead_score"] == 10
    assert out["score"] == 0


def test_unknown_lead_path_falls_back_to_none():
    out = parse_score_response('{"lead_score": 8, "lead_path": "banana", "score": 4}')
    assert out["lead_path"] == "none"
