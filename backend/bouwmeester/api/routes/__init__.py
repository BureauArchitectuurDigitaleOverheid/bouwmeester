"""API router registry -- includes all sub-routers under /api."""

from fastapi import APIRouter

from bouwmeester.api.routes.activity import router as activity_router
from bouwmeester.api.routes.auth import router as auth_router
from bouwmeester.api.routes.edge_types import router as edge_types_router
from bouwmeester.api.routes.edges import router as edges_router
from bouwmeester.api.routes.graph import router as graph_router
from bouwmeester.api.routes.import_export import router as import_export_router
from bouwmeester.api.routes.nodes import router as nodes_router
from bouwmeester.api.routes.notifications import router as notifications_router
from bouwmeester.api.routes.organisatie import router as organisatie_router
from bouwmeester.api.routes.people import router as people_router
from bouwmeester.api.routes.search import router as search_router
from bouwmeester.api.routes.tasks import router as tasks_router

api_router = APIRouter()

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
api_router.include_router(notifications_router)
api_router.include_router(organisatie_router)
