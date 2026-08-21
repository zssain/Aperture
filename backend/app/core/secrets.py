"""Startup-only secret resolution; resolved values remain in memory and are never logged."""

import json
import os
from typing import Protocol

from app.core.config import Settings


class SecretResolutionError(RuntimeError):
    pass


class SecretProvider(Protocol):
    def get_many(self, names: frozenset[str]) -> dict[str, str]: ...


class SecretsManagerClient(Protocol):
    def get_secret_value(self, *, SecretId: str) -> dict[str, object]: ...  # noqa: N803


class EnvironmentSecretProvider:
    def get_many(self, names: frozenset[str]) -> dict[str, str]:
        missing = sorted(name for name in names if not os.environ.get(name))
        if missing:
            raise SecretResolutionError(f"required secret variables are missing: {missing}")
        return {name: os.environ[name] for name in names}


class AWSSecretsManagerProvider:
    def __init__(
        self, region: str, secret_id: str, client: SecretsManagerClient | None = None
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("secretsmanager", region_name=region)
        self._client = client
        self._secret_id = secret_id
        self._cache: dict[str, str] | None = None

    def get_many(self, names: frozenset[str]) -> dict[str, str]:
        try:
            if self._cache is None:
                response = self._client.get_secret_value(SecretId=self._secret_id)
                parsed = json.loads(str(response["SecretString"]))
                self._cache = {str(key): str(value) for key, value in parsed.items()}
            missing = sorted(name for name in names if name not in self._cache)
            if missing:
                raise SecretResolutionError(f"managed secret is missing required keys: {missing}")
            return {name: self._cache[name] for name in names}
        except SecretResolutionError:
            raise
        except Exception as exc:
            raise SecretResolutionError("AWS Secrets Manager startup resolution failed") from exc


def secret_provider(
    settings: Settings, client: SecretsManagerClient | None = None
) -> SecretProvider:
    if settings.secret_provider == "environment":
        return EnvironmentSecretProvider()
    if settings.secret_provider == "aws_secrets_manager":
        if not settings.aws_secret_id:
            raise SecretResolutionError("AWS_SECRET_ID is required in deployed profiles")
        return AWSSecretsManagerProvider(settings.aws_region, settings.aws_secret_id, client)
    raise SecretResolutionError(f"unknown secret provider: {settings.secret_provider}")
