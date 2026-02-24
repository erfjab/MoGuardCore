import time
import aiohttp
import gc
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import select, func, update
from src.db import GetDB, Subscription, SubscriptionUsageLogs, SubscriptionUsage, Admin
from src.config import MOREBOT_LINCENSE_KEY, MOREBOT_SECRET_KEY, logger
from src.utils.notif import NotificationService

FAILED_USAGES: dict[str, int] = defaultdict(int)


async def send_usage(usages: dict[str, int]) -> None:
    total_gb = sum(usages.values()) / (1024**3)
    failed_gb = sum(FAILED_USAGES.values()) / (1024**3)
    for username, failed_usage in FAILED_USAGES.items():
        usages[username] += failed_usage
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.post(
                f"https://{MOREBOT_LINCENSE_KEY}.morebot.top/api/subscriptions/{MOREBOT_SECRET_KEY}/usages",
                json=[{"username": username, "usage": int(usage)} for username, usage in usages.items()],
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                FAILED_USAGES.clear()
                logger.info(f"Sent {total_gb:.2f}GB (+{failed_gb:.2f}GB retry) to MoreBot")
    except Exception as e:
        for username, usage in usages.items():
            FAILED_USAGES[username] = usage
        logger.error(f"Failed to send {total_gb:.2f}GB to MoreBot, stored for retry | {e}")


async def upsert_subscription_usage() -> None:
    start = time.time()
    usages = defaultdict(int)
    async with GetDB() as db:
        subs_stmt = select(Subscription.id, Subscription.owner_id, Admin.username).join(
            Admin, Subscription.owner_id == Admin.id
        )
        result = await db.execute(subs_stmt)
        subs_info = result.all()

        if not subs_info:
            return

        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        total_usage_stmt = (
            select(SubscriptionUsage.subscription_id, func.coalesce(func.sum(SubscriptionUsage.usage), 0))
            .join(Subscription, SubscriptionUsage.subscription_id == Subscription.id)
            .group_by(SubscriptionUsage.subscription_id)
        )
        result = await db.execute(total_usage_stmt)
        total_usages = dict(result.all())
        all_logged_stmt = (
            select(SubscriptionUsageLogs.subscription_id, func.coalesce(func.sum(SubscriptionUsageLogs.usage), 0))
            .join(Subscription, SubscriptionUsageLogs.subscription_id == Subscription.id)
            .group_by(SubscriptionUsageLogs.subscription_id)
        )
        result = await db.execute(all_logged_stmt)
        all_logged_usages = dict(result.all())

        current_hour_plus = current_hour + timedelta(hours=1)
        current_logs_stmt = (
            select(SubscriptionUsageLogs)
            .join(Subscription, SubscriptionUsageLogs.subscription_id == Subscription.id)
            .where(SubscriptionUsageLogs.created_at >= current_hour)
            .where(SubscriptionUsageLogs.created_at < current_hour_plus)
        )
        result = await db.execute(current_logs_stmt)
        current_logs = {log.subscription_id: log for log in result.scalars().all()}

        admin_updates = defaultdict(int)

        for sub_id, owner_id, owner_username in subs_info:
            total = total_usages.get(sub_id, 0)
            all_logged = all_logged_usages.get(sub_id, 0)
            unlogged_usage = total - all_logged
            if unlogged_usage > 0:
                existing_log = current_logs.get(sub_id)
                if existing_log:
                    existing_log.usage += unlogged_usage
                    admin_updates[owner_id] += unlogged_usage
                    usages[owner_username] += unlogged_usage
                else:
                    new_log = SubscriptionUsageLogs(subscription_id=sub_id, usage=unlogged_usage, created_at=current_hour)
                    db.add(new_log)
                    admin_updates[owner_id] += unlogged_usage
                    usages[owner_username] += unlogged_usage

        for owner_id, delta in admin_updates.items():
            if delta > 0:
                await db.execute(update(Admin).where(Admin.id == owner_id).values(current_usage=Admin.current_usage + delta))
        await db.flush()

    if MOREBOT_LINCENSE_KEY and MOREBOT_SECRET_KEY:
        await send_usage(usages)

    end = time.time()
    logger.info(f"Upserted subscription usages in {end - start:.2f} seconds")
    await NotificationService.system_log(f"Upserted subscription usages in {end - start:.2f} seconds")
    del usages, admin_updates, subs_info, total_usages, all_logged_usages, current_logs
    gc.collect()
