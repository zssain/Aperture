import pytest
from app.core.config import Settings
from app.core.secrets import SecretResolutionError, secret_provider


class FailingClient:
    def get_secret_value(self, *, SecretId: str) -> dict[str, object]:  # noqa: N803
        del SecretId
        raise OSError("unreachable contains-sensitive-provider-message")


def test_deployed_secret_manager_failure_is_loud_without_env_fallback() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        frontend_origin="http://localhost:5173",
        environment="production",
        secret_provider="aws_secrets_manager",
        aws_secret_id="aperture/prod",
    )
    provider = secret_provider(settings, FailingClient())
    with pytest.raises(SecretResolutionError, match="startup resolution failed") as failure:
        provider.get_many(frozenset({"DATABASE_URL"}))
    assert "sensitive" not in str(failure.value)
