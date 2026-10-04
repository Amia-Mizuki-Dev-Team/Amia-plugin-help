# ruff: noqa: N999, TC002

from __future__ import annotations

from nonebot import logger, on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .config import render_prefix_text
from .gensokyo import (
    HelpRequest,
    parse_help_request,
    render_page_request,
)

__plugin_meta__ = PluginMetadata(
    name="Mizuki 文字帮助",
    description="Amia 图片帮助总菜单，带动态分页按钮和插件功能详情",
    usage="/help",
    extra={
        # The help plugin describes the other plugins; it should not list itself.
        "menu_ignore": True,
        "author": "Amia-Mizuki-Dev-Team",
        "version": "016",
        "pmn": {"markdown": True},
        "menu_data": [
            {
                "func": "Amia 帮助入口",
                "trigger_method": "指令",
                "trigger_condition": "/help 或 帮助",
                "brief_des": "打开图片帮助菜单",
                "detail_des": (
                    "按插件、功能和分页生成图片，并在 Gensokyo 中附带动态按钮。"
                ),
            },
        ],
    },
)


# Keep this matcher before ordinary plugin commands.  It owns /help so the
# image and its keyboard are emitted exactly once; pjskhelp keeps its separate
# ``pjsk帮助`` entry point.
mizuki_text_help = on_command(
    "help",
    aliases={"帮助"},
    priority=0,
    block=True,
)


@mizuki_text_help.handle()
async def handle_help(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    args: Message = CommandArg(),
) -> None:
    plain_arg = args.extract_plain_text().strip()
    request = parse_help_request(plain_arg)
    if request is None:
        await matcher.finish("没有找到对应的帮助页面，请使用 /help 查看首页。")

    try:
        message = await render_page_request(bot, event, request or HelpRequest())
    except Exception as exc:  # noqa: BLE001 - renderer is an optional runtime boundary
        logger.exception("Amia help image rendering failed: {}", type(exc).__name__)
        fallback = render_prefix_text()
        await matcher.finish(f"{fallback}\n图片帮助暂时不可用，请稍后重试。")
        return
    if message is None:
        await matcher.finish("没有找到对应的帮助页面，请使用 /help 查看首页。")
    await matcher.finish(message)
