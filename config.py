from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PREFIX_TEXT = "欢迎使用 Amia_晓山瑞希。"
DEFAULT_FOOTER_TEXT = "Amia_晓山瑞希 Powered By HX-Wrdzgzs"
DEFAULT_BUTTON_PAGE_SIZE = 12
MAX_BUTTON_PAGE_SIZE = 12


def _env_bool(name: str, *, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def prefix_enabled() -> bool:
    return _env_bool("AMIA_HELP_PREFIX_ENABLED", default=True)


def render_prefix_text() -> str:
    """Render configurable Markdown prefix text without hard-coded group data."""

    lines = [os.getenv("AMIA_HELP_PREFIX_TEXT", DEFAULT_PREFIX_TEXT)]
    docs_url = os.getenv("AMIA_HELP_DOCS_URL", "").strip()
    if docs_url:
        lines.append(f"帮助文档：{docs_url}")
    group_url = os.getenv("AMIA_HELP_GROUP_URL", "").strip()
    if group_url:
        lines.append(f"官方群：[加入官方群]({group_url})")
    qbind_text = os.getenv(
        "AMIA_HELP_QBIND_TEXT", "使用前请先完成 qbind 绑定。"
    ).strip()
    if qbind_text:
        lines.append(qbind_text)
    group_id = os.getenv("AMIA_HELP_GROUP_ID", "").strip()
    if group_id:
        lines.append(f"交流群：{group_id}")
    return "\n".join(lines)


def render_footer_text() -> str:
    """Return the footer rendered into every generated help image."""

    value = os.getenv("AMIA_HELP_FOOTER_TEXT", DEFAULT_FOOTER_TEXT).strip()
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
    value = os.getenv(name)
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
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    parsed = max(parsed, minimum)
    return min(parsed, maximum) if maximum is not None else parsed


def markdown_help_config() -> MarkdownHelpConfig:
    mode = os.getenv("AMIA_HELP_MARKDOWN_MODE", "auto").strip().lower()
    if mode not in {"auto", "on", "off"}:
        mode = "auto"
    upload_url = os.getenv(
        "AMIA_HELP_GENSOKYO_UPLOAD_URL",
        "http://127.0.0.1:15630/uploadpicv2",
    ).strip()
    prefix = os.getenv("AMIA_HELP_BUTTON_COMMAND_PREFIX", "/").strip()
    return MarkdownHelpConfig(
        mode=mode,
        upload_url=upload_url,
        access_token=os.getenv("AMIA_HELP_GENSOKYO_ACCESS_TOKEN", "").strip(),
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
