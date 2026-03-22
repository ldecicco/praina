from fastapi import APIRouter

from app.api.v1.routes.action_items import router as action_items_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.coherence import router as coherence_router
from app.api.v1.routes.courses import router as courses_router
from app.api.v1.routes.calendar_integrations import router as calendar_integrations_router
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.documents import router as documents_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.meetings import router as meetings_router
from app.api.v1.routes.notifications import router as notifications_router
from app.api.v1.routes.project_chat import router as project_chat_router
from app.api.v1.routes.project_inbox import router as project_inbox_router
from app.api.v1.routes.proposal_collab import router as proposal_collab_router
from app.api.v1.routes.proposals import router as proposals_router
from app.api.v1.routes.my_work import router as my_work_router
from app.api.v1.routes.reports import router as reports_router
from app.api.v1.routes.reviews import router as reviews_router
from app.api.v1.routes.projects import router as projects_router
from app.api.v1.routes.research import router as research_router
from app.api.v1.routes.search import router as search_router
from app.api.v1.routes.todos import router as todos_router
from app.api.v1.routes.teaching import router as teaching_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(courses_router, tags=["courses"])
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(meetings_router, prefix="/projects", tags=["meetings"])
api_router.include_router(action_items_router, prefix="/projects", tags=["meeting-action-items"])
api_router.include_router(calendar_integrations_router, tags=["calendar-integrations"])
api_router.include_router(project_chat_router, prefix="/projects", tags=["project-chat"])
api_router.include_router(project_inbox_router, prefix="/projects", tags=["project-inbox"])
api_router.include_router(proposal_collab_router, tags=["proposal-collab"])
api_router.include_router(proposals_router, tags=["proposals"])
api_router.include_router(chat_router, prefix="/projects", tags=["chat"])
api_router.include_router(reviews_router, prefix="/projects", tags=["reviews"])
api_router.include_router(documents_router, prefix="/projects", tags=["documents"])
api_router.include_router(coherence_router, prefix="/projects", tags=["coherence"])
api_router.include_router(reports_router, prefix="/projects", tags=["reports"])
api_router.include_router(dashboard_router, prefix="/projects", tags=["dashboard"])
api_router.include_router(notifications_router, tags=["notifications"])
api_router.include_router(todos_router, prefix="/projects", tags=["todos"])
api_router.include_router(research_router, prefix="/projects", tags=["research"])
api_router.include_router(teaching_router, prefix="/projects", tags=["teaching"])
api_router.include_router(search_router, prefix="/projects", tags=["search"])
api_router.include_router(my_work_router, tags=["my-work"])
