"""Tenant-scoped repository base.

The tenant filter is applied by the only query builder (``_scoped_select``), which is
private. No public method returns an unscoped query, so a caller cannot accidentally
read across tenants through this interface. Writes are scoped too: ``add`` stamps the
repository's tenant id onto the entity.
"""

import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import TenantScopedBase

ModelT = TypeVar("ModelT", bound=TenantScopedBase)


class TenantScopedRepository(Generic[ModelT]):
    """Base class for repositories over a single tenant-scoped model."""

    #: Concrete subclasses set the mapped model they operate on.
    model: type[ModelT]

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> uuid.UUID:
        return self._tenant_id

    def _scoped_select(self) -> Select[tuple[ModelT]]:
        """The single query entry point — always filtered to this tenant."""
        return select(self.model).where(self.model.tenant_id == self._tenant_id)

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        stmt = self._scoped_select().where(self.model.id == entity_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        stmt = self._scoped_select().limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    def add(self, entity: ModelT) -> ModelT:
        """Persist a new entity, structurally stamping the tenant scope onto it."""
        entity.tenant_id = self._tenant_id
        self._session.add(entity)
        return entity
