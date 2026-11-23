"""Websocket API for Sidebar Manager (admin only)."""

from __future__ import annotations

from typing import Any

try:  # Home Assistant 2026.11+ replaced voluptuous with probatio
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, NEW_ITEMS_HIDE, NEW_ITEMS_SHOW
from .manager import ProfileError, SidebarManager


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register websocket commands."""
    websocket_api.async_register_command(hass, ws_profiles)
    websocket_api.async_register_command(hass, ws_profile_save)
    websocket_api.async_register_command(hass, ws_profile_delete)
    websocket_api.async_register_command(hass, ws_assign)


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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/profiles"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_profiles(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Return profiles, assignments and the effective profile of each user."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    connection.send_result(msg["id"], await manager.async_get_state())


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/profile/save",
        vol.Optional("profile_id"): str,
        vol.Required("name"): str,
        vol.Required("panel_order"): [str],
        vol.Required("hidden_panels"): [str],
        vol.Optional("default_panel", default=None): vol.Any(str, None),
        vol.Optional("lock", default=False): bool,
        vol.Optional("new_items", default=NEW_ITEMS_SHOW): vol.In(
            [NEW_ITEMS_SHOW, NEW_ITEMS_HIDE]
        ),
        vol.Optional("is_default", default=False): bool,
        vol.Optional("user_ids"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_profile_save(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Create (without profile_id) or replace a profile."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if not (name := msg["name"].strip()):
        connection.send_error(msg["id"], "invalid_name", "The profile name is empty")
        return
    user_ids = msg.get("user_ids")
    if user_ids is not None and not await _valid_users(hass, connection, msg, user_ids):
        return
    profile = {
        "name": name,
        "panel_order": msg["panel_order"],
        "hidden_panels": msg["hidden_panels"],
        "default_panel": msg["default_panel"] or None,
        "lock": msg["lock"],
        "new_items": msg["new_items"],
        "is_default": msg["is_default"],
    }
    try:
        profile_id = await manager.async_save_profile(
            msg.get("profile_id"), profile, user_ids
        )
    except ProfileError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"], {"profile_id": profile_id})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/profile/delete", vol.Required("profile_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_profile_delete(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Delete a profile."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    try:
        await manager.async_delete_profile(msg["profile_id"])
    except ProfileError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/assign",
        vol.Required("user_id"): str,
        vol.Required("profile_id"): vol.Any(str, None),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_assign(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Assign a user to a profile, or remove the assignment (profile_id null)."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if not await _valid_users(hass, connection, msg, [msg["user_id"]]):
        return
    try:
        await manager.async_assign(msg["user_id"], msg["profile_id"])
    except ProfileError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"])
