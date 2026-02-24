from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from .subs_tracker import track_subscriptions
from .resellers_tracker import track_resellers
from .node_access import upsert_access
from .usage_record import upsert_subscription_usage
from .reached_tracker import track_subscriptions_reacheds
from .links_update import update_links_task
from .configs_update import update_configs_task
from .ram_checker import check_system_resources

TaskManager = AsyncIOScheduler()

TaskManager.add_job(
    check_system_resources,
    IntervalTrigger(seconds=90, timezone="UTC"),
    id="check_system_resources",
    replace_existing=False,
)
TaskManager.add_job(
    update_links_task,
    CronTrigger(minute="*", hour="*", timezone="UTC"),
    id="update_links_task",
    replace_existing=False,
)
TaskManager.add_job(
    update_configs_task,
    CronTrigger(minute="*", hour="*", timezone="UTC"),
    id="update_configs_task",
    replace_existing=False,
)
TaskManager.add_job(
    upsert_subscription_usage,
    CronTrigger(minute="*", hour="*", timezone="UTC"),
    id="upsert_subscription_usage",
    replace_existing=False,
)
TaskManager.add_job(
    track_subscriptions_reacheds,
    CronTrigger(minute="*", hour="*", timezone="UTC"),
    id="track_subscriptions_reacheds",
    replace_existing=False,
)
TaskManager.add_job(
    track_subscriptions,
    CronTrigger(minute="*", hour="*", timezone="UTC"),
    id="track_subscriptions_usage",
    replace_existing=False,
)
TaskManager.add_job(
    track_resellers,
    CronTrigger(minute="*", hour="*", timezone="UTC"),
    id="track_resellers",
    replace_existing=False,
)
TaskManager.add_job(
    upsert_access,
    IntervalTrigger(hours=8, timezone="UTC"),
    id="upsert_access",
    replace_existing=False,
)
