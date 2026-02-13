"""API router registry -- includes all sub-routers under /api."""

from fastapi import APIRouter

from bouwmeester.api.routes.activity import router as activity_router
from bouwmeester.api.routes.admin import router as admin_router
from bouwmeester.api.routes.auth import router as auth_router
from bouwmeester.api.routes.bijlage import router as bijlage_router
from bouwmeester.api.routes.edge_types import router as edge_types_router
from bouwmeester.api.routes.edges import router as edges_router
from bouwmeester.api.routes.graph import router as graph_router
from bouwmeester.api.routes.import_export import router as import_export_router
from bouwmeester.api.routes.llm import router as llm_router
from bouwmeester.api.routes.mentions import router as mentions_router
from bouwmeester.api.routes.nodes import router as nodes_router
from bouwmeester.api.routes.notifications import router as notifications_router
from bouwmeester.api.routes.organisatie import router as organisatie_router
from bouwmeester.api.routes.parlementair import router as parlementair_router
from bouwmeester.api.routes.people import router as people_router
from bouwmeester.api.routes.search import router as search_router
from bouwmeester.api.routes.skill import router as skill_router
from bouwmeester.api.routes.tags import router as tags_router
from bouwmeester.api.routes.tasks import router as tasks_router

api_router = APIRouter()

api_router.include_router(admin_router)
api_router.include_router(bijlage_router)
api_router.include_router(auth_router)
api_router.include_router(nodes_router)
api_router.include_router(edges_router)
api_router.include_router(edge_types_router)
api_router.include_router(tasks_router)
api_router.include_router(people_router)
api_router.include_router(activity_router)
api_router.include_router(graph_router)
api_router.include_router(search_router)
api_router.include_router(import_export_router)
api_router.include_router(llm_router)
api_router.include_router(mentions_router)
api_router.include_router(notifications_router)
api_router.include_router(organisatie_router)
api_router.include_router(skill_router)
api_router.include_router(tags_router)
api_router.include_router(parlementair_router)
