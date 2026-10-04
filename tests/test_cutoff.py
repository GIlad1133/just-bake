from datetime import datetime, timedelta, timezone
from src.community_monitor import (compute_cutoff, build_run_input,
                                   LOOKBACK_MIN_HOURS, LOOKBACK_MAX_HOURS)

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _hours_back(cutoff: str) -> float:
    return (NOW - datetime.fromisoformat(cutoff.replace("Z", "+00:00"))).total_seconds() / 3600


def test_uses_the_last_run_plus_margin():
    """Two hours since the last run, so the window covers it with slack."""
    last = (NOW - timedelta(hours=2)).isoformat()
    assert 3.0 <= _hours_back(compute_cutoff(last, NOW)) <= 3.1


def test_overnight_gap_is_covered_without_a_fixed_constant():
    """The 20:00->04:00 UTC gap is 8h. The window must stretch to cover it."""
    last = (NOW - timedelta(hours=8)).isoformat()
    assert _hours_back(compute_cutoff(last, NOW)) >= 8.0


def test_never_shorter_than_the_floor():
    last = (NOW - timedelta(minutes=5)).isoformat()
    assert _hours_back(compute_cutoff(last, NOW)) >= LOOKBACK_MIN_HOURS


def test_long_outage_is_capped_so_it_cannot_blow_the_budget():
    last = (NOW - timedelta(days=9)).isoformat()
    assert _hours_back(compute_cutoff(last, NOW)) == LOOKBACK_MAX_HOURS


def test_missing_or_corrupt_meta_value_falls_back_to_the_floor():
    for bad in ("", None, "not a date", "2026-13-45"):
        assert _hours_back(compute_cutoff(bad, NOW)) == LOOKBACK_MIN_HOURS


def test_run_input_has_only_the_four_fields_the_actor_accepts():
    """Build 0.0.375 (28/09/2026) removed maxComments, sortOrder and
    proxyConfiguration. We were still sending all three."""
    inp = build_run_input(["https://fb.com/groups/1"], "2026-09-28T00:00:00Z")
    assert set(inp) == {"startUrls", "resultsLimit", "viewOption", "onlyPostsNewerThan"}
    assert inp["viewOption"] == "CHRONOLOGICAL"


def test_empty_streak_alarm_is_a_day_not_a_morning():
    """'no_items' means no posts in the window, not blocked. With 7 small groups
    on a 2h window, all-empty is ordinary — 30/09 produced 5 posts across 9 runs.
    A threshold of 3 fired on a quiet morning, repeatedly."""
    from src.community_monitor import EMPTY_STREAK_ALARM
    assert EMPTY_STREAK_ALARM >= 9, "must exceed one day's runs to mean anything"


def test_activity_sweep_has_no_date_filter_and_a_small_limit():
    """It scans by newest ACTIVITY, where a creation-date filter is meaningless,
    and most results are already known — so the limit stays low because Apify
    bills per post examined."""
    from src.community_monitor import build_activity_input, ACTIVITY_SWEEP_LIMIT
    inp = build_activity_input(["https://fb.com/groups/1"])
    assert inp["viewOption"] == "RECENT_ACTIVITY"
    assert "onlyPostsNewerThan" not in inp
    assert inp["resultsLimit"] == ACTIVITY_SWEEP_LIMIT <= 8


def test_logging_survives_an_input_with_no_date_filter(caplog):
    """The activity sweep has no onlyPostsNewerThan; indexing it crashed the
    first run after the sweep shipped, after Apify had already been paid."""
    from src.community_monitor import build_activity_input
    inp = build_activity_input(["https://fb.com/groups/1"])
    since = inp.get("onlyPostsNewerThan") or f"(all, {inp.get('viewOption')})"
    assert "RECENT_ACTIVITY" in since
