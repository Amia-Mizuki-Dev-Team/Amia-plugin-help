from __future__ import annotations

import asyncio
import base64
import re
import sys
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.plugin import get_loaded_plugins

from .compat import build_button_fallback_text, build_markdown_keyboard_payload
from .config import (
    MarkdownHelpConfig,
    markdown_help_config,
    prefix_enabled,
    render_footer_text,
    render_group_link,
    render_prefix_text,
)
from .menu import collect_capabilities

MAX_IMAGE_BYTES = 10 * 1024 * 1024
OFFICIAL_HELP_URL = "https://help.mizuki.top"
BUTTON_COLUMNS = 3
MALFORMED_PAGE_PARTS = 3
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_MAX = 300
TEMPLATE_PATH = str(Path(__file__).parent / "templates")
HIDDEN_HELP_FUNCTIONS = frozenset({"很忙"})
_PAGE_ARGUMENT = re.compile(r"^(?:(?P<plugin>\d+)\s+)?--page\s+(?P<page>-?\d+)$")
_PAGE_ARGUMENT_PREFIX = re.compile(r"^(?:(?P<plugin>\d+)\s+)?--page(?:\s+\S+)?$")
_TARGET_ARGUMENT = re.compile(r"^(?P<plugin>\d+)(?:\s+(?P<function>\d+))?$")


@dataclass(frozen=True, slots=True)
class HelpInfo:
    """Small local plugin-info model used by the merged image menu."""

    name: str
    description: str = ""
    usage: str = ""
    pm_data: tuple[dict[str, Any], ...] = ()
    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PageRequest:
    plugin_index: str | None
    page: int


@dataclass(frozen=True, slots=True)
class HelpRequest:
    plugin_index: int | None = None
    function_index: int | None = None
    page: int = 1


@dataclass(frozen=True, slots=True)
class PageWindow:
    page: int
    total_pages: int
    start: int
    end: int
    valid: bool


@dataclass(frozen=True, slots=True)
class UploadedImage:
    url: str
    width: int
    height: int


PAGE_REQUEST: ContextVar[PageRequest | None] = ContextVar(
    "amia_help_page_request", default=None
)
_UPLOAD_CACHE: OrderedDict[str, tuple[float, UploadedImage]] = OrderedDict()
_RENDER_LOCK = asyncio.Lock()
_UPLOAD_LOCK_STATE: list[asyncio.Lock | None] = [None]
_VERSION_CACHE: dict[str, tuple[float, bool]] = {}
_VERSION_CACHE_TTL = 300.0


def parse_page_request(argument: str) -> PageRequest | None:
    """Parse the explicit pagination extension used by help buttons."""

    text = argument.strip()
    if not _PAGE_ARGUMENT_PREFIX.fullmatch(text):
        return None
    match = _PAGE_ARGUMENT.fullmatch(text)
    if not match:
        parts = text.split()
        plugin = (
            parts[0]
            if len(parts) == MALFORMED_PAGE_PARTS and parts[0].isdigit()
            else None
        )
        return PageRequest(plugin, 0)
    return PageRequest(match.group("plugin"), int(match.group("page")))


def parse_help_request(argument: str) -> HelpRequest | None:
    """Parse index, function and pagination targets from a button command."""

    text = argument.strip()
    if not text:
        return HelpRequest()
    page = parse_page_request(text)
    if page is not None:
        return HelpRequest(
            plugin_index=int(page.plugin_index) if page.plugin_index else None,
            page=page.page,
        )
    match = _TARGET_ARGUMENT.fullmatch(text)
    if not match:
        return None
    return HelpRequest(
        plugin_index=int(match.group("plugin")),
        function_index=(
            int(match.group("function")) if match.group("function") else None
        ),
    )


@contextmanager
def page_request_context(request: PageRequest | None) -> Iterator[None]:
    token = PAGE_REQUEST.set(request)
    try:
        yield
    finally:
        PAGE_REQUEST.reset(token)


