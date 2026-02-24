from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func, case
from sqlalchemy.orm import lazyload
from src.dependencies import GetAsyncSession, GetCurrentAdmin, GetStatsDateRange, GetCurrentOwner
from src.db import Subscription, SubscriptionUsageLogs
from src.models.stats import (
    SubscriptionStatusStatsResponse,
    MostUsageSubscription,
    UsageSubscriptionDetail,
    UsageDetail,
    UsageStatsResponse,
    AgentStatsDetail,
    AgentStatsResponse,
    LastReachedSubscriptionDetail,
)

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("/subscriptions/status", response_model=SubscriptionStatusStatsResponse)
async def get_subscription_status_stats(
    session: GetAsyncSession,
    current: GetCurrentAdmin,
):
    query = select(
        func.count().label("total"),
        func.sum(case((Subscription.is_active == True, 1), else_=0)).label("available"),
        func.sum(case((Subscription.is_active == False, 1), else_=0)).label("unavailable"),
        func.sum(case((Subscription.enabled == False, 1), else_=0)).label("disabled"),
        func.sum(case((Subscription.expired == True, 1), else_=0)).label("expired"),
        func.sum(case((Subscription.limited == True, 1), else_=0)).label("limited"),
        func.sum(case(((Subscription.is_active == True) & (Subscription.limit_expire >= 0), 1), else_=0)).label("active"),
        func.sum(case(((Subscription.is_active == True) & (Subscription.limit_expire < 0), 1), else_=0)).label("pending"),
        func.sum(case(((Subscription.is_online == True) & (Subscription.is_active == True), 1), else_=0)).label("online"),
        func.sum(case(((Subscription.is_online == False) & (Subscription.is_active == True), 1), else_=0)).label("offline"),
        func.sum(case(((Subscription.online_at >= datetime.utcnow() - timedelta(hours=24)), 1), else_=0)).label(
            "last_24h_online"
        ),
    ).where(Subscription.removed == False)

    if not current.is_owner:
        query = query.where(Subscription.owner_id == current.id)

    result = await session.execute(query)
    stats = result.one()

    last_24h_usage_query = (
        select(func.sum(SubscriptionUsageLogs.usage))
        .join(Subscription, Subscription.id == SubscriptionUsageLogs.subscription_id)
        .where(
            SubscriptionUsageLogs.created_at >= datetime.utcnow() - timedelta(hours=24),
        )
    )

    if not current.is_owner:
        last_24h_usage_query = last_24h_usage_query.where(Subscription.owner_id == current.id)

    last_24h_usage_result = await session.execute(last_24h_usage_query)
    last_24h_usage = last_24h_usage_result.scalar() or 0

    total_usage_query = select(func.sum(SubscriptionUsageLogs.usage)).join(
        Subscription, Subscription.id == SubscriptionUsageLogs.subscription_id
    )

    if not current.is_owner:
        total_usage_query = total_usage_query.where(Subscription.owner_id == current.id)

    total_usage_result = await session.execute(total_usage_query)
    total_usage = total_usage_result.scalar() or 0

    return SubscriptionStatusStatsResponse(
        total=stats.total or 0,
        active=stats.active or 0,
        disabled=stats.disabled or 0,
        expired=stats.expired or 0,
        limited=stats.limited or 0,
        pending=stats.pending or 0,
        available=stats.available or 0,
        unavailable=stats.unavailable or 0,
        online=stats.online or 0,
        offline=stats.offline or 0,
        total_usage=total_usage,
        last_24h_online=stats.last_24h_online or 0,
        last_24h_usage=last_24h_usage,
    )


@router.get("/subscriptions/most_usage", response_model=MostUsageSubscription)
async def get_most_usage_subscriptions(
    date_range: GetStatsDateRange,
    session: GetAsyncSession,
    current: GetCurrentOwner,
):
    start_date, end_date = date_range
    usage_sum = func.sum(SubscriptionUsageLogs.usage).label("usage")
    query = (
        select(Subscription.username, Subscription.is_active, usage_sum)
        .join(SubscriptionUsageLogs, Subscription.id == SubscriptionUsageLogs.subscription_id)
        .where(SubscriptionUsageLogs.created_at >= start_date)
        .where(SubscriptionUsageLogs.created_at <= end_date)
        .where(Subscription.removed == False)
        .group_by(Subscription.id)
        .order_by(usage_sum.desc())
        .limit(10)
    )

    if not current.is_owner:
        query = query.where(Subscription.owner_id == current.id)

    result = await session.execute(query)
    subscriptions = result.all()

    usage_details = [
        UsageSubscriptionDetail(username=username, usage=usage or 0, is_active=is_active)
        for username, is_active, usage in subscriptions
    ]

    return MostUsageSubscription(subscriptions=usage_details, start_date=start_date, end_date=end_date)


