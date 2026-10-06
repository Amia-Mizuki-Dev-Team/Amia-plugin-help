from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PREFIX_TEXT = "欢迎使用 Amia_晓山瑞希。"
DEFAULT_FOOTER_TEXT = "Amia_晓山瑞希 Powered By HX-Wrdzgzs"
DEFAULT_BUTTON_PAGE_SIZE = 12
MAX_BUTTON_PAGE_SIZE = 12


def _setting(name: str) -> str | None:
    """Read a setting from the process environment or NoneBot's dotenv config."""

    value = os.getenv(name)
    if value is not None:
        return value
    try:
        from nonebot import get_driver

        value = getattr(get_driver().config, name.lower(), None)
    except Exception:  # noqa: BLE001 - config helpers also run in unit tests
        return None
    return None if value is None else str(value)


def _env_bool(name: str, *, default: bool = True) -> bool:
    value = _setting(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def prefix_enabled() -> bool:
    return _env_bool("AMIA_HELP_PREFIX_ENABLED", default=True)


def render_group_link() -> str:
    """Return the configured Markdown link for the official group."""

    group_url = (_setting("AMIA_HELP_GROUP_URL") or "").strip()
    if not group_url:
        return ""
    return f"官方群：[加入官方群]({group_url})"


def render_prefix_text(*, include_group: bool = True) -> str:
    """Render configurable prefix text, optionally including the group link."""

    prefix_text = _setting("AMIA_HELP_PREFIX_TEXT")
    lines = [prefix_text if prefix_text is not None else DEFAULT_PREFIX_TEXT]
    docs_url = (_setting("AMIA_HELP_DOCS_URL") or "").strip()
    if docs_url:
        lines.append(f"帮助文档：{docs_url}")
    if include_group and (group_link := render_group_link()):
        lines.append(group_link)
    qbind_value = _setting("AMIA_HELP_QBIND_TEXT")
    qbind_text = (
        qbind_value if qbind_value is not None else "使用前请先完成 qbind 绑定。"
    ).strip()
    if qbind_text:
        lines.append(qbind_text)
    group_id = (_setting("AMIA_HELP_GROUP_ID") or "").strip()
    if group_id:
        lines.append(f"交流群：{group_id}")
    return "\n".join(lines)


def render_footer_text() -> str:
    """Return the footer rendered into every generated help image."""

    value = (_setting("AMIA_HELP_FOOTER_TEXT") or DEFAULT_FOOTER_TEXT).strip()
    return value or DEFAULT_FOOTER_TEXT


@dataclass(frozen=True, slots=True)
class MarkdownHelpConfig:
    """Runtime settings for the optional Gensokyo Markdown adapter."""

    mode: str = "auto"
    upload_url: str = "http://127.0.0.1:15630/uploadpicv2"
    access_token: str = ""
    upload_timeout_seconds: float = 15.0
    image_cache_ttl_seconds: float = 3600.0
    image_cache_max_entries: int = 64
    button_page_size: int = DEFAULT_BUTTON_PAGE_SIZE
    command_prefix: str = "/"


def _env_float(name: str, default: float, minimum: float) -> float:
    value = _setting(name)
    if value is None:
        return default
    try:
        return max(float(value.strip()), minimum)
    except ValueError:
        return default


def _env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    value = _setting(name)
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    parsed = max(parsed, minimum)
    return min(parsed, maximum) if maximum is not None else parsed


def markdown_help_config() -> MarkdownHelpConfig:
    mode = (_setting("AMIA_HELP_MARKDOWN_MODE") or "auto").strip().lower()
    if mode not in {"auto", "on", "off"}:
        mode = "auto"
    upload_url = (
        _setting("AMIA_HELP_GENSOKYO_UPLOAD_URL")
        or "http://127.0.0.1:15630/uploadpicv2"
    ).strip()
    prefix = (_setting("AMIA_HELP_BUTTON_COMMAND_PREFIX") or "/").strip()
    return MarkdownHelpConfig(
        mode=mode,
        upload_url=upload_url,
        access_token=(_setting("AMIA_HELP_GENSOKYO_ACCESS_TOKEN") or "").strip(),
        upload_timeout_seconds=_env_float(
            "AMIA_HELP_UPLOAD_TIMEOUT_SECONDS", 15.0, 1.0
        ),
        image_cache_ttl_seconds=_env_float(
            "AMIA_HELP_IMAGE_CACHE_TTL_SECONDS", 3600.0, 1.0
        ),
        image_cache_max_entries=_env_int(
            "AMIA_HELP_IMAGE_CACHE_MAX_ENTRIES", 64, 1, 64
        ),
        button_page_size=_env_int(
            "AMIA_HELP_BUTTON_PAGE_SIZE",
            DEFAULT_BUTTON_PAGE_SIZE,
            1,
            MAX_BUTTON_PAGE_SIZE,
        ),
        command_prefix=prefix or "/",
    )
