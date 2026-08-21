from app.services.rate_limit import LIMITS


def test_all_required_rate_limit_policies() -> None:
    assert (LIMITS["login"].limit, LIMITS["login"].window_seconds) == (5, 60)
    assert (LIMITS["decide"].limit, LIMITS["decide"].window_seconds) == (30, 60)
    assert (LIMITS["upload"].limit, LIMITS["upload"].window_seconds) == (10, 60)
    assert (LIMITS["recourse"].limit, LIMITS["recourse"].window_seconds) == (20, 3600)
    assert (LIMITS["events"].limit, LIMITS["events"].window_seconds) == (1000, 60)
    assert (LIMITS["policy_simulate"].limit, LIMITS["policy_simulate"].window_seconds) == (10, 3600)
    assert (LIMITS["notice_render"].limit, LIMITS["notice_render"].window_seconds) == (60, 3600)
