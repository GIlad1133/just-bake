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
