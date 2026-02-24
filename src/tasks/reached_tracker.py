import time
from datetime import datetime

from sqlalchemy import and_, delete, func, not_, or_, select, update

from src.db import GetDB, Admin, AsyncSession, Subscription, SubscriptionAutoRenewal
from src.config import logger
from src.utils.notif import NotificationService


def _limited_expr():
    return (func.coalesce(Subscription.limit_usage, 0) > 0) & (
        (func.coalesce(Subscription.limit_usage, 0) - (Subscription.total_usage - func.coalesce(Subscription.reset_usage, 0)))
        < 0
    )


def _expired_expr(now_ts: int):
    return (Subscription.limit_expire > 0) & (Subscription.limit_expire < now_ts)


async def _process_auto_renewals_batch(db: AsyncSession, now_utc: datetime, now_ts: int) -> int:
    ranked_renewals = select(
        SubscriptionAutoRenewal.id.label("renewal_id"),
        SubscriptionAutoRenewal.subscription_id.label("subscription_id"),
        SubscriptionAutoRenewal.limit_usage.label("renewal_limit_usage"),
        SubscriptionAutoRenewal.limit_expire.label("renewal_limit_expire"),
        SubscriptionAutoRenewal.reset_usage.label("renewal_reset_usage"),
        func.row_number()
        .over(partition_by=SubscriptionAutoRenewal.subscription_id, order_by=SubscriptionAutoRenewal.id.asc())
        .label("rn"),
    ).subquery()

    candidates_query = (
        select(
            Subscription.id.label("subscription_id"),
            Subscription.total_usage.label("total_usage"),
            ranked_renewals.c.renewal_id,
            ranked_renewals.c.renewal_limit_usage,
            ranked_renewals.c.renewal_limit_expire,
            ranked_renewals.c.renewal_reset_usage,
        )
        .join(ranked_renewals, ranked_renewals.c.subscription_id == Subscription.id)
        .where(
            Subscription.removed == False,  # noqa: E712
            Subscription.reached == True,  # noqa: E712
            or_(_limited_expr(), _expired_expr(now_ts)),
            ranked_renewals.c.rn == 1,
        )
    )
    result = await db.execute(candidates_query)
    rows = result.all()
    if not rows:
        return 0

    updates = []
    renewal_ids = []
    for row in rows:
        renewal_limit_expire = row.renewal_limit_expire
        new_limit_expire = (
            renewal_limit_expire
            if renewal_limit_expire < 0
            else now_ts + renewal_limit_expire
            if renewal_limit_expire > 0
            else 0
        )

        payload = {
            "id": row.subscription_id,
            "limit_usage": row.renewal_limit_usage,
            "limit_expire": new_limit_expire,
            "reached": False,
            "reached_at": None,
            "onreached_expire": False,
            "onreached_usage": False,
        }
        if row.renewal_reset_usage:
            payload["reset_usage"] = row.total_usage
            payload["last_reset_at"] = now_utc
        updates.append(payload)
        renewal_ids.append(row.renewal_id)

    await db.execute(update(Subscription), updates)
    await db.execute(
        delete(SubscriptionAutoRenewal)
        .where(SubscriptionAutoRenewal.id.in_(renewal_ids))
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    logger.info(f"Auto renewals executed in batch for {len(updates)} subscriptions.")
    return len(updates)


async def track_subscriptions_reacheds() -> None:
    start = time.time()
    now_utc = datetime.utcnow()
    now_ts = int(now_utc.timestamp())
    reached_count = 0
    unreached_count = 0
    auto_renewed_count = 0
    auto_deleted_count = 0
    limited_count = 0

    async with GetDB() as db:
        expire_warning_days_sq = (
            select(func.coalesce(Admin.expire_warning_days, 1)).where(Admin.id == Subscription.owner_id).scalar_subquery()
        )
        usage_warning_percent_sq = (
            select(func.coalesce(Admin.usage_warning_percent, 90)).where(Admin.id == Subscription.owner_id).scalar_subquery()
        )

        expire_warning_condition = and_(
            Subscription.limit_expire.is_not(None),
            Subscription.limit_expire > 0,
            ((Subscription.limit_expire - now_ts) / 86400) <= func.coalesce(expire_warning_days_sq, 1),
        )
        usage_warning_condition = and_(
            Subscription.limit_usage.is_not(None),
            Subscription.limit_usage > 0,
            ((Subscription.total_usage - func.coalesce(Subscription.reset_usage, 0)) * 100.0 / Subscription.limit_usage)
            >= func.coalesce(usage_warning_percent_sq, 90),
        )

        await db.execute(
            update(Subscription)
            .where(Subscription.removed == False, expire_warning_condition)  # noqa: E712
            .values(onreached_expire=True)
            .execution_options(synchronize_session=False)
        )
        await db.execute(
            update(Subscription)
            .where(Subscription.removed == False, not_(expire_warning_condition))  # noqa: E712
            .values(onreached_expire=False)
            .execution_options(synchronize_session=False)
        )

        await db.execute(
            update(Subscription)
            .where(Subscription.removed == False, usage_warning_condition)  # noqa: E712
            .values(onreached_usage=True)
            .execution_options(synchronize_session=False)
        )
        await db.execute(
            update(Subscription)
            .where(Subscription.removed == False, not_(usage_warning_condition))  # noqa: E712
            .values(onreached_usage=False)
            .execution_options(synchronize_session=False)
        )

        reached_limited_count_result = await db.execute(
            select(func.count(Subscription.id)).where(
                Subscription.removed == False,  # noqa: E712
                Subscription.reached == False,  # noqa: E712
                _limited_expr(),
            )
        )
        limited_count = reached_limited_count_result.scalar() or 0

        reached_result = await db.execute(
            update(Subscription)
            .where(
                Subscription.removed == False,  # noqa: E712
                Subscription.reached == False,  # noqa: E712
                or_(_limited_expr(), _expired_expr(now_ts)),
            )
            .values(reached=True, reached_at=now_utc)
            .execution_options(synchronize_session=False)
        )
        reached_count = reached_result.rowcount or 0

        auto_renewed_count = await _process_auto_renewals_batch(db, now_utc, now_ts)

        unreached_result = await db.execute(
            update(Subscription)
            .where(
                Subscription.removed == False,  # noqa: E712
                Subscription.reached == True,  # noqa: E712
                not_(or_(_limited_expr(), _expired_expr(now_ts))),
            )
            .values(reached=False, reached_at=None, onreached_expire=False, onreached_usage=False)
            .execution_options(synchronize_session=False)
        )
        unreached_count = unreached_result.rowcount or 0

        auto_delete_condition = and_(
            Subscription.removed == False,  # noqa: E712
            Subscription.reached == True,  # noqa: E712
            Subscription.auto_delete_days.is_not(None),
            Subscription.auto_delete_days > 0,
            Subscription.reached_at.is_not(None),
            func.extract("epoch", now_utc - Subscription.reached_at) >= (Subscription.auto_delete_days * 86400),
        )

        to_delete_result = await db.execute(
            select(
                Subscription.id,
                Subscription.username,
                Subscription.owner_id,
                Subscription.auto_delete_days,
            ).where(auto_delete_condition)
        )
        to_delete_rows = to_delete_result.all()

        if to_delete_rows:
            delete_ids = [row.id for row in to_delete_rows]
            auto_deleted_count = len(delete_ids)

            await db.execute(
                update(Subscription)
                .where(Subscription.id.in_(delete_ids))
                .values(removed=True, username=None, removed_at=now_utc)
                .execution_options(synchronize_session=False)
            )

            logger.warning(f"Auto deleted {len(delete_ids)} subscriptions after reached timeout.")

    end = time.time()
    duration = end - start
    logger.warning(
        "Subscriptions Reached tracked in "
        f"{duration:.2f} seconds. "
        f"[Reached: {reached_count}, Limited: {limited_count}, Unreached: {unreached_count}, AutoRenewed: {auto_renewed_count}, AutoDeleted: {auto_deleted_count}]"
    )
    await NotificationService.system_log(
        "Subscriptions reached tracker completed "
        f"in {duration:.2f}s | Reached: {reached_count} | Limited: {limited_count} | "
        f"Unreached(Connected): {unreached_count} | AutoRenewed: {auto_renewed_count} | AutoDeleted: {auto_deleted_count}"
    )
