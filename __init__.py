from nonebot import logger, on_command
from nonebot.adapters import Bot, Event
from nonebot.params import CommandArg
from nonebot.adapters import Message
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata

from .config import prefix_enabled, render_prefix_text
from .menu import (
    PICMENU_COMMIT,
    PICMENU_UPSTREAM,
    build_amiya_menu,
    collect_capabilities,
    ensure_picmenu_loaded,
)

# PicMenu Next is an external renderer.  Requiring it here makes the dependency
# explicit while keeping its source and lifecycle outside Amia-plugin-help.
ensure_picmenu_loaded()

from .gensokyo import (  # noqa: E402 - PicMenu must be loaded first
    parse_page_request,
    picmenu_templates_configured,
    render_page_request,
)

if not picmenu_templates_configured():
    logger.warning(
        "Amia help Markdown templates are not fully configured; "
        "PicMenu will keep its configured templates and native-card output is disabled."
    )

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="Mizuki 文字帮助",
    description="PicMenu 图片帮助与 Gensokyo 原生 Markdown 动态按钮适配",
    usage="/help",
    # 这里的 extra 可以设置不让它显示在某些自动帮助菜单里
    extra={
        "menu_ignore": True,
        "author": "Amia-Mizuki-Dev-Team",
        "version": "015",
        "pmn": {"markdown": True},
        "menu_data": [
            {
                "func": "Amia 帮助入口",
                "trigger_method": "指令",
                "trigger_condition": "/help 或 帮助",
                "brief_des": "打开 PicMenu Next 图片帮助菜单",
                "detail_des": "支持分类、模糊搜索、拼音搜索、Markdown 和 Keyboard。",
            },
            {
                "func": "Amia 功能分类",
                "trigger_method": "指令参数",
                "trigger_condition": "/help <分类>",
                "brief_des": "查看指定插件的功能详情",
                "detail_des": "分类由已加载插件的 PluginMetadata 和 CapabilityProvider 聚合生成。",
            },
        ],
    },
)

# 核心设置：
# 1. priority=0：分页扩展需要在 PicMenu 的 help matcher 之前处理
# 2. block=False：普通 help 查询继续交给 PicMenu；只有分页请求会动态停止传播
mizuki_text_help = on_command(
    "help",
    aliases={"帮助"},
    priority=0,
    block=False,
)


@mizuki_text_help.handle()
async def handle_help(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    args: Message = CommandArg(),
):
    plain_arg = args.extract_plain_text().strip()
    page_request = parse_page_request(plain_arg)
    if page_request is not None:
        matcher.stop_propagation()
        message = await render_page_request(bot, event, page_request)
        if message is not None:
            await message.finish()
        await mizuki_text_help.finish("没有找到对应的帮助页面。")

    if plain_arg or not prefix_enabled():
        return

    # With the adaptive templates selected, the template owns both the native
    # card prefix and the non-Gensokyo fallback prefix.  Keeping this matcher
    # silent avoids a duplicate text message before PicMenu renders.
    if picmenu_templates_configured():
        return

    await mizuki_text_help.send(render_prefix_text())
