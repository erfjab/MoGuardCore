import math
import asyncio
import time
import gc
import traceback
import aiohttp
from src.guard_node import GuardNodeManager, MarzbanUserResponse, MarzneshinUserResponse, RustneshinUserResponse
from src.db import GetDB, Subscription, Node, Admin, NodeCategory
from src.db.models.subscription import SubscriptionUsage
from src.config import logger
from src.utils.notif import NotificationService
from src.utils.configs import get_configs

UserResponse = MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse

_sync_lock = asyncio.Lock()


async def fetch_node_scripted_data(node: Node) -> tuple[dict | None, dict[str, UserResponse]]:
    try:
        data = await GuardNodeManager.get_scripted_users(node=node)
        if data is None:
            return None, {}
        configs = get_configs(node.id)
        if not configs:
            logger.warning(f"Failed to get configs from '{node.remark}' Node")
            return None, {}
        users_list: list[UserResponse] = []
        for item in data["users"]:
            if node.category == NodeCategory.marzban:
                user = MarzbanUserResponse.parse_obj(item)
            elif node.category == NodeCategory.marzneshin:
                user = MarzneshinUserResponse.parse_obj(item)
            elif node.category == NodeCategory.rustneshin:
                user = RustneshinUserResponse.parse_obj(item)
            else:
                continue
            users_list.append(user)
        users_dict = {user.username: user for user in users_list}
        return configs, users_dict
    except aiohttp.ClientConnectorError as e:
        from src.utils.notif import NotificationService

        await NotificationService.system_log(f"❌ Connection error while fetching subs from '{node.remark}': {e}")
        logger.error(f"Connection error while fetching scripted data from '{node.remark}': {e}")
        return None, {}
    except Exception as e:
        from src.utils.notif import NotificationService

        await NotificationService.system_log(f"❌ Exception while fetching subs from '{node.remark}': {e}")
        logger.exception(f"Exception while fetching scripted data from '{node.remark}': {e}")
        return None, {}


async def fetch_node_data(node: Node) -> tuple[dict | None, dict[str, UserResponse]]:
    if node.is_scripted:
        return await fetch_node_scripted_data(node)
    configs = get_configs(node.id)
    if not configs:
        logger.warning(f"Failed to get configs from '{node.remark}' Node")
        return None, {}

    for _ in range(2):
        users_count = await GuardNodeManager.get_subscriptions_count(node=node)
        if users_count is not None:
            break
        await asyncio.sleep(1.5)
    if users_count is None:
        logger.warning(f"Failed to get users count from '{node.remark}' Node")
        return None, {}

    users_list: list[UserResponse] = []
    pages = math.ceil(users_count / 100) if users_count > 0 else 0
    start = time.perf_counter()
    for page in range(1, pages + 1):
        for _ in range(10):
            res = await GuardNodeManager.get_all_subscriptions(node=node, page=page, size=100)
            if res is not None:
                break
            await asyncio.sleep(2)
        if res is None:
            await NotificationService.system_log(f"❌ failed to get subs in '{node.remark}' at page '{page}'")
            logger.warning(f"Skipping '{node.remark}' Node due to API failure")
            return None, {}
        if res:
            users_list.extend(res)
    duration = time.perf_counter() - start
    logger.info(f"Fetched {len(users_list)} users from '{node.remark}' in {duration:.3f}s")

    users_dict = {user.username: user for user in users_list}
    return configs, users_dict


async def sync_sub_on_node(
    node: Node, configs: dict, sub: Subscription, user: UserResponse | None, sem: asyncio.Semaphore
) -> None:
    async with sem:
        sub_is_active = sub.is_active
        sub_node_ids = sub.node_ids

        if not user:
            if sub_is_active and node.id in sub_node_ids:
                logger.info(f"Creating '{sub.username}' on '{node.remark}'")
                await GuardNodeManager.create_subscription(node=node, sub=sub, configs=configs)
            return

        if not node.availabled:
            if user.is_active:
                logger.info(f"Deactivating '{sub.username}' on '{node.remark}'")
                await GuardNodeManager.deactivate_subscription(node=node, sub=sub)
            return

        if node.id not in sub_node_ids:
            if user.is_active:
                logger.info(f"Deactivating '{sub.username}' on '{node.remark}'")
                await GuardNodeManager.deactivate_subscription(sub=sub, node=node)
            return

        await GuardNodeManager.sync_config(node=node, sub=sub, user=user, configs=configs)

        if not sub_is_active and user.is_active:
            logger.info(f"Deactivating '{sub.username}' on '{node.remark}'")
            await GuardNodeManager.deactivate_subscription(node=node, sub=sub)
        elif sub_is_active and not user.is_active:
            logger.info(f"Activating '{sub.username}' on '{node.remark}'")
            await GuardNodeManager.activate_subscription(node=node, sub=sub)


