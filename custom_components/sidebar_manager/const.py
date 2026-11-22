"""Constants for Sidebar Manager."""

from typing import Final

DOMAIN: Final = "sidebar_manager"
VERSION: Final = "0.1.0"

PANEL_URL_PATH: Final = "sidebar-manager"
PANEL_COMPONENT: Final = "sidebar-manager-panel"
PANEL_TITLE: Final = "Sidebar Manager"
PANEL_ICON: Final = "mdi:menu-open"

STATIC_URL: Final = "/sidebar_manager_static"

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1

# Keys of the frontend user data written by the native sidebar editor
USER_DATA_SIDEBAR: Final = "sidebar"
USER_DATA_CORE: Final = "core"
