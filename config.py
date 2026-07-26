from __future__ import annotations

import os


DEFAULT_PREFIX_TEXT = "欢迎使用 Mizuki Bot。帮助菜单由 PicMenu Next 提供。"


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def prefix_enabled() -> bool:
    return _env_bool("AMIA_HELP_PREFIX_ENABLED", True)


def render_prefix_text() -> str:
    """Render configurable text without embedding account or group data."""

    lines = [os.getenv("AMIA_HELP_PREFIX_TEXT", DEFAULT_PREFIX_TEXT)]
    docs_url = os.getenv("AMIA_HELP_DOCS_URL", "").strip()
    if docs_url:
        lines.append(f"帮助文档：{docs_url}")
    qbind_text = os.getenv(
        "AMIA_HELP_QBIND_TEXT", "使用前请先完成 qbind 绑定。"
    ).strip()
    if qbind_text:
        lines.append(qbind_text)
    group_id = os.getenv("AMIA_HELP_GROUP_ID", "").strip()
    if group_id:
        lines.append(f"交流群：{group_id}")
    return "\n".join(lines)
