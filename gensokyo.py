from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import time
from collections.abc import Iterator, Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

import httpx
from cookit.pw import make_real_path_router
from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.matcher import current_bot
from nonebot_plugin_alconna.uniseg import Image, Other, UniMessage
from nonebot_plugin_picmenu_next.__main__ import render_menu
from nonebot_plugin_picmenu_next.templates import (
    detail_templates,
    func_detail_templates,
    index_templates,
)
import nonebot_plugin_picmenu_next.templates.default as picmenu_default
from nonebot_plugin_picmenu_next.config import config as picmenu_config

from .compat import build_markdown_keyboard_payload
from .config import (
    MarkdownHelpConfig,
    markdown_help_config,
    prefix_enabled,
    render_prefix_text,
)


MAX_IMAGE_BYTES = 10 * 1024 * 1024
OFFICIAL_HELP_URL = "https://help.mizuki.top"
BUTTON_COLUMNS = 3
_PAGE_ARGUMENT = re.compile(r"^(?:(?P<plugin>\d+)\s+)?--page\s+(?P<page>-?\d+)$")
_PAGE_ARGUMENT_PREFIX = re.compile(r"^(?:(?P<plugin>\d+)\s+)?--page(?:\s+\S+)?$")


@dataclass(frozen=True, slots=True)
class PageRequest:
    plugin_index: str | None
    page: int


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
_UPLOAD_LOCK: asyncio.Lock | None = None
_VERSION_CACHE: dict[str, tuple[float, bool]] = {}
_VERSION_CACHE_TTL = 300.0


def _install_picmenu_local_file_compat() -> None:
    """Repair PicMenu 0.4.1's trailing-slash local-file route.

    The default template emits ``./local-file/?path=...`` while the pinned
    upstream router only matches ``/local-file?path=...``. Additional CSS is
    therefore silently skipped unless this compatible route is registered.
    The route lives in this adapter so the upstream package remains untouched.
    """

    pattern = re.compile(
        rf"^{re.escape(picmenu_default.ROUTE_BASE_URL)}/local-file/\?path=[^/]+"
    )
    if any(
        getattr(router.pattern, "pattern", router.pattern) == pattern.pattern
        for router in picmenu_default.base_routers.routers
    ):
        return

    @picmenu_default.base_routers.router(pattern)
    @make_real_path_router
    async def _local_file_with_trailing_slash(url, **_):
        return Path(url.query["path"]).resolve()


_install_picmenu_local_file_compat()


def parse_page_request(argument: str) -> PageRequest | None:
    """Parse only the explicit pagination extension, leaving PicMenu queries alone."""

    text = argument.strip()
    if not _PAGE_ARGUMENT_PREFIX.fullmatch(text):
        return None
    match = _PAGE_ARGUMENT.fullmatch(text)
    if not match:
        # Let the caller provide a deterministic error for malformed page input.
        parts = text.split()
        plugin = parts[0] if len(parts) == 3 and parts[0].isdigit() else None
        return PageRequest(plugin, 0)
    return PageRequest(match.group("plugin"), int(match.group("page")))


@contextmanager
def page_request_context(request: PageRequest | None) -> Iterator[None]:
    token = PAGE_REQUEST.set(request)
    try:
        yield
    finally:
        PAGE_REQUEST.reset(token)


def picmenu_templates_configured() -> bool:
    return all(
        getattr(picmenu_config, name, "default") == "amia_gensokyo"
        for name in ("index_template", "detail_template", "func_detail_template")
    )


