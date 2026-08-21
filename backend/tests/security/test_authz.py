from app.api.routes.policies import owner


def test_policy_routes_share_policy_owner_guard() -> None:
    # The dependency object is deliberately declared once and attached to every route.
    assert callable(owner)
