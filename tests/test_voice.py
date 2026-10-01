import json
from types import SimpleNamespace

from src.voice import (
    Voice,
    append_examples,
    build_messages,
    learned_examples,
    load_voice,
    parse_canned,
    recent_group_replies,
    select_examples,
    write_reply,
)


def _write_voice(tmp_path, examples, rules="כלל אחד", canned="## recipe\nwhen: מתכון\n\nטקסט"):
    (tmp_path / "voice.md").write_text(rules, encoding="utf-8")
    (tmp_path / "examples.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in examples), encoding="utf-8")
    (tmp_path / "canned.md").write_text(canned, encoding="utf-8")
    return tmp_path


def test_loads_rules_examples_and_canned(tmp_path):
    path = _write_voice(tmp_path, [{"situation": "tech_answer", "text": "תקין."}])
    voice = load_voice(path)
    assert voice.rules == "כלל אחד"
    assert voice.examples[0]["text"] == "תקין."
    assert voice.canned["recipe"]["text"] == "טקסט"


def test_missing_folder_returns_none(tmp_path):
    assert load_voice(tmp_path / "nope") is None


def test_empty_rules_returns_none(tmp_path):
    assert load_voice(_write_voice(tmp_path, [], rules="  ")) is None


def test_canned_keeps_text_verbatim_and_reads_when():
    md = "# title\n\n## recipe_48h\nwhen: מבקשים מתכון\n\n1000 גרם קמח\n660 גרם מים\n\n## other\nwhen: x\n\ny"
    canned = parse_canned(md)
    assert canned["recipe_48h"] == {"when": "מבקשים מתכון", "text": "1000 גרם קמח\n660 גרם מים"}
    assert canned["other"]["text"] == "y"


def test_examples_jsonl_skips_bad_lines_but_loads_good_ones(tmp_path):
    (tmp_path / "voice.md").write_text("כלל", encoding="utf-8")
    (tmp_path / "canned.md").write_text("## recipe\nwhen: x\n\nטקסט", encoding="utf-8")
    (tmp_path / "examples.jsonl").write_text(
        '{"id": "good1", "text": "a"}\nnot json at all\n[]\n{"id": "good2", "text": "b"}\n',
        encoding="utf-8")
    voice = load_voice(tmp_path)
    assert [e["id"] for e in voice.examples] == ["good1", "good2"]


def _ex(i, situation="tech_answer", audience="taboon_group", **kw):
    return {"id": f"e{i}", "situation": situation, "audience": audience, "text": f"t{i}", **kw}


def test_picks_only_matching_situation():
    examples = [_ex(1), _ex(2, situation="lead_order")]
    assert [e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", "seed")] == ["e1"]


def test_same_audience_first_then_fallback():
    examples = [_ex(1), _ex(2, audience="neighborhood"), _ex(3, audience="neighborhood")]
    picked = select_examples(examples, "tech_answer", "taboon_group", "seed", k=2)
    assert picked[0]["id"] == "e1"
    assert len(picked) == 2


def test_skips_null_text_ignored_and_not_bot_use():
    examples = [_ex(1, text=None), _ex(2, ignored=True), _ex(3, bot_use=False), _ex(4)]
    assert [e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", "s")] == ["e4"]


def test_skips_whitespace_only_text():
    examples = [_ex(1, text="   "), _ex(2)]
    assert [e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", "s")] == ["e2"]


def test_same_seed_same_pick_different_seed_varies():
    examples = [_ex(i) for i in range(12)]
    a = select_examples(examples, "tech_answer", "taboon_group", "post-A", k=4)
    assert a == select_examples(examples, "tech_answer", "taboon_group", "post-A", k=4)
    picks = {tuple(e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", f"p{i}", k=4))
             for i in range(10)}
    assert len(picks) > 1  # variety is a hard requirement


class FakeClaude:
    def __init__(self, text="טיוטה", fail=False):
        self.text, self.fail, self.calls = text, fail, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("boom")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


def _voice(examples=None, canned=None):
    return Voice(rules="כללים", examples=examples or [], canned=canned or {})


def test_examples_become_alternating_turns_then_the_post():
    ex = [_ex(1, context="שאלה 1"), _ex(2, context="")]
    system, messages = build_messages(_voice(), "הפוסט", ex, recent=[], facts=[])
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant", "user"]
    assert messages[0]["content"] == "שאלה 1"
    assert messages[1]["content"] == "t1"
    assert messages[2]["content"] == "(tech_answer)"   # empty context falls back to the situation
    assert messages[-1]["content"] == "הפוסט"
    assert "כללים" in system


def test_recent_and_facts_go_into_system():
    system, _ = build_messages(_voice(), "p", [], recent=["מוזמן אליי לפתח תקווה"], facts=["כדור 300 גרם"])
    assert "מוזמן אליי לפתח תקווה" in system
    assert "כדור 300 גרם" in system


def test_empty_post_text_becomes_placeholder():
    _, messages = build_messages(_voice(), "   ", [], recent=[], facts=[])
    assert messages[-1]["content"] == "(פוסט בלי טקסט)"


def test_canned_is_returned_verbatim_without_calling_claude():
    claude = FakeClaude()
    voice = _voice(canned={"recipe_48h": {"when": "", "text": "1000 גרם קמח"}})
    draft, warning = write_reply("p", "tech_answer", "taboon_group", "recipe_48h", voice, claude, "s")
    assert draft == "1000 גרם קמח" and warning is None
    assert claude.calls == []


def test_no_answer_situation_gives_no_draft():
    draft, warning = write_reply("p", "no_answer", "taboon_group", None, _voice(), FakeClaude(), "s")
    assert draft is None and warning is None


def test_missing_voice_warns():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None, None, FakeClaude(), "s")
    assert draft is None and "בלי קול" in warning


def test_few_examples_warns_but_still_drafts():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None, _voice([_ex(1)]), FakeClaude(), "s")
    assert draft == "טיוטה"
    assert "אין דוגמאות" in warning


def test_enough_examples_no_warning():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None,
                                 _voice([_ex(1), _ex(2), _ex(3)]), FakeClaude(), "s")
    assert draft == "טיוטה" and warning is None


def test_claude_error_warns_and_never_raises():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None,
                                 _voice([_ex(1), _ex(2)]), FakeClaude(fail=True), "s")
    assert draft is None and "נכשל" in warning


def _row(url, my_answer, **kw):
    base = {"post_url": url, "my_answer": my_answer, "post_text": "הפוסט", "group_url": "g1",
            "lead_path": "order", "situation": "", "posted_date": "", "date_fetched": "30/09/2026",
            "answer": ""}
    return {**base, **kw}


def test_new_my_answer_becomes_telegram_example():
    new = learned_examples([_row("u1", "מוזמן אליי")], known_urls=set())
    assert new == [{"id": "tg-u1", "situation": "lead_order", "audience": "taboon_group",
                    "context": "הפוסט", "text": "מוזמן אליי", "source": "telegram",
                    "date": "30/09/2026", "post_url": "u1", "bot_use": True}]


def test_known_url_and_empty_answer_are_skipped():
    rows = [_row("u1", "x"), _row("u2", "  ")]
    assert learned_examples(rows, known_urls={"u1"}) == []


def test_situation_column_wins_over_lead_path():
    new = learned_examples([_row("u1", "x", situation="where_to_buy")], known_urls=set())
    assert new[0]["situation"] == "where_to_buy"


def test_no_answer_situation_falls_back_when_gilad_answered():
    """A row left over from before an answer was written still says
    situation=no_answer; once my_answer is filled in, that label is stale."""
    new = learned_examples([_row("u1", "מוזמן אליי", situation="no_answer")], known_urls=set())
    assert new[0]["situation"] == "lead_order"


def test_same_url_twice_in_rows_is_learned_once():
    assert len(learned_examples([_row("u1", "a"), _row("u1", "a")], known_urls=set())) == 1


def test_append_writes_jsonl(tmp_path):
    path = tmp_path / "examples.jsonl"
    path.write_text('{"id": "old"}\n', encoding="utf-8")
    append_examples(path, [{"id": "new", "text": "שלום"}])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1]) == {"id": "new", "text": "שלום"}


def test_append_adds_missing_trailing_newline_first(tmp_path):
    """A file saved without a trailing newline must not get the next JSON
    object glued onto its last line."""
    (tmp_path / "voice.md").write_text("כלל", encoding="utf-8")
    (tmp_path / "canned.md").write_text("## recipe\nwhen: x\n\nטקסט", encoding="utf-8")
    path = tmp_path / "examples.jsonl"
    path.write_text('{"id": "old", "text": "a"}', encoding="utf-8")  # no trailing newline
    append_examples(path, [{"id": "new", "text": "b"}])
    voice = load_voice(tmp_path)
    assert [e["id"] for e in voice.examples] == ["old", "new"]


def test_recent_group_replies_prefers_gilads_text_and_limits():
    rows = [_row(f"u{i}", "", group_url="g1", answer=f"a{i}") for i in range(15)]
    rows.append(_row("mine", "שלי", group_url="g1", answer="בוט"))
    rows.append(_row("other", "", group_url="g2", answer="אחר"))
    recent = recent_group_replies(rows, "g1", n=10)
    assert recent[0] == "שלי"
    assert len(recent) == 10
    assert "אחר" not in recent
