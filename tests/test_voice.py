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
