from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def collect_capabilities(registry: Any | None = None) -> list[dict[str, Any]]:
    """Collect stable menu metadata from Core CapabilityProviders.

    Capability providers are an optional supplement to normal
    ``PluginMetadata.extra['menu_data']``.  A broken provider is isolated so
    one optional service cannot make the help image disappear.
    """

    if registry is None:
        return []
    getter = getattr(registry, "get_capability_providers", None)
    if getter is None:
        return []
    try:
        providers = getter() or {}
    except Exception:  # noqa: BLE001 - optional registry boundary
        return []
    result: list[dict[str, Any]] = []
    for provider_name, provider in sorted(
        providers.items(),
        key=lambda item: str(item[0]),
    ):
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
    """Build the old external-menu-compatible shape for local consumers."""

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
    """Build capability menu data from an already-loaded Core registry."""

    core = sys.modules.get("amia_core") or sys.modules.get("src.plugins.amia_core")
    registry = getattr(core, "registry", None) if core is not None else None
    return build_amiya_menu(collect_capabilities(registry))
