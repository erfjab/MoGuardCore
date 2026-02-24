from fastapi import APIRouter
from sqlalchemy import select, func
from src.dependencies import (
    GetAsyncSession,
    GetService,
    GetCurrentOwner,
    GetCurrentAdmin,
)
from src.db import Service
from src.models.services import ServiceUpdate, ServiceCreate, ServiceResponse


router = APIRouter(prefix="/services", tags=["Services"])


@router.get("", response_model=list[ServiceResponse])
async def get_services(current: GetCurrentAdmin, db: GetAsyncSession) -> list[ServiceResponse]:
    """Get a list of all services."""
    services = current.services if not current.is_owner else await Service.get_all(db)
    counts = await Service.get_services_users_count(db, [s.id for s in services], None if current.is_owner else current.id)
    return [ServiceResponse(id=s.id, remark=s.remark, node_ids=s.node_ids, users_count=counts.get(s.id, 0)) for s in services]


@router.post("", response_model=ServiceResponse)
async def create_service(
    current: GetCurrentOwner,
    data: ServiceCreate,
    db: GetAsyncSession,
) -> ServiceResponse:
    """Create a new service."""
    return await Service.create(
        db,
        data=data,
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(current: GetCurrentAdmin, service: GetService, db: GetAsyncSession) -> ServiceResponse:
    """Get a single service by ID."""
    counts = await Service.get_services_users_count(db, [service.id], None if current.is_owner else current.id)
    return ServiceResponse(
        id=service.id, remark=service.remark, node_ids=service.node_ids, users_count=counts.get(service.id, 0)
    )


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
    current: GetCurrentOwner,
    service: GetService,
    data: ServiceUpdate,
    db: GetAsyncSession,
) -> ServiceResponse:
    """Update an existing service."""
    return await Service.update(db, service, data=data)


@router.delete("/{service_id}", response_model=dict)
async def delete_service(current: GetCurrentOwner, service: GetService, db: GetAsyncSession) -> dict:
    """Delete a service by ID."""
    await Service.remove(db, service)
    return {"message": "Service deleted successfully"}
