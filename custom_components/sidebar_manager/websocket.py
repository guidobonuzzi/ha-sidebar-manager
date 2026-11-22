"""Websocket API for Sidebar Manager (admin only)."""

from __future__ import annotations

from typing import Any

try:  # Home Assistant 2026.12+ replaced voluptuous with probatio
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .manager import SidebarManager


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register websocket commands."""
    websocket_api.async_register_command(hass, ws_get)
    websocket_api.async_register_command(hass, ws_save)
    websocket_api.async_register_command(hass, ws_reset)


def _manager(hass: HomeAssistant, connection, msg) -> SidebarManager | None:
    manager: SidebarManager | None = hass.data.get(DOMAIN)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Sidebar Manager is not loaded")
    return manager


async def _valid_users(hass: HomeAssistant, connection, msg, user_ids: list[str]) -> bool:
    for user_id in user_ids:
        user = await hass.auth.async_get_user(user_id)
        if user is None or user.system_generated:
            connection.send_error(msg["id"], "user_not_found", f"Unknown user {user_id}")
            return False
    return True


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/get", vol.Required("user_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_get(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Return the sidebar settings of a user."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if not await _valid_users(hass, connection, msg, [msg["user_id"]]):
        return
    connection.send_result(msg["id"], await manager.async_get(msg["user_id"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/save",
        vol.Required("user_ids"): [str],
        vol.Required("panel_order"): [str],
        vol.Required("hidden_panels"): [str],
        vol.Optional("default_panel"): vol.Any(str, None),
        vol.Optional("lock", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Save sidebar settings for one or more users."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if not await _valid_users(hass, connection, msg, msg["user_ids"]):
        return
    for user_id in msg["user_ids"]:
        await manager.async_set(
            user_id,
            msg["panel_order"],
            msg["hidden_panels"],
            msg.get("default_panel"),
            msg["lock"],
        )
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/reset", vol.Required("user_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_reset(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Restore the default sidebar for a user."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if not await _valid_users(hass, connection, msg, [msg["user_id"]]):
        return
    await manager.async_reset(msg["user_id"])
    connection.send_result(msg["id"])
