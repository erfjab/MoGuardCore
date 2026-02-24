import time
from src.db import GetDB, Admin, Subscription
from src.models.admins import AdminRole
from src.config import logger
from src.utils.cache import AdminCache
from src.utils.notif import NotificationService


async def track_resellers() -> None:
    start = time.time()
    activated_admins: list[int] = []
    deactivated_admins: list[int] = []
    async with GetDB() as db:
        all_admins = await Admin.get_all(db)
        AdminCache.set_all(all_admins)
        logger.debug(f"Cached {len(all_admins)} admins")

        admins = [a for a in all_admins if a.role in [AdminRole.RESELLER, AdminRole.SELLER]]
        if not admins:
            return
        activated_admins = [admin.id for admin in admins if not admin.reached_usage_limit]
        deactivated_admins = [admin.id for admin in admins if admin.reached_usage_limit]
        if activated_admins:
            await Subscription.bulk_dedebted(db, owner_ids=activated_admins)
        if deactivated_admins:
            await Subscription.bulk_debted(db, owner_ids=deactivated_admins)
    end = time.time()
    duration = end - start
    logger.warning(
        f"Resellers tracker task completed in {duration:.2f} seconds. [Activated: {len(activated_admins)}, Deactivated: {len(deactivated_admins)}]"
    )
    await NotificationService.system_log(
        f"Resellers tracker completed in {duration:.2f}s | Activated: {len(activated_admins)} | Deactivated: {len(deactivated_admins)}"
    )
