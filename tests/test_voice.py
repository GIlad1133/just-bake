import json

from src.voice import load_voice, parse_canned


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


from src.voice import select_examples


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


def test_same_seed_same_pick_different_seed_varies():
    examples = [_ex(i) for i in range(12)]
    a = select_examples(examples, "tech_answer", "taboon_group", "post-A", k=4)
    assert a == select_examples(examples, "tech_answer", "taboon_group", "post-A", k=4)
    picks = {tuple(e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", f"p{i}", k=4))
             for i in range(10)}
    assert len(picks) > 1  # variety is a hard requirement


from types import SimpleNamespace

from src.voice import Voice, build_messages, write_reply


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
