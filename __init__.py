from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters import Message
from nonebot.plugin import PluginMetadata

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="Mizuki 文字帮助",
    description="在图片帮助前插入文字",
    usage="/help",
    # 这里的 extra 可以设置不让它显示在某些自动帮助菜单里
    extra={"menu_ignore": True} 
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
    if plain_arg:
        return 

    # 发送文字消息
    # 注意：这里必须用 .send() 而不能用 .finish()
    # 因为 .finish() 会直接强行结束，导致后面的图片插件收不到指令
    await mizuki_text_help.send("欢迎使用Mizuki Bot\n使用网站(已更新) help mizuki top\nbot吹水(x):105 396 4431\npjsk所有功能私聊已全部禁掉\n已更新官方Bot\n使用前请qbind 你的qq号\n更多详情请前往必应搜索Mizuki Bot")

# 执行完这个 handle 后，因为 block=False，NoneBot 会继续寻找下一个 help 指令插件（即你的图片插件）