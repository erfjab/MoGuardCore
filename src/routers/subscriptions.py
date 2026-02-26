import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from src.db import Subscription, Admin
from src.guard_node import GuardNodeManager
from src.utils.notif import NotificationService
from src.models.subscriptions import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
    SubscriptionUsageLogsResponse,
    SubscriptionStatsResponse,
)
from src.dependencies import (
    GetAsyncSession,
    GetSubscription,
    GetSubscriptions,
    GetCurrentAdmin,
    CheckSubCreateAccess,
    CheckSubRemoveAccess,
    CheckSubUpdateAccess,
    GetService,
)


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("", response_model=list[SubscriptionResponse])
async def get_subscriptions(
    current: GetCurrentAdmin,
    db: GetAsyncSession,
    limited: Optional[bool] = None,
    expired: Optional[bool] = None,
    is_active: Optional[bool] = None,
    enabled: Optional[bool] = None,
    search: Optional[str] = None,
    online: Optional[bool] = None,
    order_by: Optional[str] = None,
    page: Optional[int] = 1,
    size: Optional[int] = 10,
) -> list[SubscriptionResponse]:
    """Get a list of all subscriptions."""
    owner_filter = None if current.is_owner else current.id

    subscriptions = await Subscription.get_all(
        db,
        owner_id=owner_filter,
        limited=limited,
        expired=expired,
        is_active=is_active,
        enabled=enabled,
        search=search,
        online=online,
        order_by=order_by,
        page=page,
        size=size,
        load_services=True,
    )

    response = [SubscriptionResponse.from_orm(sub) for sub in subscriptions]
    return response


@router.get("/count", response_model=int)
async def get_subscription_count(
    current: GetCurrentAdmin,
    db: GetAsyncSession,
    limited: Optional[bool] = None,
    expired: Optional[bool] = None,
    is_active: Optional[bool] = None,
    enabled: Optional[bool] = None,
    online: Optional[bool] = None,
) -> int:
    """Get the count of subscriptions."""
    return await Subscription.count(
        db,
        owner_id=None if current.is_owner else current.id,
        limited=limited,
        expired=expired,
        is_active=is_active,
        enabled=enabled,
        online=online,
    )


@router.get("/stats", response_model=SubscriptionStatsResponse)
async def get_subscription_stats(current: GetCurrentAdmin, db: GetAsyncSession) -> SubscriptionStatsResponse:
    """Get subscription statistics."""
    stats = await Subscription.get_stats(db, owner_id=None if current.is_owner else current.id)
    return stats


@router.post("", response_model=list[SubscriptionResponse])
async def create_subscription(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    data: list[SubscriptionCreate],
    db: GetAsyncSession,
    _: CheckSubCreateAccess,
) -> list[SubscriptionResponse]:
    """Create bulk subscriptions."""
    if current.is_owner:
        raise HTTPException(status_code=403, detail="Owners cannot create subscriptions")
    usernames = [item.username for item in data]
    if len(usernames) != len(set(usernames)):
        raise HTTPException(status_code=400, detail="Duplicate usernames in request")
    check_exists = await Subscription.bulk_check_exists(db, usernames)
    if check_exists:
        raise HTTPException(status_code=400, detail="Subscription with this username already exists")
    if len(data) > 20:
        raise HTTPException(status_code=400, detail="Cannot create more than 20 subscriptions at once")
    subs = await Subscription.bulk_create(
        db,
        data=data,
        owner=current,
    )
    for sub in subs:
        asyncio.create_task(GuardNodeManager.create_subscription(sub=sub))
    asyncio.create_task(NotificationService.create_subscriptions(subs, current))
    return [SubscriptionResponse.from_orm(sub) for sub in subs]


@router.get("/{username}", response_model=SubscriptionResponse)
async def get_subscription(current: GetCurrentAdmin, subscription: GetSubscription) -> SubscriptionResponse:
    """Get a single subscription by username."""
    return subscription


