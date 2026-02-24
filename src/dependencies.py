import asyncio
from typing import Annotated, AsyncGenerator, Optional, List
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Body, Request
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from src.db import GetDB, AsyncSession, Node, Service, Admin, Subscription
from src.utils.auth import Auth
from src.utils.cache import AdminCache

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admins/token", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _get_db() -> AsyncGenerator[AsyncSession, None]:
    async with GetDB() as db:
        yield db


async def _get_node(node_id: int, db: AsyncSession = Depends(_get_db)) -> Node:
    node = await Node.get_by_id(db, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


async def _get_service(service_id: int, db: AsyncSession = Depends(_get_db)) -> Service:
    service = await Service.get_by_id(db, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


async def _get_admin(username: str, db: AsyncSession = Depends(_get_db)) -> "Admin":
    admin = await Admin.get_by_username(db, username)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return admin


async def _get_current_admin(
    token: Annotated[str, Depends(oauth2_scheme)] = None,
    x_api_key: Annotated[Optional[str], Depends(api_key_header)] = None,
    db: AsyncSession = Depends(_get_db),
) -> Admin:
    if token:
        data = Auth.load(token)
        if not data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        admin = AdminCache.get_by_username(data.username)
        if admin is None:
            admin = await Admin.get_by_username(db, data.username)
            if admin:
                AdminCache.update(admin)

        if (
            not admin
            or (not admin.enabled and admin.id != int(data.admin_id))
            or admin.role != data.role
            or admin.hashed_secret() != data.secret
        ):
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
        if (admin.last_password_reset_at or admin.created_at) > data.created_at:
            raise HTTPException(status_code=401, detail="Token has been invalidated due to password change")
        if admin.last_totp_revoked_at and admin.last_totp_revoked_at > data.created_at:
            raise HTTPException(status_code=401, detail="Token has been invalidated due to TOTP revocation")
        asyncio.create_task(Admin.update_last_online(admin))

        if not admin.is_owner and admin.reached_usage_limit:
            raise HTTPException(status_code=403, detail="Usage limit reached, contact owner to upgrade your plan")
        return admin

    if x_api_key:
        admin = await Admin.get_by_api_key(db, x_api_key)
        if not admin or not admin.enabled:
            raise HTTPException(status_code=401, detail="Invalid or expired credentials")
        if not admin.is_owner and admin.reached_usage_limit:
            raise HTTPException(status_code=403, detail="Usage limit reached, contact owner to upgrade your plan")
        return admin

    raise HTTPException(status_code=401, detail="Invalid or expired credentials")


async def _get_current_owner(
    current: Annotated[Admin, Depends(_get_current_admin)],
) -> Admin:
    if not current.is_owner:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current


async def _block_owner_action(
    admin: Annotated[Admin, Depends(_get_admin)],
) -> None:
    if admin.is_owner:
        raise HTTPException(status_code=403, detail="Owners are not allowed to perform this action")


async def _get_subscription_by_username(
    username: str,
    current: Admin = Depends(_get_current_admin),
    db: AsyncSession = Depends(_get_db),
) -> Subscription:
    subscription = await Subscription.get_by_username(db, username)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.owner_id != current.id and not current.is_owner:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return subscription


async def _subscription_create_access(
    current: Admin = Depends(_get_current_admin),
) -> None:
    if not current.is_owner and not current.create_access:
        raise HTTPException(status_code=403, detail="Not enough permissions")


async def _subscription_update_access(
    current: Admin = Depends(_get_current_admin),
) -> None:
    if not current.is_owner and not current.update_access:
        raise HTTPException(status_code=403, detail="Not enough permissions")


async def _subscription_remove_access(
    current: Admin = Depends(_get_current_admin),
) -> None:
    if not current.is_owner and not current.remove_access:
        raise HTTPException(status_code=403, detail="Not enough permissions")


async def _get_subscription_by_secret(
    secret: str,
) -> Subscription:
    async with GetDB() as db:
        subscription = await Subscription.get_by_secret(db, secret)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


async def _get_subscriptions_by_usernames(
    usernames: List[str] = Body(..., embed=True, min_length=1, max_length=10),
    current: Admin = Depends(_get_current_admin),
    db: AsyncSession = Depends(_get_db),
) -> List[Subscription]:
    if len(list(set(usernames))) != len(usernames):
        raise HTTPException(status_code=400, detail="Duplicate usernames in request")
    subscriptions = await Subscription.get_by_usernames(db, usernames)
    if len(subscriptions) != len(usernames):
        found = {s.username for s in subscriptions}
        missing = [u for u in usernames if u not in found]
        raise HTTPException(status_code=404, detail=f"Subscriptions not found: {', '.join(missing)}")
    for sub in subscriptions:
        if not current.is_owner and sub.owner_id != current.id:
            raise HTTPException(status_code=403, detail=f"Access denied for '{sub.username}'")
    return subscriptions


async def _get_stats_date_range(
    start_date: str,
    end_date: str,
) -> tuple[datetime, datetime]:
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

        if start.tzinfo is not None:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        if end.tzinfo is not None:
            end = end.astimezone(timezone.utc).replace(tzinfo=None)

        return start, end
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format.")


async def _check_access_tag(tag: str) -> str:
    if not (4 <= len(tag) <= 30):
        raise HTTPException(status_code=400, detail="Access tag length must be between 4 and 30 characters.")
    return tag


GetAsyncSession = Annotated[AsyncSession, Depends(_get_db)]
GetNode = Annotated[Node, Depends(_get_node)]
GetService = Annotated[Service, Depends(_get_service)]
GetAdmin = Annotated["Admin", Depends(_get_admin)]
GetCurrentAdmin = Annotated[Admin, Depends(_get_current_admin)]
GetCurrentOwner = Annotated[Admin, Depends(_get_current_owner)]
GetSubscription = Annotated[Subscription, Depends(_get_subscription_by_username)]
GetSubscriptions = Annotated[List[Subscription], Depends(_get_subscriptions_by_usernames)]
GetGuard = Annotated[Subscription, Depends(_get_subscription_by_secret)]
GetStatsDateRange = Annotated[tuple[datetime, datetime], Depends(_get_stats_date_range)]
CheckSubCreateAccess = Annotated[None, Depends(_subscription_create_access)]
CheckSubUpdateAccess = Annotated[None, Depends(_subscription_update_access)]
CheckSubRemoveAccess = Annotated[None, Depends(_subscription_remove_access)]
BlockOwnerAction = Annotated[None, Depends(_block_owner_action)]
CheckAccessTag = Annotated[str, Depends(_check_access_tag)]
