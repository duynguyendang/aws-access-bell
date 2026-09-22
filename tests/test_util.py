from backend.util import RateLimiter, is_quiet_hours


def test_rate_limiter_prunes_when_many_keys():
    limiter = RateLimiter(limit=1, window_seconds=60, max_keys=2)
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert limiter.allow("a") is False
    assert limiter.allow("c")
    assert len(limiter._hits) <= 3


def test_is_quiet_hours_wraps_midnight():
    assert is_quiet_hours("2026-09-15T23:30:00Z", "22:00", "07:00")
    assert is_quiet_hours("2026-09-15T02:00:00Z", "22:00", "07:00")
    assert not is_quiet_hours("2026-09-15T12:00:00Z", "22:00", "07:00")
    assert not is_quiet_hours("2026-09-15T23:30:00Z", "", "")
    assert not is_quiet_hours("2026-09-15T23:30:00Z", "bad", "end")