@router.get("/{username}/usages", response_model=SubscriptionUsageLogsResponse)
async def get_subscription_usages(
    current: GetCurrentAdmin, subscription: GetSubscription, db: GetAsyncSession
) -> SubscriptionUsageLogsResponse:
    """Get usage logs for a subscription by username."""
    raise HTTPException(status_code=404, detail="Not implemented")


@router.put("/{username}", response_model=SubscriptionResponse)
async def update_subscription(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    subscription: GetSubscription,
    data: SubscriptionUpdate,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> SubscriptionResponse:
    """Update an existing subscription."""
    asyncio.create_task(GuardNodeManager.sync_subscription(subscription.username))
    asyncio.create_task(NotificationService.update_subscription(subscription, current, data))
    updated = await Subscription.update(db, subscription, data=data)
    return updated


@router.post("/enable", response_model=list[SubscriptionResponse])
async def enable_subscriptions(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    subscriptions: GetSubscriptions,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> list[SubscriptionResponse]:
    """Enable subscriptions by usernames."""
    for sub in subscriptions:
        asyncio.create_task(GuardNodeManager.activate_subscription(sub))
    asyncio.create_task(NotificationService.enable_subscriptions(subscriptions, current))
    return await Subscription.bulk_enable(db, subscriptions)


@router.post("/disable", response_model=list[SubscriptionResponse])
async def disable_subscriptions(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    subscriptions: GetSubscriptions,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> list[SubscriptionResponse]:
    """Disable subscriptions by usernames."""
    for sub in subscriptions:
        asyncio.create_task(GuardNodeManager.deactivate_subscription(sub))
    asyncio.create_task(NotificationService.disable_subscriptions(subscriptions, current))
    return await Subscription.bulk_disable(db, subscriptions)


@router.post("/revoke", response_model=list[SubscriptionResponse])
async def revoke_subscriptions(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    subscriptions: GetSubscriptions,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> list[SubscriptionResponse]:
    """Revoke subscriptions by usernames."""
    subs = await Subscription.bulk_revoke(db, subscriptions)
    for sub in subs:
        asyncio.create_task(GuardNodeManager.revoke_subscription(sub))
    asyncio.create_task(NotificationService.revoke_subscriptions(subscriptions, current))
    return subs


@router.post("/reset", response_model=list[SubscriptionResponse])
async def reset_subscriptions(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    subscriptions: GetSubscriptions,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> list[SubscriptionResponse]:
    """Reset subscriptions by usernames."""
    asyncio.create_task(NotificationService.reset_subscriptions_usage(subscriptions, current))
    return await Subscription.bulk_reset_usages(db, subscriptions)


@router.delete("", response_model=dict)
async def delete_subscriptions(
    bg: BackgroundTasks,
    current: GetCurrentAdmin,
    subscriptions: GetSubscriptions,
    db: GetAsyncSession,
    _: CheckSubRemoveAccess,
) -> dict:
    """Delete subscriptions by usernames."""
    for sub in subscriptions:
        asyncio.create_task(GuardNodeManager.remove_subscription(sub.username, sub.nodes))
    await NotificationService.delete_subscriptions(subscriptions, current)
    await Subscription.bulk_remove(db, subscriptions)
    await Admin.sync_current_counts(db)
    return {"message": f"{len(subscriptions)} subscription(s) deleted successfully"}


@router.post("/services/{service_id}", response_model=dict)
async def bulk_add_service(
    current: GetCurrentAdmin,
    service: GetService,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> dict:
    """Add a service to all subscriptions of the current admin."""
    await Subscription.bulk_add_service(db, current, service)
    return {"message": f"Service {service.id} added to all subscriptions"}


@router.delete("/services/{service_id}", response_model=dict)
async def bulk_remove_service(
    current: GetCurrentAdmin,
    service: GetService,
    db: GetAsyncSession,
    _: CheckSubUpdateAccess,
) -> dict:
    """Remove a service from all subscriptions of the current admin."""
    await Subscription.bulk_remove_service(db, current, service)
    return {"message": f"Service {service.id} removed from all subscriptions"}
