from backend.util import RateLimiter, client_ip, is_quiet_hours


def test_client_ip_ignores_forwarded_for_by_default():
    assert client_ip("10.0.0.5", "203.0.113.9", "") == "10.0.0.5"
    assert client_ip("10.0.0.5", "203.0.113.9", "  ") == "10.0.0.5"


def test_client_ip_trusts_forwarded_for_for_allowlisted_peer():
    assert client_ip("10.0.0.5", "203.0.113.9, 10.0.0.5", "10.0.0.5") == "203.0.113.9"


def test_client_ip_trusts_forwarded_for_for_cidr_peer():
    assert client_ip("10.0.1.77", "203.0.113.9", "10.0.0.0/8,192.168.0.0/16") == "203.0.113.9"


def test_client_ip_ignores_spoofed_header_from_untrusted_peer():
    assert client_ip("198.51.100.7", "1.2.3.4", "10.0.0.0/8") == "198.51.100.7"


def test_client_ip_wildcard_trusts_every_peer():
    assert client_ip("198.51.100.7", "1.2.3.4", "*") == "1.2.3.4"


def test_client_ip_falls_back_on_missing_or_bad_values():
    assert client_ip("10.0.0.5", None, "10.0.0.0/8") == "10.0.0.5"
    assert client_ip("10.0.0.5", "not-an-ip", "10.0.0.0/8") == "10.0.0.5"
    assert client_ip("", "", "") == "unknown"


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