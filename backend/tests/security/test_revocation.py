from app.models.enums import ApplicationStatus, SourceConnectionStatus


def test_revocation_terminal_states_are_explicit() -> None:
    assert SourceConnectionStatus.REVOKED.value == "REVOKED"
    assert ApplicationStatus.CLOSED.value == "CLOSED"
