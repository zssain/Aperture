"""Case-intake routes used by the ingest screen.

The connect route creates a durable case and queues server-side work. The document
route parses the hostile upload first, so a malformed file cannot create an applicant,
application, consent, or snapshot.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.context import RequestContext
from app.db.session import get_session
from app.jobs.runner import enqueue
from app.models.applicant import Applicant
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobType, SourceType, UserRole
from app.models.source import SourceSnapshot
from app.schemas.application import (
    ApplicationFields,
    CaseIntakeOut,
    ConnectCaseRequest,
)
from app.schemas.source import IngestionResultOut
from app.services.audit.ledger import append
from app.services.consent.service import create_consent
from app.services.ingestion.service import ingest_document
from app.services.rate_limit import PostgresRateLimitExceededError, hit_many
from app.services.sources.document import (
    DocumentTooLargeError,
    RowCapExceededError,
    SchemaError,
    UnsupportedDocumentError,
)
from app.services.sources.upload_security import parse_document_securely

router = APIRouter(prefix="/applications", tags=["applications"])

_CASE_WRITER = require_role(UserRole.CREDIT_ANALYST, UserRole.CREDIT_POLICY_OWNER)


def _initial_progress(
    *, consent_count: int, ingestion: IngestionResultOut | None
) -> dict[str, object]:
    ingested = ingestion.ingested if ingestion is not None else 0
    deduplicated = ingestion.deduplicated if ingestion is not None else 0
    source_complete = ingestion is not None
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "stages": [
            {"key": "consent", "label": "Consent", "status": "complete", "count": consent_count},
            {
                "key": "fetching",
                "label": "Fetching evidence",
                "status": "complete" if source_complete else "pending",
                "count": ingested + deduplicated if source_complete else None,
            },
            {
                "key": "normalising",
                "label": "Normalising",
                "status": "complete" if source_complete else "pending",
                "count": ingested if source_complete else None,
            },
            {"key": "features", "label": "Computing features", "status": "pending"},
            {"key": "assessing", "label": "Assessing", "status": "pending"},
            {"key": "decided", "label": "Decided", "status": "pending"},
        ],
        "sources": [],
    }


async def _create_records(
    session: AsyncSession,
    context: RequestContext,
    fields: ApplicationFields,
    *,
    application_status: ApplicationStatus,
) -> tuple[Applicant, Application]:
    applicant = Applicant(
        tenant_id=context.tenant_id,
        external_ref=fields.external_ref,
        display_name=fields.display_name,
    )
    session.add(applicant)
    await session.flush()
    application = Application(
        tenant_id=context.tenant_id,
        applicant_id=applicant.id,
        status=application_status,
        product=fields.product,
        declared_income_paise=fields.declared_income_paise,
        occupation=fields.occupation,
        requested_amount_paise=fields.requested_amount_paise,
        requested_tenor_months=fields.requested_tenor_months,
    )
    session.add(application)
    await session.flush()
    await append(
        session,
        context,
        event_type="APPLICATION_CREATED",
        subject_type="application",
        subject_id=application.id,
        payload={
            "application_id": str(application.id),
            "applicant_id": str(applicant.id),
            "external_ref": applicant.external_ref,
            "requested_amount_paise": application.requested_amount_paise,
            "requested_tenor_months": application.requested_tenor_months,
            "status": application.status.value,
        },
    )
    return applicant, application


def _conflict(exc: IntegrityError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "EXTERNAL_REF_EXISTS", "message": "External reference already exists."},
    )


@router.post("", response_model=CaseIntakeOut, status_code=status.HTTP_201_CREATED)
async def create_connect_case(
    payload: ConnectCaseRequest,
    context: RequestContext = Depends(_CASE_WRITER),
    session: AsyncSession = Depends(get_session),
) -> CaseIntakeOut:
    application_status = (
        ApplicationStatus.PROCESSING
        if payload.consent_granted
        else ApplicationStatus.AWAITING_CONSENT
    )
    try:
        applicant, application = await _create_records(
            session, context, payload, application_status=application_status
        )
        if not payload.consent_granted:
            await session.commit()
            return CaseIntakeOut(
                status="AWAITING_CONSENT",
                application_id=application.id,
                applicant_id=applicant.id,
                application_status=application.status,
            )

        expires_at = payload.expires_at or datetime.now(UTC) + timedelta(days=90)
        _consent, connections = await create_consent(
            session,
            context,
            applicant_id=applicant.id,
            purpose=payload.purpose,
            scope=payload.scope,
            expires_at=expires_at,
        )
        job = await enqueue(
            session,
            tenant_id=context.tenant_id,
            handler="ingest_pipeline",
            job_type=JobType.INGEST,
            payload={
                "application_id": str(application.id),
                "applicant_id": str(applicant.id),
                "connection_ids": [str(connection.id) for connection in connections],
                "failure_modes": {
                    source.value: mode for source, mode in payload.failure_modes.items()
                },
                "as_of": datetime.now(UTC).isoformat(),
                "idempotency_key": f"intake:{application.id}",
                "user_id": str(context.user_id),
            },
        )
        job.result = _initial_progress(consent_count=len(connections), ingestion=None)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict(exc) from exc

    return CaseIntakeOut(
        status="QUEUED",
        application_id=application.id,
        applicant_id=applicant.id,
        application_status=application.status,
        job_id=job.id,
    )


async def _existing_upload(
    session: AsyncSession, tenant_id: uuid.UUID, content_hash: str
) -> Application | None:
    existing: Application | None = await session.scalar(
        select(Application)
        .join(SourceSnapshot, SourceSnapshot.applicant_id == Application.applicant_id)
        .where(
            Application.tenant_id == tenant_id,
            SourceSnapshot.tenant_id == tenant_id,
            SourceSnapshot.content_hash == content_hash,
        )
        .order_by(Application.created_at.asc())
        .limit(1)
    )
    return existing


def _document_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DocumentTooLargeError):
        return HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "FILE_TOO_LARGE", "message": str(exc)},
        )
    if isinstance(exc, RowCapExceededError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "ROW_CAP_EXCEEDED", "message": str(exc), "limit": exc.limit},
        )
    if isinstance(exc, SchemaError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "SCHEMA_ERROR",
                "message": str(exc),
                "expected_columns": exc.expected_columns,
            },
        )
    return HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail={"code": "UNSUPPORTED", "message": str(exc)},
    )


@router.post("/documents", response_model=CaseIntakeOut, status_code=status.HTTP_201_CREATED)
async def create_document_case(
    request: Request,
    display_name: str = Form(...),
    external_ref: str = Form(...),
    declared_income_paise: int = Form(...),
    occupation: str = Form(...),
    requested_amount_paise: int = Form(...),
    requested_tenor_months: int = Form(...),
    product: str = Form(default="PERSONAL_LOAN"),
    file: UploadFile = File(...),
    context: RequestContext = Depends(_CASE_WRITER),
    session: AsyncSession = Depends(get_session),
) -> CaseIntakeOut:
    try:
        await hit_many(
            session,
            tenant_id=context.tenant_id,
            bucket="upload",
            principals=(
                f"user:{context.user_id}",
                f"ip:{request.client.host if request.client else 'unknown'}",
            ),
        )
    except PostgresRateLimitExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Upload rate limit reached"},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    try:
        fields = ApplicationFields(
            display_name=display_name,
            external_ref=external_ref,
            declared_income_paise=declared_income_paise,
            occupation=occupation,
            requested_amount_paise=requested_amount_paise,
            requested_tenor_months=requested_tenor_months,
            product=product,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    data = await file.read()
    filename = file.filename or "upload"

    # Parse before creating any row. ingest_document parses again after consent is
    # persisted; the second parse is deterministic and cannot introduce new side effects.
    try:
        parse_document_securely(data, filename)
    except (
        DocumentTooLargeError,
        RowCapExceededError,
        SchemaError,
        UnsupportedDocumentError,
    ) as exc:
        raise _document_error(exc) from exc

    existing = await _existing_upload(session, context.tenant_id, hashlib.sha256(data).hexdigest())
    if existing is not None:
        return CaseIntakeOut(
            status="ALREADY_INGESTED",
            already_ingested=True,
            application_id=existing.id,
            applicant_id=existing.applicant_id,
            application_status=existing.status,
            existing_case_url=f"/cases/{existing.id}",
        )

    try:
        applicant, application = await _create_records(
            session, context, fields, application_status=ApplicationStatus.PROCESSING
        )
        _consent, connections = await create_consent(
            session,
            context,
            applicant_id=applicant.id,
            purpose="Credit underwriting from an uploaded statement",
            scope=[SourceType.BANK],
            expires_at=datetime.now(UTC) + timedelta(days=90),
        )
        ingestion_result = await ingest_document(session, connections[0], data, filename)
        ingestion = IngestionResultOut.from_result(ingestion_result)
        job = await enqueue(
            session,
            tenant_id=context.tenant_id,
            handler="ingest_pipeline",
            job_type=JobType.INGEST,
            payload={
                "application_id": str(application.id),
                "applicant_id": str(applicant.id),
                "connection_ids": [],
                "as_of": datetime.now(UTC).isoformat(),
                "idempotency_key": f"intake:{application.id}",
                "user_id": str(context.user_id),
                "document_ingestion": ingestion.model_dump(mode="json"),
            },
        )
        job.result = _initial_progress(consent_count=1, ingestion=ingestion)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict(exc) from exc

    return CaseIntakeOut(
        status="QUEUED",
        application_id=application.id,
        applicant_id=applicant.id,
        application_status=application.status,
        job_id=job.id,
        ingestion=ingestion,
    )
