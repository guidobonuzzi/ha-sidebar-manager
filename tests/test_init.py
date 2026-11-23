"""Tests for Sidebar Manager."""
from typing import Any

from homeassistant.components import frontend
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.frontend.storage import async_user_store
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sidebar_manager.const import DOMAIN, PANEL_URL_PATH, STORAGE_KEY

LAYOUT = {"panelOrder": ["map", "lovelace", "energy"], "hiddenPanels": ["energy"]}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _ws(client, type_: str, **fields: Any) -> dict:
    await client.send_json_auto_id({"type": f"{DOMAIN}/{type_}", **fields})
    return await client.receive_json()


async def _save(client, **fields: Any) -> str:
    fields.setdefault("name", "Family")
    fields.setdefault("panel_order", LAYOUT["panelOrder"])
    fields.setdefault("hidden_panels", LAYOUT["hiddenPanels"])
    res = await _ws(client, "profile/save", **fields)
    assert res["success"], res
    return res["result"]["profile_id"]


async def _assign(client, user_id: str, profile_id: str | None) -> None:
    res = await _ws(client, "assign", user_id=user_id, profile_id=profile_id)
    assert res["success"], res


async def _state(client) -> dict:
    res = await _ws(client, "profiles")
    assert res["success"], res
    return res["result"]


def _user_state(state: dict, user_id: str) -> dict:
    return next(u for u in state["users"] if u["id"] == user_id)


