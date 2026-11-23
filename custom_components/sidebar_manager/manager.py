"""Sidebar profiles, written to the native per-user sidebar settings."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
import uuid

from homeassistant.auth import EVENT_USER_ADDED, EVENT_USER_REMOVED
from homeassistant.auth.models import User
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.frontend.storage import async_user_store
from homeassistant.const import EVENT_PANELS_UPDATED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    FIXED_PANELS,
    NEW_ITEMS_HIDE,
    NEW_ITEMS_SHOW,
    STORAGE_KEY,
    STORAGE_VERSION,
    USER_DATA_CORE,
    USER_DATA_SIDEBAR,
)


class ProfileError(Exception):
    """A profile operation was rejected."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SidebarStore(Store[dict[str, Any]]):
    """Integration store, with migration from the 0.1.0 per-user layouts."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        if old_major_version != 1:
            raise NotImplementedError
        # v1: {"locked": {user_id: {"sidebar": {...}, "default_panel": ...}}}
        # Every locked user becomes a locked profile named after them.
        profiles: dict[str, dict[str, Any]] = {}
        assignments: dict[str, str] = {}
        for user_id, config in (old_data.get("locked") or {}).items():
            user = await self.hass.auth.async_get_user(user_id)
            if user is None or user.system_generated:
                continue
            sidebar = config.get("sidebar") or {}
            profile_id = uuid.uuid4().hex
            profiles[profile_id] = {
                "name": user.name or user_id,
                "panel_order": list(sidebar.get("panelOrder") or []),
                "hidden_panels": list(sidebar.get("hiddenPanels") or []),
                "default_panel": config.get("default_panel"),
                "lock": True,
                "new_items": NEW_ITEMS_SHOW,
                "is_default": False,
            }
            assignments[user_id] = profile_id
        return {"profiles": profiles, "assignments": assignments}


class SidebarManager:
    """Manage sidebar profiles and apply them to Home Assistant users.

    A profile's layout is written to the same per-user frontend storage the
    native "Change the order and hide items from the sidebar" editor uses, so
    Home Assistant renders it natively and open sessions update live.
    Each user gets their assigned profile, or the default profile if they
    have none. Users of locked profiles get the layout re-applied whenever
    it changes.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = SidebarStore(hass, STORAGE_VERSION, STORAGE_KEY)
        self.profiles: dict[str, dict[str, Any]] = {}
        # user_id -> profile_id
        self.assignments: dict[str, str] = {}
        self._watchers: dict[str, Callable[[], None]] = {}
        self._user_locks: dict[str, asyncio.Lock] = {}
        self._op_lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []

    # ---- lifecycle ---------------------------------------------------------

    async def async_load(self) -> None:
        """Load profiles, re-apply them to every user and start listening."""
        data = await self._store.async_load() or {}
        self.profiles = data.get("profiles", {})
        self.assignments = data.get("assignments", {})

        users = await self._async_users()
        valid = {user.id for user in users}
        stale = [
            user_id
            for user_id, profile_id in self.assignments.items()
            if user_id not in valid or profile_id not in self.profiles
        ]
        for user_id in stale:
            self.assignments.pop(user_id)
        if stale:
            await self._async_save()

        bus = self.hass.bus
        self._listeners = [
            bus.async_listen(EVENT_USER_ADDED, self._handle_user_added),
            bus.async_listen(EVENT_USER_REMOVED, self._handle_user_removed),
            bus.async_listen(EVENT_PANELS_UPDATED, self._handle_panels_updated),
        ]

        async with self._op_lock:
            for user in users:
                if (profile := self._effective_profile(user.id)) is not None:
                    await self._async_write(user.id, profile)
            await self._async_sync_watchers(users)

    @callback
    def async_unload(self) -> None:
        """Stop listening to events and user stores."""
        for unsub in self._listeners:
            unsub()
        self._listeners.clear()
        for unsub in self._watchers.values():
            unsub()
        self._watchers.clear()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"profiles": self.profiles, "assignments": self.assignments}
        )

    # ---- queries -----------------------------------------------------------

    @property
    def default_profile_id(self) -> str | None:
        """Return the id of the default profile, if any."""
        return next(
            (pid for pid, profile in self.profiles.items() if profile["is_default"]),
            None,
        )

    def _effective_profile_id(self, user_id: str) -> str | None:
        if (profile_id := self.assignments.get(user_id)) in self.profiles:
            return profile_id
        return self.default_profile_id

    def _effective_profile(self, user_id: str) -> dict[str, Any] | None:
        if (profile_id := self._effective_profile_id(user_id)) is None:
            return None
        return self.profiles[profile_id]

    async def _async_users(self) -> list[User]:
        return [
            user
            for user in await self.hass.auth.async_get_users()
            if not user.system_generated
        ]

    async def async_get_state(self) -> dict[str, Any]:
        """Return profiles, assignments and each user's effective profile."""
        users = []
        for user in await self._async_users():
            assigned = self.assignments.get(user.id)
            effective = self._effective_profile_id(user.id)
            if assigned is not None:
                source = "assigned"
            elif effective is not None:
                source = "default"
            else:
                source = "none"
            users.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "is_admin": user.is_admin,
                    "is_active": user.is_active,
                    "profile_id": assigned,
                    "effective_profile_id": effective,
                    "source": source,
                }
            )
        return {
            "profiles": {pid: dict(p) for pid, p in self.profiles.items()},
            "assignments": dict(self.assignments),
            "default_profile_id": self.default_profile_id,
            "users": users,
        }

    # ---- changes -----------------------------------------------------------

    async def async_save_profile(
        self,
        profile_id: str | None,
        profile: dict[str, Any],
        user_ids: list[str] | None = None,
    ) -> str:
        """Create or update a profile and apply it to its users.

        With user_ids, those users are assigned to the profile (moving them
        from any other profile) and its other users are unassigned.
        """
        if profile_id is None:
            profile_id = uuid.uuid4().hex
        elif profile_id not in self.profiles:
            raise ProfileError("profile_not_found", f"Unknown profile {profile_id}")

        def mutate() -> None:
            if profile["is_default"]:
                for other in self.profiles.values():
                    other["is_default"] = False
            self.profiles[profile_id] = profile
            if user_ids is not None:
                for user_id, assigned in list(self.assignments.items()):
                    if assigned == profile_id and user_id not in user_ids:
                        del self.assignments[user_id]
                for user_id in user_ids:
                    self.assignments[user_id] = profile_id

        await self._async_change(mutate, changed_profile=profile_id)
        return profile_id

    async def async_delete_profile(self, profile_id: str) -> None:
        """Delete a profile; its users fall back to the default profile."""
        if (profile := self.profiles.get(profile_id)) is None:
            raise ProfileError("profile_not_found", f"Unknown profile {profile_id}")
        if profile["is_default"]:
            raise ProfileError(
                "profile_is_default",
                "The default profile can't be deleted: unset it as default first",
            )

        def mutate() -> None:
            del self.profiles[profile_id]
            for user_id, assigned in list(self.assignments.items()):
                if assigned == profile_id:
                    del self.assignments[user_id]

        await self._async_change(mutate)

    async def async_assign(self, user_id: str, profile_id: str | None) -> None:
        """Assign a user to a profile, or remove their assignment."""
        if profile_id is not None and profile_id not in self.profiles:
            raise ProfileError("profile_not_found", f"Unknown profile {profile_id}")

        def mutate() -> None:
            if profile_id is None:
                self.assignments.pop(user_id, None)
            else:
                self.assignments[user_id] = profile_id

        await self._async_change(mutate, force_user=user_id)

    async def _async_change(
        self,
        mutate: Callable[[], None],
        changed_profile: str | None = None,
        force_user: str | None = None,
    ) -> None:
        """Apply a change and update every user whose layout it affects.

        A user whose effective profile changed, or whose profile was edited,
        gets the new layout. A user left without a profile gets Home
        Assistant's default sidebar back.
        """
        async with self._op_lock:
            users = await self._async_users()
            before = {user.id: self._effective_profile_id(user.id) for user in users}
            mutate()
            await self._async_save()
            for user in users:
                old = before[user.id]
                new = self._effective_profile_id(user.id)
                if new is not None:
                    if new != old or new == changed_profile or user.id == force_user:
                        await self._async_write(user.id, self.profiles[new])
                elif old is not None or user.id == force_user:
                    await self._async_reset(user.id)
            await self._async_sync_watchers(users)

    # ---- user store --------------------------------------------------------

    def _sidebar_panels(self) -> set[str]:
        """Return the url paths of the panels that can appear in the sidebar."""
        return {
            url_path
            for url_path, panel in self.hass.data.get(DATA_PANELS, {}).items()
            if panel.sidebar_title
            and getattr(panel, "show_in_sidebar", True)
            and url_path not in FIXED_PANELS
        }

    def _layout(self, profile: dict[str, Any]) -> dict[str, list[str]]:
        """Return the native sidebar settings for a profile.

        The panel editor saves every existing panel in panel_order or
        hidden_panels, so any other panel is new since the profile was saved.
        """
        order = list(profile["panel_order"])
        hidden = list(profile["hidden_panels"])
        if profile.get("new_items") == NEW_ITEMS_HIDE:
            known = set(order) | set(hidden)
            hidden += sorted(self._sidebar_panels() - known)
        return {"panelOrder": order, "hiddenPanels": hidden}

    def _user_lock(self, user_id: str) -> asyncio.Lock:
        return self._user_locks.setdefault(user_id, asyncio.Lock())

    async def _async_write(self, user_id: str, profile: dict[str, Any]) -> None:
        """Write a profile's layout to a user store, only where it differs."""
        sidebar = self._layout(profile)
        default_panel = profile.get("default_panel")
        async with self._user_lock(user_id):
            store = await async_user_store(self.hass, user_id)
            if store.data.get(USER_DATA_SIDEBAR) != sidebar:
                await store.async_set_item(USER_DATA_SIDEBAR, sidebar)
            core = dict(store.data.get(USER_DATA_CORE) or {})
            if core.get("default_panel") != default_panel:
                if default_panel:
                    core["default_panel"] = default_panel
                else:
                    core.pop("default_panel", None)
                await store.async_set_item(USER_DATA_CORE, core)

    async def _async_reset(self, user_id: str) -> None:
        """Restore Home Assistant's default sidebar for a user."""
        async with self._user_lock(user_id):
            store = await async_user_store(self.hass, user_id)
            if store.data.get(USER_DATA_SIDEBAR) is not None:
                await store.async_set_item(USER_DATA_SIDEBAR, None)
            core = dict(store.data.get(USER_DATA_CORE) or {})
            if "default_panel" in core:
                core.pop("default_panel")
                await store.async_set_item(USER_DATA_CORE, core)

    # ---- lock enforcement --------------------------------------------------

    async def _async_sync_watchers(self, users: list[User]) -> None:
        """Watch the store of every user whose effective profile is locked."""
        wanted = {
            user.id
            for user in users
            if (profile := self._effective_profile(user.id)) is not None
            and profile["lock"]
        }
        for user_id in set(self._watchers) - wanted:
            self._unwatch(user_id)
        for user_id in wanted - set(self._watchers):
            await self._async_watch(user_id)

    async def _async_watch(self, user_id: str) -> None:
        store = await async_user_store(self.hass, user_id)

        @callback
        def _changed() -> None:
            self.hass.async_create_task(self._async_enforce(user_id))

        self._watchers[user_id] = store.async_subscribe(None, _changed)

    def _unwatch(self, user_id: str) -> None:
        if (unsub := self._watchers.pop(user_id, None)) is not None:
            unsub()

    async def _async_enforce(self, user_id: str) -> None:
        profile = self._effective_profile(user_id)
        if profile is not None and profile["lock"]:
            await self._async_write(user_id, profile)

    # ---- events ------------------------------------------------------------

    @callback
    def _handle_user_added(self, event: Event) -> None:
        self.hass.async_create_task(self._async_user_added(event.data["user_id"]))

    async def _async_user_added(self, user_id: str) -> None:
        user = await self.hass.auth.async_get_user(user_id)
        if user is None or user.system_generated:
            return
        async with self._op_lock:
            if (profile := self._effective_profile(user_id)) is not None:
                await self._async_write(user_id, profile)
                if profile["lock"] and user_id not in self._watchers:
                    await self._async_watch(user_id)

    @callback
    def _handle_user_removed(self, event: Event) -> None:
        self.hass.async_create_task(self._async_user_removed(event.data["user_id"]))

    async def _async_user_removed(self, user_id: str) -> None:
        async with self._op_lock:
            self._unwatch(user_id)
            self._user_locks.pop(user_id, None)
            if self.assignments.pop(user_id, None) is not None:
                await self._async_save()

    @callback
    def _handle_panels_updated(self, event: Event) -> None:
        if any(p.get("new_items") == NEW_ITEMS_HIDE for p in self.profiles.values()):
            self.hass.async_create_task(self._async_panels_updated())

    async def _async_panels_updated(self) -> None:
        """Keep panels added after a profile was saved hidden, if asked to."""
        async with self._op_lock:
            for user in await self._async_users():
                profile = self._effective_profile(user.id)
                if profile is not None and profile.get("new_items") == NEW_ITEMS_HIDE:
                    await self._async_write(user.id, profile)
