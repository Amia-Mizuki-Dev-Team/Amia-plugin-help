from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def normalize_message_segments(message: Any) -> list[dict[str, Any]]:
    """Normalize Release009 string/array message forms without losing segments."""

    if isinstance(message, str):
        return [{"type": "text", "data": {"text": message}}]
    if hasattr(message, "type") and hasattr(message, "data"):
        return [{
            "type": str(getattr(message, "type")),
            "data": dict(getattr(message, "data") or {}),
        }]
    if isinstance(message, Mapping):
        if "type" in message:
            return [{"type": str(message["type"]), "data": dict(message.get("data") or {})}]
        return [{"type": "text", "data": {"text": str(message)}}]
    if isinstance(message, Sequence) and not isinstance(message, (bytes, bytearray)):
        result: list[dict[str, Any]] = []
        for item in message:
            result.extend(normalize_message_segments(item))
        return result
    return [{"type": "text", "data": {"text": str(message)}}]


def safe_local_media_path(media_root: str | Path, candidate: str | Path) -> Path:
    """Resolve a local image path and reject traversal or absolute input."""

    root = Path(media_root).expanduser().resolve()
    relative = Path(candidate)
    if relative.is_absolute():
        raise ValueError("absolute media paths are not allowed")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("media path escapes configured root") from exc
    return resolved


def _button_payload(button: Mapping[str, Any], media_root: str | Path | None) -> dict[str, Any]:
    item = {str(key): value for key, value in button.items()}
    local_image = item.pop("local_image", None)
    if local_image is not None:
        if media_root is None:
            raise ValueError("media_root is required for local keyboard images")
        item["local_image"] = str(safe_local_media_path(media_root, str(local_image)))
    render_data = dict(item.get("render_data") or {})
    label = str(render_data.get("label") or item.get("label") or "帮助")
    render_data.setdefault("label", label)
    render_data.setdefault("visited_label", label)
    item["render_data"] = render_data
    action = dict(item.get("action") or {})
    action.setdefault("type", 2)
    action.setdefault("data", "")
    item["action"] = action
    return item


def build_markdown_keyboard_payload(
    markdown: str,
    buttons: Sequence[Sequence[Mapping[str, Any]]] | None = None,
    *,
    media_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build an offline-checkable Gensokyo Markdown + Keyboard payload."""

    payload: dict[str, Any] = {"markdown": {"content": str(markdown)}}
    if buttons:
        payload["keyboard"] = {
            "content": {
                "rows": [
                    {"buttons": [_button_payload(button, media_root) for button in row]}
                    for row in buttons
                ]
            }
        }
    return payload


def strip_markdown(markdown: str) -> str:
    """Conservative text fallback when Markdown/Keyboard cannot be delivered."""

    value = re.sub(r"!\[[^]]*\]\([^)]*\)", "", str(markdown))
    value = re.sub(r"[*_`#>]", "", value)
    return value.strip()


def build_help_outbound(
    markdown: str,
    buttons: Sequence[Sequence[Mapping[str, Any]]] | None = None,
    *,
    supports_markdown: bool,
    supports_keyboard: bool,
    media_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return structured output or safe text degradation for Release009."""

    if not supports_markdown:
        return {"mode": "text", "message": strip_markdown(markdown), "degraded": True}
    if buttons and not supports_keyboard:
        return {"mode": "markdown", "message": {"markdown": {"content": markdown}}, "degraded": True}
    return {
        "mode": "markdown_keyboard" if buttons else "markdown",
        "message": build_markdown_keyboard_payload(markdown, buttons, media_root=media_root),
        "degraded": False,
    }
