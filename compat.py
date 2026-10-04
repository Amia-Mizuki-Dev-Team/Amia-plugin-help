from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_CQ_RE = re.compile(r"\[CQ:(?P<type>[A-Za-z0-9_-]+)(?:,(?P<data>[^\]]*))?\]")


def _parse_cq_data(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    data: dict[str, str] = {}
    for item in raw.split(","):
        key, separator, value = item.partition("=")
        if separator:
            data[key] = value.replace("&#44;", ",").replace("&#91;", "[")
    return data


def _normalize_cq_text(message: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cursor = 0
    for match in _CQ_RE.finditer(message):
        if match.start() > cursor:
            result.append(
                {"type": "text", "data": {"text": message[cursor : match.start()]}}
            )
        result.append(
            {
                "type": match.group("type"),
                "data": _parse_cq_data(match.group("data")),
            }
        )
        cursor = match.end()
    if cursor < len(message):
        result.append({"type": "text", "data": {"text": message[cursor:]}})
    return result or [{"type": "text", "data": {"text": message}}]


def normalize_message_segments(message: Any) -> list[dict[str, Any]]:
    """Normalize string/array/map message forms without losing segments."""

    if isinstance(message, str):
        return _normalize_cq_text(message)
    if hasattr(message, "type") and hasattr(message, "data"):
        return [
            {
                "type": str(message.type),
                "data": dict(message.data or {}),
            }
        ]
    if isinstance(message, Mapping):
        if "type" in message:
            return [
                {
                    "type": str(message["type"]),
                    "data": dict(message.get("data") or {}),
                }
            ]
        return [{"type": "text", "data": {"text": str(message)}}]
    if isinstance(message, Sequence) and not isinstance(message, (bytes, bytearray)):
        result: list[dict[str, Any]] = []
        for item in message:
            result.extend(normalize_message_segments(item))
        return result
    return [{"type": "text", "data": {"text": str(message)}}]


def is_bot_mention(segment: Mapping[str, Any], bot_id: str | int | None) -> bool:
    """Recognize native and CQ @ segments without numeric coercion."""

    if str(segment.get("type", "")) != "at":
        return False
    data = dict(segment.get("data") or {})
    if data.get("bot") is True or str(data.get("bot", "")).lower() == "true":
        return True
    target = data.get("qq") or data.get("user_id") or data.get("id")
    if target is None or bot_id is None:
        return False
    return str(target) == str(bot_id)


def remove_bot_mentions(
    message: Any,
    bot_id: str | int | None,
) -> list[dict[str, Any]]:
    """Remove only @Bot segments and preserve all other message segments."""

    return [
        segment
        for segment in normalize_message_segments(message)
        if not is_bot_mention(segment, bot_id)
    ]


def build_file_segment_payload(
    path: str | Path,
    file_name: str | None = None,
) -> dict[str, Any]:
    """Build a Gensokyo file segment without exposing local secrets."""

    resolved = Path(path).expanduser().resolve()
    return {
        "type": "file",
        "data": {
            "file": resolved.as_uri(),
            "file_name": file_name or resolved.name,
        },
    }


def safe_local_media_path(media_root: str | Path, candidate: str | Path) -> Path:
    """Resolve a local image path and reject traversal or absolute input."""

    root = Path(media_root).expanduser().resolve()
    relative = Path(candidate)
    if relative.is_absolute():
        raise ValueError("absolute media paths are not allowed")  # noqa: TRY003
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("media path escapes configured root") from exc  # noqa: TRY003
    return resolved


def _button_payload(
    button: Mapping[str, Any],
    media_root: str | Path | None,
) -> dict[str, Any]:
    del media_root  # Kept in the public signature for compatibility.
    item = {str(key): value for key, value in button.items()}
    local_image = item.pop("local_image", None)
    if local_image is not None:
        # Images must be uploaded first and referenced from Markdown or a
        # supported render_data field; a local path is never sent to QQ.
        raise ValueError(  # noqa: TRY003
            "local keyboard images must be uploaded before building a payload"
        )
    render_data = dict(item.get("render_data") or {})
    label = str(render_data.get("label") or item.get("label") or "帮助")
    render_data.setdefault("label", label)
    render_data.setdefault("visited_label", label)
    render_data.setdefault("style", 0)
    item["render_data"] = render_data
    action = dict(item.get("action") or {})
    action.setdefault("type", 2)
    action.setdefault("permission", {"type": 2})
    action.setdefault("data", "")
    action.setdefault("enter", False)
    action.setdefault("reply", False)
    action.setdefault("unsupport_tips", "请手动发送按钮中的指令")
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


def build_button_fallback_text(
    buttons: Sequence[Sequence[Mapping[str, Any]]] | None = None,
) -> str:
    """Build executable command hints for clients that drop keyboard fields.

    NapCat can preserve the Markdown image while omitting the optional QQ
    keyboard from readback/rendering.  Keeping the action data in the visible
    message means every generated button still has an equivalent command,
    including pagination and return-navigation buttons.
    """

    if not buttons:
        return ""
    lines: list[str] = []
    for row in buttons:
        items: list[str] = []
        for button in row:
            action = button.get("action") or {}
            command = str(action.get("data") or "").strip()
            if not command:
                continue
            render_data = button.get("render_data") or {}
            label = str(
                render_data.get("label")
                or button.get("label")
                or "按钮"
            ).strip()
            items.append(f"{label}：{command}")
        if items:
            lines.append(" · ".join(items))
    if not lines:
        return ""
    return "按钮命令（键盘不可用时发送）：\n" + "\n".join(lines)


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
    """Return structured output or safe text degradation."""

    if not supports_markdown:
        return {"mode": "text", "message": strip_markdown(markdown), "degraded": True}
    if buttons and not supports_keyboard:
        fallback = build_button_fallback_text(buttons)
        content = f"{markdown}\n\n{fallback}" if fallback else markdown
        return {
            "mode": "markdown",
            "message": {"markdown": {"content": content}},
            "degraded": True,
        }
    return {
        "mode": "markdown_keyboard" if buttons else "markdown",
        "message": build_markdown_keyboard_payload(
            markdown,
            buttons,
            media_root=media_root,
        ),
        "degraded": False,
    }
