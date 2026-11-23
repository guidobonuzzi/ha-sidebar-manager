# Changelog

## 0.2.0

### Added
- **Profiles**: define named sidebar layouts (order, hidden items, default dashboard) and assign users to them. Saving a profile updates all its users immediately.
- **Default profile**, applied to every user without a profile, including users created later.
- **New items** option per profile: panels added after the profile was saved can show up at the bottom or stay hidden.
- Panel with two tabs: *Profiles* (list and editor with New, Duplicate and Delete) and *Users* (profile per user, applied immediately). The two columns stack on narrow screens.
- Profiles are re-applied at startup, users removed from Home Assistant lose their assignment, and system users are ignored.

### Changed
- Lock now applies per profile, to all its users.
- WebSocket API: `sidebar_manager/profiles`, `profile/save`, `profile/delete` and `assign` replace `get`, `save` and `reset`.
- Storage version 2. Data from 0.1.0 is migrated automatically: each user with a locked layout gets a locked profile named after them.

## 0.1.0

- First release: per-user sidebar order, visibility, default dashboard and lock, from an admin-only panel.
