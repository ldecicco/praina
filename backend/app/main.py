import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.proposal_collab_service import proposal_collab_service


def _configure_logging() -> None:
    level_name = (settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(title=settings.app_name)
    if settings.cors_allowed_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.on_event("startup")
    async def _start_background_tasks() -> None:
        if not proposal_collab_service.is_available():
            logging.getLogger(__name__).warning("Proposal collaboration disabled because pycrdt is not installed.")
            app.state.proposal_collab_persist_task = None
            return
        app.state.proposal_collab_persist_task = asyncio.create_task(proposal_collab_service.persist_loop())

    @app.on_event("shutdown")
    async def _stop_background_tasks() -> None:
        task = getattr(app.state, "proposal_collab_persist_task", None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