@router.get("/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    date_range: GetStatsDateRange,
    session: GetAsyncSession,
    current: GetCurrentOwner,
):
    start_date, end_date = date_range

    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if (end_date - start_date).total_seconds() < 3600:
        raise HTTPException(status_code=400, detail="Date range must be at least 1 hour")

    query = (
        select(
            func.date_trunc("hour", SubscriptionUsageLogs.created_at).label("hour"),
            func.sum(SubscriptionUsageLogs.usage).label("usage"),
        )
        .where(SubscriptionUsageLogs.created_at >= start_date)
        .where(SubscriptionUsageLogs.created_at <= end_date)
        .join(Subscription, Subscription.id == SubscriptionUsageLogs.subscription_id)
        .group_by("hour")
        .order_by("hour")
    )
    if not current.is_owner:
        query = query.where(Subscription.owner_id == current.id)
    result = await session.execute(query)
    usage_stats = result.all()
    usage_details = [
        UsageDetail(start_date=hour, end_date=hour + timedelta(hours=1), usage=usage or 0) for hour, usage in usage_stats
    ]
    total_usage = sum(usage.usage for usage in usage_details)
    return UsageStatsResponse(total=total_usage, usages=usage_details, start_date=start_date, end_date=end_date)


@router.get("/agents", response_model=AgentStatsResponse)
async def get_agent_stats(
    session: GetAsyncSession,
    current: GetCurrentOwner,
):
    agent_column = Subscription.last_client_agent

    category_expr = case(
        (agent_column.ilike("%v2rayNG%"), "v2rayNG"),
        (agent_column.ilike("%v2rayN%"), "v2rayN"),
        (agent_column.ilike("%Hiddify%"), "Hiddify"),
        (agent_column.ilike("%Neko%"), "NekoBox"),
        (agent_column.ilike("%V2Box%"), "V2Box"),
        (agent_column.ilike("%Foxray%"), "FoXray"),
        (agent_column.ilike("%Shadowrocket%"), "Shadowrocket"),
        (agent_column.ilike("%Streisand%"), "Streisand"),
        (agent_column.ilike("%SFA%"), "SFA"),
        (agent_column.ilike("%Clash%"), "Clash"),
        (agent_column.ilike("%Stash%"), "Stash"),
        (agent_column.ilike("%Loon%"), "Loon"),
        (agent_column.ilike("%Surge%"), "Surge"),
        (agent_column.ilike("%Fair%"), "Fair"),
        (agent_column.ilike("%Karing%"), "Karing"),
        (agent_column.ilike("%Happ%"), "Happ"),
        (agent_column.ilike("%sing-box%"), "Sing-Box"),
        (agent_column.ilike("%CheckHost%"), "CheckHost"),
        (agent_column.ilike("%Mozilla%"), "Browser"),
        (agent_column.ilike("%Chrome%"), "Browser"),
        (agent_column.ilike("%Safari%"), "Browser"),
    ).label("category")

    query = (
        select(
            category_expr,
            func.count(Subscription.id).label("count"),
        )
        .where(Subscription.removed == False)
        .where(Subscription.last_client_agent.isnot(None))
    )

    if not current.is_owner:
        query = query.where(Subscription.owner_id == current.id)

    query = query.group_by(category_expr).order_by(func.count(Subscription.id).desc())

    result = await session.execute(query)
    agent_stats = result.all()

    agents = [AgentStatsDetail(category=category, count=count) for category, count in agent_stats if category is not None]

    return AgentStatsResponse(agents=agents)


@router.get("/subscriptions/reacheds", response_model=list[LastReachedSubscriptionDetail])
async def get_last_reached_subscriptions(
    session: GetAsyncSession,
    current: GetCurrentOwner,
    page: int = 1,
    size: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    query = select(
        Subscription.username,
        Subscription.reached_at,
        Subscription.limited,
        Subscription.expired,
    ).where(Subscription.reached_at.isnot(None), Subscription.removed == False)

    if start_date:
        query = query.where(Subscription.reached_at >= start_date)
    if end_date:
        query = query.where(Subscription.reached_at <= end_date)

    if not current.is_owner:
        query = query.where(Subscription.owner_id == current.id)

    query = query.order_by(Subscription.reached_at.desc()).offset((page - 1) * size).limit(size)

    result = await session.execute(query)
    subscriptions = result.all()

    return [
        LastReachedSubscriptionDetail(
            username=row.username,
            reached_at=row.reached_at,
            limited=row.limited,
            expired=row.expired,
        )
        for row in subscriptions
    ]
