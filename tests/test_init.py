"""Tests for Sidebar Manager."""
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.frontend.storage import async_user_store
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sidebar_manager.const import DOMAIN, PANEL_URL_PATH


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert PANEL_URL_PATH in hass.data[DATA_PANELS]
    assert hass.data[DATA_PANELS][PANEL_URL_PATH].require_admin


async def test_save_get_reset(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    uid = hass_read_only_user.id

    await client.send_json_auto_id({
        "type": f"{DOMAIN}/save", "user_ids": [uid],
        "panel_order": ["lovelace", "map", "energy"], "hidden_panels": ["energy"],
        "default_panel": "map",
    })
    assert (await client.receive_json())["success"]

    store = await async_user_store(hass, uid)
    assert store.data["sidebar"] == {"panelOrder": ["lovelace", "map", "energy"], "hiddenPanels": ["energy"]}
    assert store.data["core"]["default_panel"] == "map"

    await client.send_json_auto_id({"type": f"{DOMAIN}/get", "user_id": uid})
    res = await client.receive_json()
    assert res["result"] == {"panel_order": ["lovelace", "map", "energy"], "hidden_panels": ["energy"], "default_panel": "map", "locked": False}

    await client.send_json_auto_id({"type": f"{DOMAIN}/reset", "user_id": uid})
    assert (await client.receive_json())["success"]
    assert store.data["sidebar"] is None
    assert "default_panel" not in store.data["core"]


async def test_live_update_subscription(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_access_token, hass_read_only_user) -> None:
    """A user's open session receives the new sidebar immediately."""
    await _setup(hass)
    user_ws = await hass_ws_client(hass, hass_read_only_access_token)
    await user_ws.send_json_auto_id({"type": "frontend/subscribe_user_data", "key": "sidebar"})
    first = await user_ws.receive_json()  # initial event
    await user_ws.receive_json()  # result

    admin = await hass_ws_client(hass)
    await admin.send_json_auto_id({"type": f"{DOMAIN}/save", "user_ids": [hass_read_only_user.id], "panel_order": ["map"], "hidden_panels": []})
    assert (await admin.receive_json())["success"]
    event = await user_ws.receive_json()
    assert event["event"]["value"] == {"panelOrder": ["map"], "hiddenPanels": []}


async def test_non_admin_rejected(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": f"{DOMAIN}/get", "user_id": hass_admin_user.id})
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "unauthorized"


async def test_unknown_user(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/get", "user_id": "nope"})
    res = await client.receive_json()
    assert res["error"]["code"] == "user_not_found"


async def test_lock_enforced_and_persisted(hass: HomeAssistant, hass_ws_client, hass_read_only_user) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    uid = hass_read_only_user.id
    locked = {"panelOrder": ["map", "lovelace"], "hiddenPanels": ["history"]}
    await client.send_json_auto_id({
        "type": f"{DOMAIN}/save", "user_ids": [uid],
        "panel_order": locked["panelOrder"], "hidden_panels": locked["hiddenPanels"], "lock": True,
    })
    assert (await client.receive_json())["success"]

    store = await async_user_store(hass, uid)
    # user edits their own sidebar from the profile
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": ["map"]})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == locked

    # survives a reload
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": []})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == locked

    # unlocking stops enforcement
    await client.send_json_auto_id({
        "type": f"{DOMAIN}/save", "user_ids": [uid],
        "panel_order": ["map"], "hidden_panels": [], "lock": False,
    })
    assert (await client.receive_json())["success"]
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": ["map"]})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == {"panelOrder": [], "hiddenPanels": ["map"]}


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert PANEL_URL_PATH not in hass.data[DATA_PANELS]
    assert DOMAIN not in hass.data
