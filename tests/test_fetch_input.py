from datetime import datetime, timedelta, timezone
from src.community_monitor import build_run_input, LOOKBACK_HOURS


def test_run_input_includes_iso_cutoff_not_relative_string():
    inp = build_run_input(["https://fb.com/groups/1"])
    cutoff = inp["onlyPostsNewerThan"]
    assert cutoff.endswith("Z"), "Apify needs an ISO timestamp, not a relative string"
    parsed = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    expected = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    assert abs((parsed - expected).total_seconds()) < 120


def test_lookback_exceeds_cadence_so_a_delayed_run_loses_nothing():
    assert LOOKBACK_HOURS >= 9, "must cover the 8h overnight gap between the 20:00 and 04:00 UTC runs"


def test_run_input_maps_every_group():
    urls = ["https://fb.com/groups/1", "https://fb.com/groups/2"]
    assert build_run_input(urls)["startUrls"] == [{"url": u} for u in urls]
