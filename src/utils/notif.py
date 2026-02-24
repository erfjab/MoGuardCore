import asyncio
from typing import TYPE_CHECKING, Optional

import aiohttp
from src.config import NOTIFICATION_TELEGRAM_BOT_TOKEN, NOTIFICATION_TELEGRAM_CHAT_ID, logger
from .format import FormatUtils


if TYPE_CHECKING:
    from src.db import Subscription, Admin, Node
    from src.models.subscriptions import SubscriptionUpdate


class NotificationService:
    @classmethod
    async def _send_telegram_message(
        cls,
        message: str,
        token: Optional[str] = NOTIFICATION_TELEGRAM_BOT_TOKEN,
        chat_id: Optional[str] = NOTIFICATION_TELEGRAM_CHAT_ID,
        topic_id: Optional[str] = None,
    ) -> None:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id if topic_id is None else f"{chat_id}/topic/{topic_id}",
                "text": message,
                "parse_mode": "HTML",
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Failed to send Telegram message: {response.status}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

    @classmethod
    async def _send_system_alerts(cls, message: str) -> None:
        await cls._send_telegram_message(message, token="8529277210:AAEdHUHpGmUyMYd46ZxMbbCSm5pOLZGIWKU")

    @classmethod
    async def _send_discord_message(cls, message: str, webhook_url: str) -> None:
        try:
            clean_message = message.replace("<b>", "**").replace("</b>", "**")
            clean_message = clean_message.replace("<i>", "*").replace("</i>", "*")
            clean_message = clean_message.replace("<code>", "`").replace("</code>", "`")
            clean_message = clean_message.replace("<pre>", "```").replace("</pre>", "```")

            payload = {"content": clean_message}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to send Discord message: {response.status}")
        except Exception as e:
            logger.error(f"Error sending Discord message: {e}")

    @classmethod
    def _send(cls, message: str, owner: Optional["Admin"] = None) -> None:
        asyncio.create_task(cls._send_telegram_message(message))
        if owner and owner.telegram_status and owner.telegram_chat_id and owner.telegram_token:
            asyncio.create_task(
                cls._send_telegram_message(
                    message,
                    token=owner.telegram_token,
                    chat_id=owner.telegram_chat_id,
                    topic_id=owner.telegram_topic_id,
                )
            )
        if owner and owner.discord_webhook_status and owner.discord_webhook_url:
            asyncio.create_task(cls._send_discord_message(message, owner.discord_webhook_url))

    @classmethod
    def _send_to_subscription(cls, message: str, sub: "Subscription") -> None:
        """Send notification to subscription's telegram_id if owner has telegram_send_subscriptions enabled."""
        if sub.telegram_id and sub.owner and sub.owner.telegram_send_subscriptions and sub.owner.telegram_token:
            asyncio.create_task(
                cls._send_telegram_message(
                    message,
                    token=sub.owner.telegram_token,
                    chat_id=sub.telegram_id,
                )
            )
        if sub.discord_webhook_url and sub.owner and sub.owner.discord_send_subscriptions:
            asyncio.create_task(cls._send_discord_message(message, sub.discord_webhook_url))

    @classmethod
    async def startup(cls) -> None:
        await cls._send_system_alerts("🚀 #CoreStarted")

    @classmethod
    async def locked_task(cls, task_name: str) -> None:
        message = f"🔒 <b>#LockedTask</b>\n➖➖➖➖➖\nTaskName: {task_name}\n"
        await cls._send_system_alerts(message)

    @classmethod
    async def system_log(cls, log_message: str) -> None:
        message = f"📝 <b>#SystemLog</b>\n➖➖➖➖➖\n{log_message}\n"
        await cls._send_system_alerts(message)

    @classmethod
    async def create_subscriptions(cls, subs: list["Subscription"], admin: "Admin") -> None:
        message = f"✨ <b>#SubCreated</b>\nCreatedBy: #{admin.username}\n"
        for sub in subs:
            message += (
                "➖➖➖➖➖\n"
                f"Username: {sub.username}\n"
                f"UsageLimit: {FormatUtils.byte_convert(sub.limit_usage)}\n"
                f"ExpireIn: {FormatUtils.time_convert(sub.limit_expire)}\n"
            )
        cls._send(message, owner=sub.owner)

    @classmethod
    async def delete_subscription(cls, sub: "Subscription", admin: "Admin") -> None:
        message = f"🗑 <b>#SubDeleted</b>\n➖➖➖➖➖\nUsername: {sub.username}\nDeletedBy: #{admin.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def delete_subscriptions(cls, subs: list["Subscription"], admin: "Admin") -> None:
        usernames = ", ".join(s.username for s in subs)
        message = (
            f"🗑 <b>#SubsDeleted</b>\n➖➖➖➖➖\nUsernames: {usernames}\nCount: {len(subs)}\nDeletedBy: #{admin.username}\n"
        )
        cls._send(message, owner=subs[0].owner if subs else None)

    @classmethod
    async def update_subscription(
        cls,
        sub: "Subscription",
        admin: "Admin",
        data: "SubscriptionUpdate",
    ) -> None:
        message = f"✏️ <b>#SubUpdated</b>\n➖➖➖➖➖\nUsername: {sub.username}\n"

        changes: list[str] = []
        if data.username is not None and data.username != sub.username:
            changes.append(f"  • Username: {sub.username} → {data.username}")
        if data.limit_usage is not None and data.limit_usage != sub.limit_usage:
            old_fmt = FormatUtils.byte_convert(sub.limit_usage) if sub.limit_usage else "0B"
            new_fmt = FormatUtils.byte_convert(data.limit_usage) if data.limit_usage else "0B"
            changes.append(f"  • UsageLimit: {old_fmt} → {new_fmt}")
        if data.limit_expire is not None and data.limit_expire != sub.limit_expire:
            old_fmt = FormatUtils.time_convert(sub.limit_expire) if sub.limit_expire else "Unlimited"
            new_fmt = FormatUtils.time_convert(data.limit_expire) if data.limit_expire else "Unlimited"
            changes.append(f"  • ExpireIn: {old_fmt} → {new_fmt}")
        if data.service_ids is not None and set(data.service_ids) != set(sub.service_ids):
            old_ids = ", ".join(map(str, sub.service_ids)) if sub.service_ids else "None"
            new_ids = ", ".join(map(str, data.service_ids)) if data.service_ids else "None"
            changes.append(f"  • Services: [{old_ids}] → [{new_ids}]")
        if data.note is not None and data.note != sub.note:
            changes.append("  • Note: Updated")

        if changes:
            message += "Changes:\n" + "\n".join(changes) + "\n"

        message += f"UpdatedBy: #{admin.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def enable_subscription(cls, sub: "Subscription", admin: "Admin") -> None:
        message = f"✅ <b>#SubEnabled</b>\n➖➖➖➖➖\nUsername: {sub.username}\nEnabledBy: #{admin.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def enable_subscriptions(cls, subs: list["Subscription"], admin: "Admin") -> None:
        usernames = ", ".join(s.username for s in subs)
        message = (
            f"✅ <b>#SubsEnabled</b>\n➖➖➖➖➖\nUsernames: {usernames}\nCount: {len(subs)}\nEnabledBy: #{admin.username}\n"
        )
        cls._send(message, owner=subs[0].owner if subs else None)

    @classmethod
    async def disable_subscription(cls, sub: "Subscription", admin: "Admin") -> None:
        message = f"🚫 <b>#SubDisabled</b>\n➖➖➖➖➖\nUsername: {sub.username}\nDisabledBy: #{admin.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def disable_subscriptions(cls, subs: list["Subscription"], admin: "Admin") -> None:
        usernames = ", ".join(s.username for s in subs)
        message = (
            f"🚫 <b>#SubsDisabled</b>\n➖➖➖➖➖\nUsernames: {usernames}\nCount: {len(subs)}\nDisabledBy: #{admin.username}\n"
        )
        cls._send(message, owner=subs[0].owner if subs else None)

    @classmethod
    async def reset_subscription_usage(cls, sub: "Subscription", admin: "Admin") -> None:
        message = f"🔄 <b>#SubUsageReset</b>\n➖➖➖➖➖\nUsername: {sub.username}\nResetBy: #{admin.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def reset_subscriptions_usage(cls, subs: list["Subscription"], admin: "Admin") -> None:
        usernames = ", ".join(s.username for s in subs)
        message = (
            f"🔄 <b>#SubsUsageReset</b>\n➖➖➖➖➖\nUsernames: {usernames}\nCount: {len(subs)}\nResetBy: #{admin.username}\n"
        )
        cls._send(message, owner=subs[0].owner if subs else None)

    @classmethod
    async def revoke_subscription(cls, sub: "Subscription", admin: "Admin") -> None:
        message = f"🔑 <b>#SubRevoked</b>\n➖➖➖➖➖\nUsername: {sub.username}\nRevokedBy: #{admin.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def revoke_subscriptions(cls, subs: list["Subscription"], admin: "Admin") -> None:
        usernames = ", ".join(s.username for s in subs)
        message = (
            f"🔑 <b>#SubsRevoked</b>\n➖➖➖➖➖\nUsernames: {usernames}\nCount: {len(subs)}\nRevokedBy: #{admin.username}\n"
        )
        cls._send(message, owner=subs[0].owner if subs else None)

    @classmethod
    async def expired_subscription(cls, sub: "Subscription") -> None:
        message = f"⏰ <b>#SubExpired</b>\n➖➖➖➖➖\nUsername: {sub.username}\n"
        cls._send(message, owner=sub.owner)
        cls._send_to_subscription(message, sub)

    @classmethod
    async def limited_subscription(cls, sub: "Subscription") -> None:
        message = f"📊 <b>#SubLimited</b>\n➖➖➖➖➖\nUsername: {sub.username}\n"
        cls._send(message, owner=sub.owner)
        cls._send_to_subscription(message, sub)

    @classmethod
    async def unreached_subscription(cls, sub: "Subscription") -> None:
        message = f"🔓 <b>#SubUnReached</b>\n➖➖➖➖➖\nUsername: {sub.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def activated_expire_subscription(cls, sub: "Subscription") -> None:
        message = f"⏳ <b>#SubExpireActivated</b>\n➖➖➖➖➖\nUsername: {sub.username}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def first_requested_subscription(cls, sub: "Subscription", client_agent: str) -> None:
        message = f"🆕 <b>#SubFirstRequested</b>\n➖➖➖➖➖\nUsername: {sub.username}\nClientAgent: {client_agent[:128]}\n"
        cls._send(message, owner=sub.owner)

    @classmethod
    async def subscription_expire_warning(cls, sub: "Subscription") -> None:
        message = f"⚠️ <b>#SubExpireWarning</b>\n➖➖➖➖➖\nUsername: {sub.username}"
        cls._send(message, owner=sub.owner)
        cls._send_to_subscription(message, sub)

    @classmethod
    async def subscription_usage_warning(cls, sub: "Subscription") -> None:
        message = f"⚠️ <b>#SubUsageWarning</b>\n➖➖➖➖➖\nUsername: {sub.username}"
        cls._send(message, owner=sub.owner)
        cls._send_to_subscription(message, sub)

    @classmethod
    async def auto_deleted_subscription(cls, sub: "Subscription") -> None:
        message = (
            f"🗑 <b>#SubAutoDeleted</b>\n"
            f"➖➖➖➖➖\n"
            f"Username: {sub.username}\n"
            f"AutoDeleteDays: {sub.auto_delete_days}\n"
            f"ReachedAt: {sub.reached_at.strftime('%Y-%m-%d %H:%M:%S') if sub.reached_at else 'N/A'}\n"
        )
        cls._send(message, owner=sub.owner)
        cls._send_to_subscription(message, sub)

    @classmethod
    async def admin_login(cls, admin: "Admin", client_address: str, client_agent: str) -> None:
        message = f"🔐 <b>#AdminLogin</b>\n➖➖➖➖➖\nAdmin: #{admin.username}\nClientAddress: {client_address}\nClientAgent: {client_agent[:128]}\n"
        cls._send(message, owner=admin)

    @classmethod
    async def admin_failed_login(
        cls, username: str, password: str, totp: Optional[str], client_address: str, client_agent: str
    ) -> None:
        message = (
            f"⚠️ <b>#AdminFailedLogin</b>\n"
            f"➖➖➖➖➖\n"
            f"Username: <code>{username}</code>\n"
            f"Password: <code>{password}</code>\n"
            f"TOTP: <code>{totp or 'N/A'}</code>\n"
            f"ClientAddress: {client_address}\n"
            f"ClientAgent: {client_agent[:128]}\n"
        )
        cls._send(message)

    @classmethod
    async def auto_renewal_executed(cls, sub: "Subscription") -> None:
        message = f"🔁 <b>#AutoRenewalExecuted</b>\n➖➖➖➖➖\nUsername: {sub.username}\n"
        cls._send(message, owner=sub.owner)
        cls._send_to_subscription(message, sub)

    @classmethod
    async def negative_usage_detected(cls, sub: "Subscription", usage: int, node: "Node") -> None:
        message = f"⚠️ <b>#NegativeUsageDetected</b>\n➖➖➖➖➖\nUsername: {sub.username}\nUsage: {usage}\nNode: {node.remark}"
        await cls._send_system_alerts(message)

    @classmethod
    async def negative_log_usage_detected(cls, sub: "Subscription", total_usage: int, previous_usage: int) -> None:
        message = f"⚠️ <b>#NegativeLogUsageDetected</b>\n➖➖➖➖➖\nUsername: {sub.username}\nTotalUsage: {total_usage}\nPreviousLoggedUsage: {previous_usage}"
        await cls._send_system_alerts(message)

    @classmethod
    async def unavailable_node_detected(cls, node: "Node") -> None:
        message = f"⚠️ <b>#UnavailableNodeDetected</b>\n➖➖➖➖➖\nNodeRemark: {node.remark}"
        await cls._send_system_alerts(message)
