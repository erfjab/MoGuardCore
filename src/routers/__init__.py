from fastapi import APIRouter

from . import base, nodes, services, admins, subscriptions, guards, stats

api_router = APIRouter()

api_router.include_router(base.router)
api_router.include_router(stats.router, prefix="/api")
api_router.include_router(nodes.router, prefix="/api")
api_router.include_router(services.router, prefix="/api")
api_router.include_router(admins.router, prefix="/api")
api_router.include_router(subscriptions.router, prefix="/api")
api_router.include_router(guards.router)

__all__ = ["api_router"]