async def perform_sync_operations(
    subs: list[Subscription], nodes_data: dict[Node, tuple[dict | None, dict[str, UserResponse]]]
) -> None:
    """Perform sync operations (activate/deactivate/remove) on nodes"""
    sem = asyncio.Semaphore(10)

    sync_tasks = [
        sync_sub_on_node(node, configs, sub, users.get(sub.server_key), sem)
        for sub in subs
        if not sub.should_be_remove
        for node, (configs, users) in nodes_data.items()
        if configs is not None
    ]

    async def remove_sub_bounded(username: str, nodes: list[Node]):
        async with sem:
            await GuardNodeManager.remove_subscription(username=username, nodes=nodes)

    local_usernames = {sub.server_key for sub in subs if not sub.should_be_remove}
    for node, (configs, users) in nodes_data.items():
        if configs is None:
            continue
        for username in users:
            if username not in local_usernames and username != "guard":
                logger.info(f"Removing unknown user '{username}' from '{node.remark}'")
                sync_tasks.append(remove_sub_bounded(username=username, nodes=[node]))
    await asyncio.gather(*sync_tasks)


async def _background_sync_wrapper(
    subs: list[Subscription], nodes_data: dict[Node, tuple[dict | None, dict[str, UserResponse]]]
) -> None:
    if _sync_lock.locked():
        await NotificationService.locked_task("Subscriptions Sync")
        logger.warning("Sync operation already running, skipping background sync")
        return

    async with _sync_lock:
        try:
            await perform_sync_operations(subs=subs, nodes_data=nodes_data)
        except Exception as e:
            logger.error(f"Critical error in background sync: {e}")
            logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))


async def track_subscriptions() -> None:
    start = time.time()

    async with GetDB() as db:
        nodes = await Node.get_all(db)
        if not nodes:
            logger.warning("No nodes found")
            return
    t1 = time.time()

    nodes_data: dict[Node, tuple[dict | None, dict[str, UserResponse]]] = {}
    results = await asyncio.gather(*[fetch_node_data(node) for node in nodes], return_exceptions=True)
    for node, result in zip(nodes, results):
        if isinstance(result, Exception):
            logger.exception(f"Error fetching '{node.remark}': {result}")
            nodes_data[node] = (None, {})
        else:
            nodes_data[node] = result
    for node, (configs, users) in nodes_data.items():
        if configs is None:
            from src.utils.notif import NotificationService

            await NotificationService.unavailable_node_detected(node)
    t2 = time.time()

    async with GetDB() as db:
        subs = await Subscription.get_all(db, load_service_nodes=True)
        all_usages = await SubscriptionUsage.get_all(db)

        usages_map: dict[int, list[SubscriptionUsage]] = {}
        for usage in all_usages:
            usages_map.setdefault(usage.subscription_id, []).append(usage)

        updated_count = 0
        for sub in subs:
            sub_usages: dict[Node, tuple[int, any]] = {}
            for node, (configs, users) in nodes_data.items():
                if configs and (user := users.get(sub.server_key)):
                    sub_usages[node] = (user.lifetime_used_traffic, user.created_at)

            if sub_usages:
                await Subscription.bulk_upsert_usages(db=db, sub=sub, usages=sub_usages, sub_usages=usages_map.get(sub.id, []))
                updated_count += 1

        await db.flush()
        await Subscription.sync_cached_usages(db)
        await Admin.sync_current_counts(db)
        subs = await Subscription.get_all(db, load_service_nodes=True)

        logger.debug(f"Cached {len(subs)} subscriptions")
    t3 = time.time()
    asyncio.create_task(_background_sync_wrapper(subs=subs, nodes_data=nodes_data))
    total_users = sum(len(users) for _, users in nodes_data.values())
    logger.warning(
        f"Tracked {len(subs)} subs, {len(nodes)} nodes, {total_users} users | nodes: {t1 - start:.2f}s, fetch: {t2 - t1:.2f}s, db: {t3 - t2:.2f}s, total: {time.time() - start:.2f}s"
    )
    from src.utils.notif import NotificationService

    await NotificationService.system_log(
        f"Subscriptions tracked: {len(subs)} subs, {len(nodes)} nodes, {total_users} users in {time.time() - start:.2f} seconds."
    )
    del nodes_data, subs, results
    gc.collect()
