from __future__ import annotations

from collections.abc import Iterable, Mapping
import sys
from typing import Any

PICMENU_UPSTREAM = "lgc-NB2Dev/nonebot-plugin-picmenu-next"
PICMENU_COMMIT = "a0f8f729927c947e315f5719cfd1cd2720b2ee0c"


def picmenu_available() -> bool:
    try:
        from importlib.util import find_spec

        return find_spec("nonebot_plugin_picmenu_next") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def load_picmenu_plugin() -> Any | None:
    """Load the external menu core only when it is installed and discoverable."""

    if not picmenu_available():
        return None
    try:
        from nonebot import require

        # PicMenu declares Alconna as a required plugin.  Loading it first
        # keeps direct plugin imports and isolated test harnesses consistent
        # with a normal NoneBot plugin-directory startup.
        require("nonebot_plugin_alconna")
        return require("nonebot_plugin_picmenu_next")
    except Exception:  # noqa: BLE001 - optional external dependency boundary
        return None


def ensure_picmenu_loaded() -> Any | None:
    """Load PicMenu Next after installation without copying its implementation."""

    return load_picmenu_plugin()


def collect_capabilities(registry: Any | None = None) -> list[dict[str, Any]]:
    """Collect stable menu metadata from Core CapabilityProviders."""

    if registry is None:
        return []
    getter = getattr(registry, "get_capability_providers", None)
    if getter is None:
        return []
    result: list[dict[str, Any]] = []
    providers = getter()
    for provider_name, provider in sorted(providers.items()):
        method = getattr(provider, "get_supported_capabilities", None)
        if method is None:
            continue
        try:
            capabilities = sorted({str(value) for value in (method() or [])})
        except Exception:  # noqa: BLE001 - one provider cannot break Help
            continue
        result.append({"provider": str(provider_name), "capabilities": capabilities})
    return result


def build_amiya_menu(capabilities: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build external-menu-compatible data without copying PicMenu internals."""

    entries = []
    for item in capabilities:
        provider = str(item.get("provider", "unknown"))
        values = [str(value) for value in item.get("capabilities", [])]
        entries.append(
            {
                "id": provider,
                "name": provider,
                "type": "application",
                "func": [{"name": value} for value in values],
            }
        )
    return {"plugins": entries}


def build_registered_amiya_menu() -> dict[str, Any]:
    """Build menu data from an already-loaded Core registry, if available."""

    core = sys.modules.get("amia_core") or sys.modules.get("src.plugins.amia_core")
    registry = getattr(core, "registry", None) if core is not None else None
    return build_amiya_menu(collect_capabilities(registry))