def _page_window(count: int, requested_page: int, page_size: int) -> PageWindow:
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
    return {
        "id": button_id,
        "render_data": {
            "label": _short_label(label),
            "visited_label": _short_label(label),
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
    command_for_page,
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


def _extract_image(message: UniMessage) -> bytes | None:
    for segment in message:
        if isinstance(segment, Image):
            raw = segment.raw_bytes
            if raw:
                return bytes(raw)
    return None


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
    global _UPLOAD_LOCK
    if _UPLOAD_LOCK is None:
        _UPLOAD_LOCK = asyncio.Lock()
    return _UPLOAD_LOCK


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
        headers = {"User-Agent": "Amia-plugin-help/Release015"}
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
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning(
                    "Amia help Markdown image upload failed: HTTP {}",
                    response.status_code,
                )
                return None
            payload = response.json()
            url = _valid_public_url(payload.get("url")) if isinstance(payload, Mapping) else None
            width = payload.get("width") if isinstance(payload, Mapping) else None
            height = payload.get("height") if isinstance(payload, Mapping) else None
            if url is None or not isinstance(width, int) or isinstance(width, bool) or width <= 0:
                raise ValueError("invalid upload URL or width")
            if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
                raise ValueError("invalid upload height")
            uploaded = UploadedImage(url=url, width=width, height=height)
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
    except Exception:  # noqa: BLE001 - unsupported adapters use the old path
        supported = False
    _VERSION_CACHE[bot_id] = (now, supported)
    return supported


def _page_text(
    title: str,
    window: PageWindow,
    total: int,
) -> str:
    if total:
        start = window.start + 1
        end = window.end
        range_text = f"按钮 {start}–{end} / 共 {total} 项"
    else:
        range_text = "当前没有可用条目"
    return (
        f"# {title}\n"
        f"官方网站：[help.mizuki.top]({OFFICIAL_HELP_URL})\n"
        f"第 {window.page} / {window.total_pages} 页 · {range_text}\n"
        "点击下方按钮进入插件、功能或切换页面。"
    )


async def _render_card(
    default_message: UniMessage,
    *,
    title: str,
    window: PageWindow,
    total: int,
    rows: list[list[dict[str, Any]]],
    include_prefix: bool = False,
) -> UniMessage:
    def fallback() -> UniMessage:
        if include_prefix and prefix_enabled():
            return UniMessage.text(render_prefix_text()) + default_message
        return default_message

    bot = current_bot.get(None)
    if bot is None or not await is_gensokyo_bot(bot):
        return fallback()
    raw = _extract_image(default_message)
    if raw is None:
        logger.warning("Amia help Markdown fallback: PicMenu returned no raw image")
        return fallback()
    uploaded = await upload_image(raw)
    if uploaded is None:
        return fallback()
    prefix = f"{render_prefix_text()}\n\n" if prefix_enabled() else ""
    page_lines = _page_text(title, window, total).splitlines()
    heading, metadata = page_lines[0], page_lines[1:]
    metadata_text = "\n".join(metadata)
    markdown = (
        f"{prefix}{heading}\n"
        f"![帮助菜单 #{uploaded.width}px #{uploaded.height}px]({uploaded.url})\n"
        f"{metadata_text}"
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
    return UniMessage(Other(MessageSegment("markdown", {"data": payload})))


def _invalid_page_message(request: PageRequest, window: PageWindow) -> UniMessage:
    parts: list[object]
    if request.plugin_index is None:
        parts = ["--page", 1]
    else:
        parts = [request.plugin_index, "--page", 1]
    return UniMessage.text(
        f"页码超出范围，请输入 1 到 {window.total_pages}："
        f"{_command(markdown_help_config(), *parts)}"
    )


@index_templates("amia_gensokyo")
async def render_index(
    infos: list[Any],
    showing_hidden: bool,
    user_can_see_hidden: bool | None,
) -> UniMessage:
    config = markdown_help_config()
    request = PAGE_REQUEST.get()
    requested_page = request.page if request else 1
    rows, window = build_index_keyboard(infos, requested_page, config)
    if request and not window.valid:
        return _invalid_page_message(request, window)
    default_message = await index_templates.get("default")(
        infos,
        showing_hidden,
        user_can_see_hidden,
    )
    return await _render_card(
        default_message,
        title="帮助菜单",
        window=window,
        total=len(infos),
        rows=rows,
        include_prefix=True,
    )


@detail_templates("amia_gensokyo")
async def render_detail(
    info: Any,
    info_index: int,
    showing_hidden: bool,
    user_can_see_hidden: bool | None,
) -> UniMessage:
    config = markdown_help_config()
    request = PAGE_REQUEST.get()
    requested_page = request.page if request else 1
    rows, window = build_detail_keyboard(info, info_index, requested_page, config)
    if request and not window.valid:
        return _invalid_page_message(request, window)
    default_message = await detail_templates.get("default")(
        info,
        info_index,
        showing_hidden,
        user_can_see_hidden,
    )
    return await _render_card(
        default_message,
        title=f"插件详情：{_name(info, 'name', 'plugin_name')}",
        window=window,
        total=len(getattr(info, "pm_data", None) or []),
        rows=rows,
    )


@func_detail_templates("amia_gensokyo")
async def render_function_detail(
    info: Any,
    info_index: int,
    func: Any,
    func_index: int | None,
    showing_hidden: bool,
    user_can_see_hidden: bool | None,
) -> UniMessage:
    config = markdown_help_config()
    default_message = await func_detail_templates.get("default")(
        info,
        info_index,
        func,
        func_index,
        showing_hidden,
        user_can_see_hidden,
    )
    rows = build_function_detail_keyboard(info_index, config)
    window = PageWindow(page=1, total_pages=1, start=0, end=1, valid=True)
    return await _render_card(
        default_message,
        title=f"功能详情：{_name(func, 'func', 'name')}",
        window=window,
        total=1,
        rows=rows,
    )


async def render_page_request(bot: Any, event: Any, request: PageRequest) -> UniMessage | None:
    token = PAGE_REQUEST.set(request)
    try:
        kwargs: dict[str, Any] = {}
        if request.plugin_index is not None:
            kwargs["q_plugin"] = request.plugin_index
        message, _, _ = await render_menu(bot, event, **kwargs)
        return message
    finally:
        PAGE_REQUEST.reset(token)
