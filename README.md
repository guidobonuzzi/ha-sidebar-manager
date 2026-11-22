# Sidebar Manager for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/guidobonuzzi/ha-sidebar-manager/actions/workflows/validate.yml/badge.svg)](https://github.com/guidobonuzzi/ha-sidebar-manager/actions/workflows/validate.yml)

Manage the sidebar of **every** Home Assistant user from one admin-only panel, with no YAML involved.

Home Assistant lets each user reorder and hide their own sidebar items, but an administrator can't set them for anyone else. Sidebar Manager fills that gap.

## Features

- **Per-user layout**: choose the order and visibility of every sidebar item for each user.
- **Default dashboard** per user.
- **Lock**: if the user changes their sidebar from the profile page, it's reset to the admin-defined layout.
- **Copy layout from** another user, and **apply to several users** at once.
- **Restore default** for a user.
- Changes reach the user's open sessions on every device immediately.
- UI in English and Italian.

## How it works

Since Home Assistant 2025.6, each user's sidebar settings are stored server-side in their profile. That's the same data the built-in *"Change the order and hide items from the sidebar"* editor writes. Sidebar Manager writes that data for the selected user, so:

- the sidebar is rendered by Home Assistant itself: no DOM patching and no CSS hacks;
- nothing breaks if you uninstall it, because users simply keep their last layout.

> **This is not a security feature.** Hiding an item doesn't prevent access to its URL. To restrict access, make dashboards *admin only* and give users non-admin accounts.

## Installation

### HACS (recommended)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/guidobonuzzi/ha-sidebar-manager` as **Integration**.
2. Install **Sidebar Manager** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Sidebar Manager*.

### Manual

Copy `custom_components/sidebar_manager` into your `config/custom_components/` folder, restart, then add the integration.

## Usage

Open **Sidebar Manager** in the sidebar (admins only) and follow these steps:

1. Pick a user.
2. Drag the items or use the arrows to reorder them. Untick an item to hide it.
3. Optionally set a default dashboard, lock the layout, or apply it to other users.
4. Click **Save**.

The fixed bottom items (Settings, Notifications, Profile) can't be changed, same as with the built-in editor. Items marked *admin only* are never shown to non-admin users, whatever you choose.

## Requirements

Home Assistant **2025.6** or newer.

The integration uses Home Assistant's internal frontend user-data storage (`frontend.storage`). If a future Home Assistant release changes it, please open an issue.

## WebSocket API

Every command requires an admin user.

| Command | Fields |
|---|---|
| `sidebar_manager/get` | `user_id` |
| `sidebar_manager/save` | `user_ids`, `panel_order`, `hidden_panels`, `default_panel?`, `lock?` |
| `sidebar_manager/reset` | `user_id` |

## Development

```bash
pip install -r requirements_test.txt
pytest
```

## License

MIT