def _page_window(count: int, requested_page: int, page_size: int) -> PageWindow:
    page_size = max(1, page_size)
    total_pages = max(1, (count + page_size - 1) // page_size)
    valid = 1 <= requested_page <= total_pages
    page = requested_page if valid else max(1, min(requested_page, total_pages))
    start = (page - 1) * page_size
    return PageWindow(
        page=page,
        total_pages=total_pages,
        start=start,
        end=min(start + page_size, count),
        valid=valid,
    )


def _short_label(value: Any, limit: int = 10) -> str:
    text = str(value or "帮助").replace("\r", " ").replace("\n", " ").strip()
    for prefix in ("Amia ", "Mizuki "):
        if text.casefold().startswith(prefix.casefold()) and len(text) > len(prefix):
            text = text[len(prefix) :].strip()
            break
    if len(text) <= limit:
        return text
    words = text.split()
    if len(words) > 1:
        suffix = words[-1]
        if len(suffix) <= limit:
            return suffix
        initials = "".join(word[0] for word in words if word)
        if 1 < len(initials) <= limit:
            return initials
    return f"{text[: max(1, limit - 1)]}…"


def _command(config: MarkdownHelpConfig, *parts: object) -> str:
    suffix = " ".join(str(part) for part in parts if str(part))
    return f"{config.command_prefix}help" + (f" {suffix}" if suffix else "")


def _button(
    button_id: str,
    label: str,
    data: str,
    *,
    enter: bool = True,
) -> dict[str, Any]:
    short_label = _short_label(label)
    return {
        "id": button_id,
        "render_data": {
            "label": short_label,
            "visited_label": short_label,
            "style": 0,
        },
        "action": {
            "type": 2,
            "permission": {"type": 2},
            "data": data,
            "enter": enter,
            "reply": False,
            "unsupport_tips": f"请手动发送：{data}",
        },
    }


def _rows(buttons: Sequence[Mapping[str, Any]]) -> list[list[dict[str, Any]]]:
    return [
        [dict(button) for button in buttons[index : index + BUTTON_COLUMNS]]
        for index in range(0, len(buttons), BUTTON_COLUMNS)
    ]


def _navigation_buttons(
    window: PageWindow,
    command_for_page: Callable[[int], str],
    *,
    home_command: str | None = None,
) -> list[dict[str, Any]]:
    if window.total_pages <= 1 and home_command is None:
        return []
    buttons: list[dict[str, Any]] = []
    if window.page > 1:
        buttons.append(
            _button(
                f"nav-prev-{window.page}",
                "上一页",
                command_for_page(window.page - 1),
            )
        )
        buttons.append(
            _button(
                f"nav-first-{window.page}",
                "第一页",
                command_for_page(1),
            )
        )
    if home_command is not None:
        buttons.append(_button(f"nav-home-{window.page}", "帮助首页", home_command))
    if window.page < window.total_pages:
        buttons.append(
            _button(
                f"nav-next-{window.page}",
                "下一页",
                command_for_page(window.page + 1),
            )
        )
    return buttons


def _name(value: Any, *attributes: str, default: str = "帮助") -> str:
    for attribute in attributes:
        candidate = getattr(value, attribute, None)
        if candidate:
            return str(candidate)
        if isinstance(value, Mapping) and value.get(attribute):
            return str(value[attribute])
    return default


def build_index_keyboard(
    infos: Sequence[Any],
    requested_page: int,
    config: MarkdownHelpConfig | None = None,
) -> tuple[list[list[dict[str, Any]]], PageWindow]:
    config = config or markdown_help_config()
    window = _page_window(len(infos), requested_page, config.button_page_size)
    buttons = [
        _button(
            f"plugin-{index + 1}",
            _name(info, "name", "plugin_name"),
            _command(config, index + 1),
        )
        for index, info in enumerate(infos[window.start : window.end], window.start)
    ]
    buttons.extend(
        _navigation_buttons(
            window,
            lambda page: _command(config, "--page", page),
        )
    )
    return _rows(buttons), window


def build_detail_keyboard(
    info: Any,
    info_index: int,
    requested_page: int,
    config: MarkdownHelpConfig | None = None,
) -> tuple[list[list[dict[str, Any]]], PageWindow]:
    config = config or markdown_help_config()
    functions = list(getattr(info, "pm_data", None) or [])
    if isinstance(info, Mapping):
        functions = list(info.get("pm_data") or [])
    window = _page_window(len(functions), requested_page, config.button_page_size)
    plugin_index = info_index + 1
    buttons = [
        _button(
            f"function-{plugin_index}-{index + 1}",
            _name(item, "func", "name"),
            _command(config, plugin_index, index + 1),
        )
        for index, item in enumerate(functions[window.start : window.end], window.start)
    ]
    buttons.extend(
        _navigation_buttons(
            window,
            lambda page: _command(config, plugin_index, "--page", page),
            home_command=_command(config),
        )
    )
    return _rows(buttons), window


def build_function_detail_keyboard(
    info_index: int,
    config: MarkdownHelpConfig | None = None,
) -> list[list[dict[str, Any]]]:
    config = config or markdown_help_config()
    return _rows(
        [
            _button(
                "nav-plugin",
                "返回插件",
                _command(config, info_index + 1),
            ),
            _button("nav-home", "帮助首页", _command(config)),
        ]
    )


def _value(value: Any, *attributes: str, default: Any = "") -> Any:
    for attribute in attributes:
        if isinstance(value, Mapping) and value.get(attribute) is not None:
            return value.get(attribute)
        candidate = getattr(value, attribute, None)
        if candidate is not None:
            return candidate
    return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _usage_summary(usage: Any, description: Any = "") -> str:
    raw = _text(usage) or _text(description)
    for raw_line in raw.splitlines():
        line = raw_line.strip().lstrip("-•· ")
        if line:
            return line[:140]
    return ""


def _normalise_function(item: Any, fallback: str = "插件说明") -> dict[str, Any] | None:
    name = _text(_value(item, "func", "name", "title"), fallback)
    if not name:
        return None
    hidden = _value(item, "pmn_hidden", "hidden", default=False)
    if bool(hidden):
        return None
    condition = _text(
        _value(item, "trigger_condition", "condition", "command"),
    )
    if name in HIDDEN_HELP_FUNCTIONS or condition in HIDDEN_HELP_FUNCTIONS:
        return None
    brief = _text(
        _value(item, "brief_des", "description", "brief", "detail_des"),
    )
    detail = _text(_value(item, "detail_des", "description", "brief_des"))
    return {
        "func": name,
        "name": name,
        "trigger_method": _text(_value(item, "trigger_method", "method")),
        "trigger_condition": condition,
        "brief_des": brief,
        "detail_des": detail or brief,
    }


def _metadata_for_plugin(plugin: Any) -> Any | None:
    metadata = getattr(plugin, "metadata", None)
    if metadata is not None:
        return metadata
    return getattr(getattr(plugin, "module", None), "__plugin_meta__", None)


def _plugin_to_info(plugin: Any) -> HelpInfo | None:
    metadata = _metadata_for_plugin(plugin)
    plugin_id = _text(getattr(plugin, "id_", None) or getattr(plugin, "name", None))
    module_name = _text(getattr(plugin, "module_name", None))
    extra = getattr(metadata, "extra", None) if metadata is not None else None
    if not isinstance(extra, Mapping):
        extra = {}
    if extra.get("menu_ignore"):
        return None
    if module_name in {
        "nonebot_plugin_htmlrender",
        "nonebot_plugin_localstore",
        "nonebot_plugin_alconna",
    }:
        return None
    pmn = extra.get("pmn")
    if (
        metadata is not None
        and _text(getattr(metadata, "type", "application")) == "library"
        and not (isinstance(pmn, Mapping) and pmn.get("hidden") is False)
    ):
        return None
    name = _text(
        getattr(metadata, "name", None) if metadata is not None else None,
        plugin_id or "帮助",
    )
    description = _text(
        getattr(metadata, "description", None) if metadata is not None else None
    )
    usage = _text(getattr(metadata, "usage", None) if metadata is not None else None)
    raw_functions = extra.get("menu_data")
    if isinstance(raw_functions, Mapping):
        raw_functions = [raw_functions]
    if not isinstance(raw_functions, Sequence) or isinstance(
        raw_functions, (str, bytes, bytearray)
    ):
        raw_functions = []
    functions = [
        normalised
        for item in raw_functions
        if (normalised := _normalise_function(item)) is not None
    ]
    if not functions:
        summary = _usage_summary(usage, description)
        if summary:
            functions = [
                {
                    "func": "插件说明",
                    "name": "插件说明",
                    "trigger_method": "说明",
                    "trigger_condition": "",
                    "brief_des": summary,
                    "detail_des": usage or description or summary,
                }
            ]
    return HelpInfo(
        name=name,
        description=_usage_summary(description, usage),
        usage=usage,
        pm_data=tuple(functions),
        plugin_id=plugin_id,
    )


def collect_help_infos(plugins: Sequence[Any] | None = None) -> list[HelpInfo]:
    """Collect the current loaded plugin metadata for the local help image."""

    if plugins is None:
        plugins = tuple(get_loaded_plugins())
    infos = [
        info
        for plugin in sorted(
            plugins,
            key=lambda item: _text(
                getattr(item, "id_", None) or getattr(item, "name", None)
            ).casefold(),
        )
        if (info := _plugin_to_info(plugin)) is not None
    ]

    # CapabilityProviders can describe services that do not have a standalone
    # plugin metadata object.  Add those entries only when they are not already
    # represented, keeping the menu deterministic and avoiding duplicates.
    core = sys.modules.get("amia_core") or sys.modules.get("src.plugins.amia_core")
    registry = getattr(core, "registry", None) if core is not None else None
    known = {info.name.casefold() for info in infos}
    for capability in collect_capabilities(registry):
        provider = _text(capability.get("provider"), "能力")
        if provider.casefold() in known:
            continue
        values = [
            _text(value) for value in capability.get("capabilities", []) if _text(value)
        ]
        if not values:
            continue
        infos.append(
            HelpInfo(
                name=provider,
                description="、".join(values[:4]),
                pm_data=tuple(
                    {
                        "func": value,
                        "name": value,
                        "trigger_method": "能力",
                        "trigger_condition": "",
                        "brief_des": "已注册能力",
                        "detail_des": "已由 Amia Core 注册。",
                    }
                    for value in values
                ),
                plugin_id=f"capability:{provider}",
            )
        )
    infos.sort(key=lambda info: (info.name.casefold(), info.plugin_id.casefold()))
    return infos


async def _render_template(**templates: Any) -> bytes:
    """Render the local multi-page image template through htmlrender."""

    from nonebot import require

    htmlrender = require("nonebot_plugin_htmlrender")
    request = {
        "template_name": "help.html",
        "templates": templates,
    }
    async with _RENDER_LOCK:
        try:
            return await htmlrender.render_template(TEMPLATE_PATH, **request)
        except Exception as exc:  # noqa: BLE001 - renderer is an optional boundary
            # A stale Chromium session and an oversized full-page screenshot both
            # surface as the same generic Playwright protocol error.  Recreate the
            # shared renderer and retry at 1x so a transient browser failure does
            # not turn a valid help request into a text-only fallback.
            logger.warning(
                "Amia help screenshot failed ({}); restarting htmlrender and retrying",
                type(exc).__name__,
            )
            await htmlrender.shutdown_render()
            return await htmlrender.render_template(
                TEMPLATE_PATH,
                **request,
                device_scale_factor=1.0,
                screenshot_timeout=60_000,
            )


def _template_function(item: Any) -> dict[str, str]:
    return {
        "name": _text(_value(item, "func", "name"), "插件说明"),
        "trigger_condition": _text(_value(item, "trigger_condition", "condition")),
        "description": _text(_value(item, "detail_des", "brief_des", "description")),
    }


async def render_index_image(
    infos: Sequence[HelpInfo],
    window: PageWindow,
    config: MarkdownHelpConfig | None = None,
) -> bytes:
    config = config or markdown_help_config()
    entries = [
        {
            "index": index + 1,
            "name": _text(_value(info, "name", "plugin_name"), "帮助"),
            "description": _usage_summary(
                _value(info, "description"),
                _value(info, "usage"),
            ),
        }
        for index, info in enumerate(infos[window.start : window.end], window.start)
    ]
    return await _render_template(
        mode="index",
        title="帮助菜单",
        command_hint=f"{config.command_prefix}help 插件序号",
        entries=entries,
        functions=[],
        footer_text=render_footer_text(),
    )


async def render_detail_image(
    info: HelpInfo,
    requested_page: int,
    config: MarkdownHelpConfig | None = None,
) -> tuple[bytes, PageWindow]:
    config = config or markdown_help_config()
    functions = list(info.pm_data)
    window = _page_window(len(functions), requested_page, config.button_page_size)
    entries = [
        _template_function(item) for item in functions[window.start : window.end]
    ]
    return (
        await _render_template(
            mode="detail",
            title=f"插件详情：{info.name}",
            command_hint="",
            entries=[],
            functions=entries,
            footer_text=render_footer_text(),
        ),
        window,
    )


async def render_function_detail_image(
    function: Any,
    config: MarkdownHelpConfig | None = None,
) -> bytes:
    del config
    return await _render_template(
        mode="function",
        title=f"功能详情：{_name(function, 'func', 'name')}",
        command_hint="",
        entries=[],
        functions=[_template_function(function)],
        footer_text=render_footer_text(),
    )


def _image_dimensions(raw: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image as PillowImage

        with PillowImage.open(BytesIO(raw)) as image:
            return int(image.width), int(image.height)
    except Exception:  # noqa: BLE001 - malformed renderer output is a fallback
        return None


def _valid_public_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value.strip()


def _get_upload_lock() -> asyncio.Lock:
    if _UPLOAD_LOCK_STATE[0] is None:
        _UPLOAD_LOCK_STATE[0] = asyncio.Lock()
    return _UPLOAD_LOCK_STATE[0]


class _InvalidUploadPayloadError(ValueError):
    """Raised when uploadpicv2 returns a payload without a usable image URL."""


def _parse_uploaded_image(payload: Any) -> UploadedImage:
    if not isinstance(payload, Mapping):
        raise _InvalidUploadPayloadError(  # noqa: TRY003
            "upload response is not an object"
        )
    url = _valid_public_url(payload.get("url"))
    width = payload.get("width")
    height = payload.get("height")
    if (
        url is None
        or not isinstance(width, int)
        or isinstance(width, bool)
        or width <= 0
    ):
        raise _InvalidUploadPayloadError("invalid upload URL or width")  # noqa: TRY003
    if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
        raise _InvalidUploadPayloadError("invalid upload height")  # noqa: TRY003
    return UploadedImage(url=url, width=width, height=height)


async def upload_image(
    raw: bytes,
    config: MarkdownHelpConfig | None = None,
) -> UploadedImage | None:
    config = config or markdown_help_config()
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        logger.warning("Amia help Markdown image rejected: empty or larger than 10 MiB")
        return None
    dimensions = _image_dimensions(raw)
    if dimensions is None:
        logger.warning("Amia help Markdown image rejected: dimensions unavailable")
        return None
    cache_key = f"{config.upload_url}|{sha256(raw).hexdigest()}"
    now = time.monotonic()
    async with _get_upload_lock():
        cached = _UPLOAD_CACHE.get(cache_key)
        if cached and now - cached[0] < config.image_cache_ttl_seconds:
            _UPLOAD_CACHE.move_to_end(cache_key)
            return cached[1]
        _UPLOAD_CACHE.pop(cache_key, None)
        headers = {"User-Agent": "Amia-plugin-help/merged-menu"}
        if config.access_token:
            headers["Authorization"] = f"Bearer {config.access_token}"
        try:
            async with httpx.AsyncClient(
                timeout=config.upload_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    config.upload_url,
                    data={"base64Image": base64.b64encode(raw).decode("ascii")},
                    headers=headers,
                )
            if (
                response.status_code < HTTP_SUCCESS_MIN
                or response.status_code >= HTTP_SUCCESS_MAX
            ):
                logger.warning(
                    "Amia help Markdown image upload failed: HTTP {}",
                    response.status_code,
                )
                return None
            uploaded = _parse_uploaded_image(response.json())
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "Amia help Markdown image upload failed: {}",
                type(exc).__name__,
            )
            return None
        _UPLOAD_CACHE[cache_key] = (time.monotonic(), uploaded)
        _UPLOAD_CACHE.move_to_end(cache_key)
        while len(_UPLOAD_CACHE) > config.image_cache_max_entries:
            _UPLOAD_CACHE.popitem(last=False)
        return uploaded


def _is_onebot(bot: Any) -> bool:
    return type(getattr(bot, "adapter", None)).__module__.startswith(
        "nonebot.adapters.onebot"
    )


async def is_gensokyo_bot(bot: Any) -> bool:
    config = markdown_help_config()
    if config.mode == "off" or not _is_onebot(bot):
        return False
    if config.mode == "on":
        return True
    bot_id = str(getattr(bot, "self_id", "unknown"))
    now = time.monotonic()
    cached = _VERSION_CACHE.get(bot_id)
    if cached and now - cached[0] < _VERSION_CACHE_TTL:
        return cached[1]
    supported = False
    try:
        version = await bot.call_api("get_version_info")
        app_name = str(
            version.get("app_name", version.get("app", ""))
            if isinstance(version, Mapping)
            else version
        ).lower()
        supported = "gensokyo" in app_name
    except Exception:  # noqa: BLE001 - unsupported adapters use image fallback
        supported = False
    _VERSION_CACHE[bot_id] = (now, supported)
    return supported


def _page_text(title: str, window: PageWindow, total: int) -> str:
    if total:
        start = window.start + 1
        end = window.end
        range_text = f"按钮 {start}-{end} / 共 {total} 项"
    else:
        range_text = "当前没有可用条目"
    group_link = render_group_link()
    group_line = f"{group_link}\n" if group_link else ""
    return (
        f"# {title}\n"
        f"官方网站：[help.mizuki.top]({OFFICIAL_HELP_URL})\n"
        f"{group_line}"
        f"第 {window.page} / {window.total_pages} 页 · {range_text}\n"
        "点击下方按钮进入插件、功能或切换页面。"
    )


def _image_message(
    raw: bytes,
    *,
    include_prefix: bool = False,
    button_fallback: str = "",
) -> Message:
    segments: list[MessageSegment] = []
    if include_prefix and prefix_enabled():
        segments.append(MessageSegment.text(f"{render_prefix_text()}\n"))
    segments.append(MessageSegment.image(raw))
    if button_fallback:
        segments.append(MessageSegment.text(f"\n\n{button_fallback}"))
    return Message(segments)


async def _render_card(  # noqa: PLR0913
    bot: Any,
    raw: bytes,
    *,
    title: str,
    window: PageWindow,
    total: int,
    rows: list[list[dict[str, Any]]],
    include_prefix: bool = False,
) -> Message:
    config = markdown_help_config()
    button_fallback = build_button_fallback_text(rows)
    if not await is_gensokyo_bot(bot):
        return _image_message(
            raw,
            include_prefix=include_prefix,
            button_fallback=button_fallback,
        )
    uploaded = await upload_image(raw, config)
    if uploaded is None:
        return _image_message(
            raw,
            include_prefix=include_prefix,
            button_fallback=button_fallback,
        )
    prefix_text = render_prefix_text(include_group=False)
    prefix = f"{prefix_text}\n\n" if prefix_enabled() and prefix_text else ""
    page_lines = _page_text(title, window, total).splitlines()
    heading, metadata = page_lines[0], page_lines[1:]
    markdown = (
        f"{prefix}{heading}\n"
        f"![帮助菜单 #{uploaded.width}px #{uploaded.height}px]({uploaded.url})\n"
        f"{chr(10).join(metadata)}"
    )
    payload = build_markdown_keyboard_payload(markdown, rows)
    logger.info(
        "Amia help Markdown card: title={} page={}/{} total={} buttons={}",
        title,
        window.page,
        window.total_pages,
        total,
        sum(len(row) for row in rows),
    )
    return Message([MessageSegment("markdown", {"data": payload})])


def _invalid_page_message(request: HelpRequest, window: PageWindow) -> Message:
    parts: list[object]
    if request.plugin_index is None:
        parts = ["--page", 1]
    else:
        parts = [request.plugin_index]
        if request.function_index is not None:
            parts.append(request.function_index)
        parts.extend(["--page", 1])
    return Message(
        f"页码超出范围，请输入 1 到 {window.total_pages}："
        f"{_command(markdown_help_config(), *parts)}"
    )


async def render_page_request(  # noqa: PLR0911
    bot: Any,
    event: Any,
    request: PageRequest | HelpRequest,
) -> Message | None:
    """Render the requested index/detail page and its matching button rows."""

    del event
    if isinstance(request, PageRequest):
        request = HelpRequest(
            plugin_index=int(request.plugin_index) if request.plugin_index else None,
            page=request.page,
        )
    infos = collect_help_infos()
    config = markdown_help_config()

    if request.plugin_index is None:
        rows, window = build_index_keyboard(infos, request.page, config)
        if not window.valid:
            return _invalid_page_message(request, window)
        raw = await render_index_image(infos, window, config)
        return await _render_card(
            bot,
            raw,
            title="帮助菜单",
            window=window,
            total=len(infos),
            rows=rows,
            include_prefix=True,
        )

    info_index = request.plugin_index - 1
    if info_index < 0 or info_index >= len(infos):
        return Message("没有找到对应的插件帮助页面。")
    info = infos[info_index]
    functions = list(info.pm_data)
    if request.function_index is None:
        rows, window = build_detail_keyboard(info, info_index, request.page, config)
        if not window.valid:
            return _invalid_page_message(request, window)
        raw, rendered_window = await render_detail_image(info, request.page, config)
        return await _render_card(
            bot,
            raw,
            title=f"插件详情：{info.name}",
            window=rendered_window,
            total=len(functions),
            rows=rows,
        )

    function_index = request.function_index - 1
    if function_index < 0 or function_index >= len(functions):
        return Message("没有找到对应的功能帮助页面。")
    rows = build_function_detail_keyboard(info_index, config)
    raw = await render_function_detail_image(functions[function_index], config)
    window = PageWindow(page=1, total_pages=1, start=0, end=1, valid=True)
    return await _render_card(
        bot,
        raw,
        title=f"功能详情：{_name(functions[function_index], 'func', 'name')}",
        window=window,
        total=1,
        rows=rows,
    )
