import base64
import asyncio
from fastapi import APIRouter, Response, Request, HTTPException
from src.dependencies import GetGuard, CheckAccessTag, GetAsyncSession
from src.utils.links import LinkGeneration
from src.db import Subscription, GetDB
from src.models.subscriptions import SubscriptionResponse, SubscriptionUsageLogsResponse
from src.config import logger
from src.guard_node import GuardNodeManager

router = APIRouter(
    tags=["Guards"],
)


async def bg_update_last_request(sub_id: int, client_agent: str):
    async with GetDB() as db:
        sub = await Subscription.get_by_id(db, sub_id)
        if sub:
            await Subscription.set_last_request(db, sub, client_agent=client_agent)


async def bg_mark_changed(sub_id: int) -> None:
    async with GetDB() as db:
        sub = await Subscription.mark_changed(db=db, sub_id=sub_id)
        if sub:
            asyncio.create_task(GuardNodeManager.revoke_subscription(sub=sub))


def get_headers(sub: Subscription) -> dict:
    subscription_userinfo = {
        "upload": 0,
        "download": sub.current_usage,
        "total": sub.limit_usage,
        "expire": (sub.limit_expire if sub.limit_expire > 0 else 0),
    }

    def encode_header(text: str) -> str:
        return f"base64:{base64.b64encode(text.encode()).decode()}"

    response_headers = {
        "content-disposition": "",
        "profile-web-page-url": sub.link,
        "support-url": (sub.owner.support_url or "").strip(),
        "profile-title": encode_header((sub.owner.access_title or "").format(**sub.format).strip()),
        "profile-update-interval": str(sub.owner.update_interval) or "1",
        "subscription-userinfo": "; ".join(f"{key}={val}" for key, val in subscription_userinfo.items()),
        "announce": encode_header((sub.owner.announce or "").format(**sub.format).strip()),
        "announce-url": (sub.owner.announce_url or "").strip(),
    }
    return response_headers


@router.get("/{tag}/{secret}")
async def get_subscription(
    db: GetAsyncSession,
    subscription: GetGuard,
    request: Request,
    tag: CheckAccessTag,
) -> Response:
    """Handle incoming subscription request from clients."""
    client_agent = request.headers.get("User-Agent", "")
    asyncio.create_task(bg_update_last_request(subscription.id, client_agent))
    if not subscription.changed:
        asyncio.create_task(bg_mark_changed(subscription.id))
    links = await LinkGeneration.generate(sub=subscription)
    headers = get_headers(subscription)
    return Response(
        content="\n".join(links) if links else "",
        media_type="text/plain",
        headers=headers,
    )


@router.get("/{tag}/{secret}/info")
async def get_subscription_info(subscription: GetGuard, tag: CheckAccessTag) -> SubscriptionResponse:
    """Get subscription information."""
    return subscription


@router.get("/{tag}/{secret}/usages")
async def get_subscription_usages(
    subscription: GetGuard,
    tag: CheckAccessTag,
) -> SubscriptionUsageLogsResponse:
    """Get subscription usage logs."""
    raise HTTPException(status_code=404, detail="Not implemented")
