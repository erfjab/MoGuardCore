import time
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from src.guard_node.clients.marzban import MarzbanUserResponse
from src.guard_node.clients.marzneshin import MarzneshinUserResponse
from src.guard_node.clients.rustneshin import RustneshinUserResponse

if TYPE_CHECKING:
    from src.db.models.subscription import Subscription
    from src.db.models.admin import Admin

UserResponse = MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse

CACHE_TTL = 3000


class AdminCacheManager:
    """
    Cache for admin data.
    Data is indexed by username and id for fast lookups.
    Cache expires after 5 minutes but is updated when admins are modified.
    Used primarily for JWT token verification.
    """

    def __init__(self):
        self._by_username: dict[str, "Admin"] = {}
        self._by_id: dict[int, "Admin"] = {}
        self._by_api_key: dict[str, "Admin"] = {}
        self._cached_at: float = 0.0

    def set_all(self, admins: list["Admin"]) -> None:
        """
        Store all admins in the cache.

        Args:
            admins: List of Admin objects to cache
        """
        self._by_username = {admin.username: admin for admin in admins}
        self._by_id = {admin.id: admin for admin in admins}
        self._by_api_key = {admin.api_key: admin for admin in admins if admin.api_key}
        self._cached_at = time.time()

    def get_by_username(self, username: str) -> Optional["Admin"]:
        """
        Get an admin by username.

        Args:
            username: The username of the admin

        Returns:
            Admin if found and cache is valid, None otherwise
        """
        if self.is_expired():
            return None
        return self._by_username.get(username)

    def get_by_id(self, admin_id: int) -> Optional["Admin"]:
        """
        Get an admin by ID.

        Args:
            admin_id: The ID of the admin

        Returns:
            Admin if found and cache is valid, None otherwise
        """
        if self.is_expired():
            return None
        return self._by_id.get(admin_id)

    def get_by_api_key(self, api_key: str) -> Optional["Admin"]:
        """
        Get an admin by API key.

        Args:
            api_key: The API key of the admin

        Returns:
            Admin if found and cache is valid, None otherwise
        """
        if self.is_expired():
            return None
        return self._by_api_key.get(api_key)

    def is_expired(self) -> bool:
        """Check if the cache is expired (older than 5 minutes)"""
        return time.time() - self._cached_at > CACHE_TTL

    def is_valid(self) -> bool:
        """Check if cache is valid (exists and not expired)"""
        return bool(self._by_username) and not self.is_expired()

    def get_cache_age(self) -> Optional[float]:
        """Get the age of the cache in seconds"""
        if not self._by_username:
            return None
        return time.time() - self._cached_at

    def update(self, admin: "Admin") -> None:
        """
        Update a single admin in the cache.

        Args:
            admin: The Admin object to update
        """
        # Remove old api_key if it changed
        old_admin = self._by_id.get(admin.id)
        if old_admin and old_admin.api_key and old_admin.api_key != admin.api_key:
            self._by_api_key.pop(old_admin.api_key, None)

        self._by_username[admin.username] = admin
        self._by_id[admin.id] = admin
        if admin.api_key:
            self._by_api_key[admin.api_key] = admin

    def remove(self, admin: "Admin") -> None:
        """
        Remove an admin from the cache.

        Args:
            admin: The Admin object to remove
        """
        self._by_username.pop(admin.username, None)
        self._by_id.pop(admin.id, None)
        if admin.api_key:
            self._by_api_key.pop(admin.api_key, None)

    def clear(self) -> None:
        """Clear all cached admins"""
        self._by_username.clear()
        self._by_id.clear()
        self._by_api_key.clear()
        self._cached_at = 0.0


LINKS: dict[int, list[str]] = {}
AdminCache = AdminCacheManager()
