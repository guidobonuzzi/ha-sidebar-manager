"""Read/write the native sidebar settings of any user and enforce locked ones."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.frontend.storage import async_user_store
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION, USER_DATA_CORE, USER_DATA_SIDEBAR

_LOGGER = logging.getLogger(__name__)


class SidebarManager:
    """Manage the sidebar of Home Assistant users.

    The sidebar layout is written to the same per-user frontend storage the
    native "Change the order and hide items from the sidebar" editor uses, so
    Home Assistant renders it natively and open sessions update live.
    Locked users get their layout re-applied whenever it changes.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # user_id -> {"sidebar": {...}, "default_panel": str | None}
        self._locked: dict[str, dict[str, Any]] = {}
        self._unsubs: dict[str, Callable[[], None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def async_load(self) -> None:
        """Load locked layouts and start enforcing them."""
        data = await self._store.async_load() or {}
        self._locked = data.get("locked", {})
        for user_id in list(self._locked):
            if await self.hass.auth.async_get_user(user_id) is None:
                self._locked.pop(user_id)
                continue
            await self._async_watch(user_id)
            await self._async_enforce(user_id)

    @callback
    def async_unload(self) -> None:
        """Stop watching user stores."""
        for unsub in self._unsubs.values():
            unsub()
        self._unsubs.clear()

    async def _async_save(self) -> None:
        await self._store.async_save({"locked": self._locked})

    async def async_get(self, user_id: str) -> dict[str, Any]:
        """Return the sidebar settings of a user."""
        store = await async_user_store(self.hass, user_id)
        sidebar = store.data.get(USER_DATA_SIDEBAR) or {}
        core = store.data.get(USER_DATA_CORE) or {}
        return {
            "panel_order": sidebar.get("panelOrder"),
            "hidden_panels": sidebar.get("hiddenPanels"),
            "default_panel": core.get("default_panel"),
            "locked": user_id in self._locked,
        }

    async def async_set(
        self,
        user_id: str,
        panel_order: list[str],
        hidden_panels: list[str],
        default_panel: str | None,
        lock: bool,
    ) -> None:
        """Write the sidebar settings of a user."""
        config = {
            "sidebar": {"panelOrder": panel_order, "hiddenPanels": hidden_panels},
            "default_panel": default_panel,
        }
        if lock:
            self._locked[user_id] = config
            await self._async_watch(user_id)
        else:
            self._unwatch(user_id)
            self._locked.pop(user_id, None)
        await self._async_save()
        await self._async_write(user_id, config)

    async def async_reset(self, user_id: str) -> None:
        """Restore Home Assistant's default sidebar for a user."""
        self._unwatch(user_id)
        self._locked.pop(user_id, None)
        await self._async_save()
        store = await async_user_store(self.hass, user_id)
        await store.async_set_item(USER_DATA_SIDEBAR, None)
        core = dict(store.data.get(USER_DATA_CORE) or {})
        if "default_panel" in core:
            core.pop("default_panel")
            await store.async_set_item(USER_DATA_CORE, core)

    async def _async_write(self, user_id: str, config: dict[str, Any]) -> None:
        """Write a config to the user store, only where it differs."""
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            store = await async_user_store(self.hass, user_id)
            if store.data.get(USER_DATA_SIDEBAR) != config["sidebar"]:
                await store.async_set_item(USER_DATA_SIDEBAR, config["sidebar"])
            core = dict(store.data.get(USER_DATA_CORE) or {})
            default_panel = config.get("default_panel")
            if core.get("default_panel") != default_panel:
                if default_panel:
                    core["default_panel"] = default_panel
                else:
                    core.pop("default_panel", None)
                await store.async_set_item(USER_DATA_CORE, core)

    async def _async_enforce(self, user_id: str) -> None:
        if (config := self._locked.get(user_id)) is not None:
            await self._async_write(user_id, config)

    async def _async_watch(self, user_id: str) -> None:
        if user_id in self._unsubs:
            return
        store = await async_user_store(self.hass, user_id)

        @callback
        def _changed() -> None:
            if user_id in self._locked:
                self.hass.async_create_task(self._async_enforce(user_id))

        self._unsubs[user_id] = store.async_subscribe(None, _changed)

    def _unwatch(self, user_id: str) -> None:
        if (unsub := self._unsubs.pop(user_id, None)) is not None:
            unsub()
