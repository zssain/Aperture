"""RequestContext — the authenticated identity carried into every route handler.

``role`` is the ``UserRole`` *value* as a string (e.g. "CREDIT_ANALYST"). It is kept as
a plain string so ``app.core`` does not import ``app.models`` (which would create a
core→models→db import cycle); role semantics live in the API layer.
"""

import uuid
from dataclasses import dataclass

AUDITOR_ROLE = "AUDITOR"  # mirrors app.models.enums.UserRole.AUDITOR


@dataclass(frozen=True)
class RequestContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str
    session_id: uuid.UUID
    approval_ceilings_paise: dict[str, int]

    @property
    def is_auditor(self) -> bool:
        return self.role == AUDITOR_ROLE

    def ceiling_for_role(self) -> int | None:
        """The approval ceiling (integer paise) for this role, or None if unset."""
        return self.approval_ceilings_paise.get(self.role)
