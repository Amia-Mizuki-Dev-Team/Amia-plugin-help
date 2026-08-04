from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters import Message
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

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="Mizuki 文字帮助",
    description="在图片帮助前插入文字",
    usage="/help",
    # 这里的 extra 可以设置不让它显示在某些自动帮助菜单里
    extra={
        "menu_ignore": True,
        "author": "Amia-Mizuki-Dev-Team",
        "version": "010",
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
# 1. priority=1：设置极高优先级，确保它比生成图片的插件（通常是 5 或 10）先运行
# 2. block=False：这是关键！发送完文字后，不拦截指令，让指令继续传递给图片插件
mizuki_text_help = on_command(
    "help", 
    aliases={"帮助"}, 
    priority=1, 
    block=False
)

@mizuki_text_help.handle()
async def handle_help(args: Message = CommandArg()):
    # 检查是否有参数（如 "help 7"），如果有则跳过
    plain_arg = args.extract_plain_text().strip()
    if plain_arg or not prefix_enabled():
        return 

    # 发送文字消息
    # 注意：这里必须用 .send() 而不能用 .finish()
    # 因为 .finish() 会直接强行结束，导致后面的图片插件收不到指令
    await mizuki_text_help.send(render_prefix_text())

# 执行完这个 handle 后，因为 block=False，NoneBot 会继续寻找下一个 help 指令插件（即你的图片插件）