async def test_config_flow(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert PANEL_URL_PATH in hass.data[DATA_PANELS]
    assert hass.data[DATA_PANELS][PANEL_URL_PATH].require_admin


async def test_profile_crud(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)

    pid = await _save(client, name=" Family ", default_panel="map", lock=True, new_items="hide")
    state = await _state(client)
    assert state["profiles"] == {
        pid: {
            "name": "Family",
            "panel_order": LAYOUT["panelOrder"],
            "hidden_panels": LAYOUT["hiddenPanels"],
            "default_panel": "map",
            "lock": True,
            "new_items": "hide",
            "is_default": False,
        }
    }
    assert state["default_profile_id"] is None

    assert await _save(client, profile_id=pid, name="Guests", panel_order=["map"], hidden_panels=[]) == pid
    profile = (await _state(client))["profiles"][pid]
    assert profile["name"] == "Guests"
    assert profile["panel_order"] == ["map"]
    assert profile["lock"] is False

    res = await _ws(client, "profile/save", profile_id="nope", name="X", panel_order=[], hidden_panels=[])
    assert res["error"]["code"] == "profile_not_found"
    res = await _ws(client, "profile/save", name="  ", panel_order=[], hidden_panels=[])
    assert res["error"]["code"] == "invalid_name"
    res = await _ws(client, "profile/save", name="X", panel_order=[], hidden_panels=[], new_items="maybe")
    assert not res["success"]

    assert (await _ws(client, "profile/delete", profile_id=pid))["success"]
    assert (await _state(client))["profiles"] == {}
    res = await _ws(client, "profile/delete", profile_id=pid)
    assert res["error"]["code"] == "profile_not_found"


async def test_assign_writes_user_store(hass: HomeAssistant, hass_ws_client, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    uid = hass_read_only_user.id
    pid = await _save(client, default_panel="map")

    await _assign(client, uid, pid)
    store = await async_user_store(hass, uid)
    assert store.data["sidebar"] == LAYOUT
    assert store.data["core"]["default_panel"] == "map"

    state = await _state(client)
    assert state["assignments"] == {uid: pid}
    assert _user_state(state, uid) | {"name": None} == {
        "id": uid, "name": None, "is_admin": False, "is_active": True,
        "profile_id": pid, "effective_profile_id": pid, "source": "assigned",
    }

    res = await _ws(client, "assign", user_id=uid, profile_id="nope")
    assert res["error"]["code"] == "profile_not_found"
    res = await _ws(client, "assign", user_id="nope", profile_id=pid)
    assert res["error"]["code"] == "user_not_found"


async def test_save_with_user_ids_moves_users(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    admin, ro = hass_admin_user.id, hass_read_only_user.id
    a = await _save(client, name="A", user_ids=[admin, ro])
    b = await _save(client, name="B", panel_order=["lovelace"], hidden_panels=[], user_ids=[ro])

    assert (await _state(client))["assignments"] == {admin: a, ro: b}
    assert (await async_user_store(hass, ro)).data["sidebar"] == {"panelOrder": ["lovelace"], "hiddenPanels": []}

    # unticking a user in the profile editor unassigns them
    await _save(client, profile_id=a, name="A", user_ids=[])
    assert (await _state(client))["assignments"] == {ro: b}
    assert (await async_user_store(hass, admin)).data["sidebar"] is None

    res = await _ws(client, "profile/save", name="C", panel_order=[], hidden_panels=[], user_ids=["nope"])
    assert res["error"]["code"] == "user_not_found"


async def test_profile_update_applies_to_all_users(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    users = [hass_admin_user.id, hass_read_only_user.id]
    pid = await _save(client, user_ids=users)

    new = {"panelOrder": ["history", "map"], "hiddenPanels": ["map"]}
    await _save(client, profile_id=pid, panel_order=new["panelOrder"], hidden_panels=new["hiddenPanels"], default_panel="history", user_ids=users)
    for uid in users:
        store = await async_user_store(hass, uid)
        assert store.data["sidebar"] == new
        assert store.data["core"]["default_panel"] == "history"


async def test_unassign_applies_default_or_reset(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    uid = hass_read_only_user.id
    store = await async_user_store(hass, uid)
    pid = await _save(client, default_panel="map")

    # no default profile: Home Assistant's default sidebar
    await _assign(client, uid, pid)
    await _assign(client, uid, None)
    assert store.data["sidebar"] is None
    assert "default_panel" not in store.data["core"]
    assert _user_state(await _state(client), uid)["source"] == "none"

    # with a default profile: the default profile
    default = {"panelOrder": ["lovelace"], "hiddenPanels": ["map"]}
    did = await _save(client, name="Default", panel_order=default["panelOrder"], hidden_panels=default["hiddenPanels"], is_default=True)
    assert store.data["sidebar"] == default  # unassigned users get it right away
    assert (await async_user_store(hass, hass_admin_user.id)).data["sidebar"] == default
    await _assign(client, uid, pid)
    assert store.data["sidebar"] == LAYOUT
    await _assign(client, uid, None)
    assert store.data["sidebar"] == default
    assert "default_panel" not in store.data["core"]
    user = _user_state(await _state(client), uid)
    assert (user["profile_id"], user["effective_profile_id"], user["source"]) == (None, did, "default")

    # unsetting the default flag leaves its users without a profile
    await _save(client, profile_id=did, name="Default", panel_order=default["panelOrder"], hidden_panels=default["hiddenPanels"], is_default=False)
    assert store.data["sidebar"] is None


async def test_single_default_profile(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    a = await _save(client, name="A", is_default=True)
    b = await _save(client, name="B", is_default=True)
    state = await _state(client)
    assert state["default_profile_id"] == b
    assert state["profiles"][a]["is_default"] is False


async def test_delete_profile(hass: HomeAssistant, hass_ws_client, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    uid = hass_read_only_user.id
    store = await async_user_store(hass, uid)
    pid = await _save(client, user_ids=[uid])
    assert store.data["sidebar"] == LAYOUT

    assert (await _ws(client, "profile/delete", profile_id=pid))["success"]
    assert store.data["sidebar"] is None
    assert (await _state(client))["assignments"] == {}

    # users of a deleted profile get the default one
    did = await _save(client, name="Default", panel_order=["map"], hidden_panels=[], is_default=True)
    pid = await _save(client, user_ids=[uid])
    assert (await _ws(client, "profile/delete", profile_id=pid))["success"]
    assert store.data["sidebar"] == {"panelOrder": ["map"], "hiddenPanels": []}

    # the default profile can't be deleted
    res = await _ws(client, "profile/delete", profile_id=did)
    assert res["error"]["code"] == "profile_is_default"


async def test_default_profile_new_and_removed_users(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    await _save(client, is_default=True, lock=True)

    user = await hass.auth.async_create_user("Newcomer")
    await hass.async_block_till_done()
    store = await async_user_store(hass, user.id)
    assert store.data["sidebar"] == LAYOUT
    # the default profile's lock applies to them too
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": []})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == LAYOUT

    system = await hass.auth.async_create_system_user("Robot")
    await hass.async_block_till_done()
    assert "sidebar" not in (await async_user_store(hass, system.id)).data
    assert system.id not in {u["id"] for u in (await _state(client))["users"]}

    pid = await _save(client, name="Other", user_ids=[user.id])
    assert (await _state(client))["assignments"] == {user.id: pid}
    await hass.auth.async_remove_user(user)
    await hass.async_block_till_done()
    assert (await _state(client))["assignments"] == {}


async def test_lock_enforced_after_reload(hass: HomeAssistant, hass_ws_client, hass_read_only_user) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    uid = hass_read_only_user.id
    pid = await _save(client, lock=True, user_ids=[uid])

    store = await async_user_store(hass, uid)
    # the user edits their own sidebar from the profile page
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": ["map"]})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == LAYOUT

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": []})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == LAYOUT

    # unlocking stops enforcement
    await _save(client, profile_id=pid, lock=False, user_ids=[uid])
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": ["map"]})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == {"panelOrder": [], "hiddenPanels": ["map"]}


async def test_startup_reapplies_profiles(hass: HomeAssistant, hass_storage, hass_read_only_user) -> None:
    uid = hass_read_only_user.id
    hass_storage[STORAGE_KEY] = {
        "version": 2, "minor_version": 1, "key": STORAGE_KEY,
        "data": {
            "profiles": {"p1": {
                "name": "Family", "panel_order": LAYOUT["panelOrder"], "hidden_panels": LAYOUT["hiddenPanels"],
                "default_panel": None, "lock": False, "new_items": "show", "is_default": False,
            }},
            "assignments": {uid: "p1", "ghost": "p1"},
        },
    }
    store = await async_user_store(hass, uid)
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": []})

    await _setup(hass)
    assert store.data["sidebar"] == LAYOUT
    assert hass.data[DOMAIN].assignments == {uid: "p1"}


async def test_new_items_hide(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_user) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    hide_user, show_user = hass_read_only_user.id, hass_admin_user.id
    known = sorted(
        p for p, panel in hass.data[DATA_PANELS].items()
        if panel.sidebar_title and p not in ("profile", "config", "notfound")
    )
    await _save(client, name="Kids", panel_order=known, hidden_panels=[], new_items="hide", user_ids=[hide_user])
    await _save(client, name="Adults", panel_order=known, hidden_panels=[], new_items="show", user_ids=[show_user])
    hide_store = await async_user_store(hass, hide_user)
    show_store = await async_user_store(hass, show_user)
    assert hide_store.data["sidebar"] == {"panelOrder": known, "hiddenPanels": []}

    frontend.async_register_built_in_panel(
        hass, "iframe", sidebar_title="New dashboard", sidebar_icon="mdi:new-box", frontend_url_path="new-dashboard"
    )
    await hass.async_block_till_done()
    assert hide_store.data["sidebar"] == {"panelOrder": known, "hiddenPanels": ["new-dashboard"]}
    assert show_store.data["sidebar"] == {"panelOrder": known, "hiddenPanels": []}


async def test_migration_from_v1(hass: HomeAssistant, hass_ws_client, hass_storage, hass_read_only_user) -> None:
    uid = hass_read_only_user.id
    old = {"panelOrder": ["map", "lovelace"], "hiddenPanels": ["history"]}
    hass_storage[STORAGE_KEY] = {
        "version": 1, "minor_version": 1, "key": STORAGE_KEY,
        "data": {"locked": {
            uid: {"sidebar": old, "default_panel": "map"},
            "deleted-user": {"sidebar": old, "default_panel": None},
        }},
    }
    await _setup(hass)
    client = await hass_ws_client(hass)

    state = await _state(client)
    (pid, profile), = state["profiles"].items()
    assert profile == {
        "name": hass_read_only_user.name, "panel_order": old["panelOrder"], "hidden_panels": old["hiddenPanels"],
        "default_panel": "map", "lock": True, "new_items": "show", "is_default": False,
    }
    assert state["assignments"] == {uid: pid}
    assert hass_storage[STORAGE_KEY]["version"] == 2

    store = await async_user_store(hass, uid)
    assert store.data["sidebar"] == old
    await store.async_set_item("sidebar", {"panelOrder": [], "hiddenPanels": []})
    await hass.async_block_till_done()
    assert store.data["sidebar"] == old


async def test_non_admin_rejected(hass: HomeAssistant, hass_ws_client, hass_admin_user, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for type_, fields in [
        ("profiles", {}),
        ("profile/save", {"name": "X", "panel_order": [], "hidden_panels": []}),
        ("profile/delete", {"profile_id": "x"}),
        ("assign", {"user_id": hass_admin_user.id, "profile_id": None}),
    ]:
        res = await _ws(client, type_, **fields)
        assert not res["success"]
        assert res["error"]["code"] == "unauthorized"


async def test_live_update_subscription(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token, hass_read_only_user) -> None:
    """A user's open session receives the new sidebar immediately."""
    await _setup(hass)
    user_ws = await hass_ws_client(hass, hass_read_only_access_token)
    await user_ws.send_json_auto_id({"type": "frontend/subscribe_user_data", "key": "sidebar"})
    await user_ws.receive_json()  # initial event
    await user_ws.receive_json()  # result

    admin = await hass_ws_client(hass)
    pid = await _save(admin)
    await _assign(admin, hass_read_only_user.id, pid)
    event = await user_ws.receive_json()
    assert event["event"]["value"] == LAYOUT


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert PANEL_URL_PATH not in hass.data[DATA_PANELS]
    assert DOMAIN not in hass.data
