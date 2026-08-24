"""FastAPI application factory.

Wires structured logging, CORS restricted to the configured frontend origin, a
correlation-id middleware, and the v1 API router mounted under ``/api/v1``.
"""

import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api.router import router
from app.api.routes.applications import router as applications_router
from app.api.routes.assistant import router as assistant_router
from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.cases import router as cases_router
from app.api.routes.consents import router as consents_router
from app.api.routes.decisions import router as decisions_router
from app.api.routes.demo import router as demo_router
from app.api.routes.documents import router as documents_router
from app.api.routes.events import router as events_router
from app.api.routes.gdpr import router as gdpr_router
from app.api.routes.health_metrics import router as health_metrics_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.outcomes import router as outcomes_router
from app.api.routes.policies import router as policies_router
from app.api.routes.queue import router as queue_router
from app.api.routes.recourse import router as recourse_router
from app.api.routes.reviews import router as reviews_router
from app.api.routes.sources import router as sources_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.providers.registry import configured_registry
from app.middleware.csrf import CSRFMiddleware
from app.middleware.security import SecurityHeadersMiddleware

CORRELATION_ID_HEADER = "X-Correlation-ID"

logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind an ``X-Correlation-ID`` to the log context and echo it in the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        clear_contextvars()
        bind_contextvars(correlation_id=correlation_id)
        logger.info(
            "request_received",
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=settings.version)
    if settings.llm_notices_enabled or settings.embedding_provider != "noop":
        # Fail deployment startup, rather than the first applicant request, when a
        # configured provider or its credentials are unavailable.
        app.state.providers = configured_registry()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(applications_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(consents_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(decisions_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(demo_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(gdpr_router, prefix="/api/v1")
    app.include_router(health_metrics_router, prefix="/api/v1")
    app.include_router(outcomes_router, prefix="/api/v1")
    app.include_router(queue_router, prefix="/api/v1")
    app.include_router(policies_router, prefix="/api/v1")
    app.include_router(cases_router, prefix="/api/v1")
    app.include_router(assistant_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(recourse_router, prefix="/api/v1")

    return app


app = create_app()
