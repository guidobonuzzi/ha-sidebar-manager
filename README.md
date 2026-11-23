# Sidebar Manager for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/guidobonuzzi/ha-sidebar-manager/actions/workflows/validate.yml/badge.svg)](https://github.com/guidobonuzzi/ha-sidebar-manager/actions/workflows/validate.yml)

Manage the sidebar of **every** Home Assistant user from one admin-only panel, with no YAML involved.

Home Assistant lets each user reorder and hide their own sidebar items, but an administrator can't set them for anyone else. Sidebar Manager fills that gap.

## Features

- **Profiles** (e.g. *Family*, *Guests*, *Tablet*): set the order and visibility of every sidebar item once, then assign users to the profile.
- **Default dashboard** per profile.
- **Lock**: if a user changes their sidebar from their profile page, it's reset to their profile.
- **New items**: dashboards and panels added later can show up at the bottom (Home Assistant's behaviour) or stay hidden.
- **Default profile** for every user without a profile, including users created later.
- Changes reach the user's open sessions on every device immediately.
- UI in English and Italian.

## How it works

Since Home Assistant 2025.6, each user's sidebar settings are stored server-side in their profile. That's the same data the built-in *"Change the order and hide items from the sidebar"* editor writes. Sidebar Manager writes that data for every user of a profile, so:

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

Open **Sidebar Manager** in the sidebar (admins only).

### Profiles tab

1. Click **New** (or **Duplicate** an existing profile) and give it a name.
2. Drag the items or use the arrows to reorder them. Untick an item to hide it.
3. Optionally set a default dashboard, **Lock**, **New items** (show/hide) and **Default profile**.
4. Under **Users**, tick the users who get this profile. Ticking a user who is in another profile moves them.
5. Click **Save**: the layout is written to all its users right away.

**Delete** asks for a second click. The default profile can't be deleted until you untick *Default profile* and save.

### Users tab

Pick a profile for each user, or *None (Home Assistant default)*. The change applies immediately, and the table shows when a user gets the default profile.

### Rules

- A user has at most one profile. Users without one get the **default profile**, if there is one.
- When a user loses their profile (unassigned, or their profile is deleted), they get the default profile. If there's none, Home Assistant's default sidebar is restored.
- Unticking *Default profile* has the same effect on the users who were getting it as their default.
- **Lock** is applied after the fact: a user's change is reverted as soon as it's saved. It also applies after a restart.
- **New items: hide** treats every panel that wasn't listed when the profile was saved as new, and keeps it hidden for that profile's users.
- At startup, every profile is re-applied to its users to correct any drift.
- System users (e.g. Supervisor, add-ons) are always ignored.

The fixed bottom items (Settings, Notifications, Profile) can't be changed, same as with the built-in editor. Items marked *admin only* are never shown to non-admin users, whatever you choose.

## Requirements

Home Assistant **2025.6** or newer.

## Upgrading from 0.1.0

0.1.0 stored a layout per user and kept only the *locked* ones. On first start, 0.2.0 migrates its data automatically: every user who had a locked layout gets a locked profile named after them, with the same layout and default dashboard, and is assigned to it. Users who had an unlocked layout keep it in their own settings and get no profile.

The `sidebar_manager/get`, `save` and `reset` WebSocket commands were removed: see below.

The integration uses Home Assistant's internal frontend user-data storage (`frontend.storage`). If a future Home Assistant release changes it, please open an issue.

## WebSocket API

Every command requires an admin user.

| Command | Fields | Result |
|---|---|---|
| `sidebar_manager/profiles` | | `profiles`, `assignments`, `default_profile_id`, `users` (with `profile_id`, `effective_profile_id` and `source`: `assigned` / `default` / `none`) |
| `sidebar_manager/profile/save` | `profile_id?`, `name`, `panel_order`, `hidden_panels`, `default_panel?`, `lock?`, `new_items?` (`show`/`hide`), `is_default?`, `user_ids?` | `{"profile_id": ...}` |
| `sidebar_manager/profile/delete` | `profile_id` | |
| `sidebar_manager/assign` | `user_id`, `profile_id` (`null` to remove) | |

`profile/save` creates a profile when `profile_id` is missing, otherwise it replaces it (omitted optional fields take their defaults). With `user_ids`, exactly those users are assigned to the profile. `panel_order` should list every sidebar panel, because with `new_items: hide` any panel not in `panel_order` or `hidden_panels` is treated as new.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

## License

MIT
