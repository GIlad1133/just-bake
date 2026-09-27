from src.answer_templates import render_guidance, TEMPLATE_ROWS


def test_all_four_paths_have_a_seed_template():
    for path in ("order", "mentoring", "professional", "event"):
        assert path in TEMPLATE_ROWS


def test_guidance_includes_templates_and_facts():
    out = render_guidance(
        templates={"order": "תבדוק גאוגרפיה, אז עובדות"},
        facts=["24 שעות = 3 גרם שמרים טריים לקילו"])
    assert "order" in out
    assert "3 גרם שמרים" in out


def test_guidance_is_empty_when_sheet_tabs_are_empty():
    assert render_guidance(templates={}, facts=[]) == ""
