# Amia-plugin-help

`Amia-plugin-help` 是 **Amia_晓山瑞希** 的统一帮助菜单插件。当前代码版本：**016**。

它直接读取 NoneBot 当前已加载插件的元数据，把 `PluginMetadata`、`extra.menu_data` 与 `amia-core` 的 `CapabilityProvider` 汇总为统一的帮助信息，并使用本地 HTML 模板生成图片菜单。

在 Gensokyo 环境中，插件会发送 **Markdown 图片 + 动态 Keyboard**；在 NapCat 或其他普通 OneBot v11 环境中，则自动回退为 **普通图片 + 可手动发送的命令提示**。

## 主要能力

- 自动聚合已加载插件，不需要维护一份独立的静态菜单；
- 首页 → 插件详情 → 功能详情三级导航；
- 首页和插件详情均支持分页；
- 默认每页最多 12 项，Keyboard 每行最多 3 个按钮；
- Gensokyo 支持 `uploadpicv2`、Markdown 图片与动态 Keyboard；
- 非 Gensokyo OneBot 自动使用普通图片回退；
- 支持 `amia-core` CapabilityProvider，把无独立 PluginMetadata 的能力也加入菜单；
- PicMenu Next 不再是生产运行时依赖；
- htmlrender/Playwright 截图失败时可自动重启 renderer 并重试；
- 配置同时支持系统环境变量与 NoneBot dotenv；
- 图片上传带 TTL/LRU 风格缓存，降低重复上传开销。

## 指令

| 指令 | 作用 |
| --- | --- |
| `/help` / `帮助` | 打开帮助首页 |
| `/help 3` | 打开第 3 个插件的功能列表 |
| `/help 3 1` | 打开第 3 个插件的第 1 个功能详情 |
| `/help --page 2` | 打开帮助首页第 2 页 |
| `/help 3 --page 2` | 打开第 3 个插件功能列表第 2 页 |

`pjsk帮助` 不由本插件接管，仍由独立的 PJSK 帮助插件处理。

## 工作流程

```text
/help
  │
  ├─ 收集 PluginMetadata / extra.menu_data
  ├─ 合并 amia-core CapabilityProvider
  ├─ 过滤不应展示的功能
  ├─ 计算分页与 Keyboard
  ├─ htmlrender 渲染本地帮助图片
  │
  ├─ Gensokyo
  │    ├─ uploadpicv2 上传图片
  │    ├─ 生成 Markdown 图片正文
  │    └─ 附带 keyboard.content.rows
  │
  └─ 其他 OneBot
       └─ 普通图片 + 手动命令回退
```

## 帮助数据来源

插件按当前运行时状态生成帮助内容。

### PluginMetadata

普通插件通过 NoneBot 的 `PluginMetadata` 提供名称、描述、用法等信息。

### extra.menu_data

如果插件在 `PluginMetadata.extra["menu_data"]` 中声明功能信息，本插件会把它转换成插件功能列表和详情页。

### amia-core CapabilityProvider

如果 `amia-core` 已加载，本插件还会读取其 Capability registry。没有独立插件元数据、但已经注册到 Core 的能力也可以进入帮助菜单。

单个可选 CapabilityProvider 发生异常时会被隔离，不会拖垮整个帮助页。

## Gensokyo 与回退策略

### Gensokyo

`AMIA_HELP_MARKDOWN_MODE=auto` 时，插件会调用 `get_version_info` 判断当前 OneBot 是否为 Gensokyo，并缓存探测结果 300 秒。

确认是 Gensokyo 后：

1. 本地生成帮助图片；
2. 调用 `AMIA_HELP_GENSOKYO_UPLOAD_URL` 上传图片；
3. 校验上传结果中的公开 HTTP/HTTPS URL、宽度和高度；
4. 发送 Markdown 图片；
5. 同一消息附带动态 Keyboard。

如果图片上传失败、响应非法或运行环境并非 Gensokyo，会自动回退普通图片消息。

### 普通 OneBot / NapCat

普通 OneBot 不需要 Gensokyo 图床。插件直接发送图片；如果 Keyboard 不可用，会附上对应的手动命令提示。

## 图片渲染稳定性

帮助图由 `nonebot-plugin-htmlrender` 使用 `templates/help.html` 渲染。

当前实现对截图过程使用异步锁，避免共享 Chromium renderer 并发冲突。首次截图异常时会自动：

1. 关闭共享 renderer；
2. 重新创建浏览器会话；
3. 使用 `device_scale_factor=1.0` 再试一次；
4. 将截图超时设置为 60 秒。

模板中的首页卡片限制最大高度，标题最多显示两行，避免超长插件名导致整页布局失控。

## 配置

示例：

```env
AMIA_HELP_PREFIX_ENABLED=true
AMIA_HELP_PREFIX_TEXT=欢迎使用 Amia_晓山瑞希。
AMIA_HELP_DOCS_URL=
AMIA_HELP_GROUP_URL=
AMIA_HELP_GROUP_ID=
AMIA_HELP_QBIND_TEXT=使用前请先完成 qbind 绑定。
AMIA_HELP_FOOTER_TEXT=Amia_晓山瑞希 Powered By HX-Wrdzgzs

AMIA_HELP_MARKDOWN_MODE=auto
AMIA_HELP_GENSOKYO_UPLOAD_URL=http://127.0.0.1:15630/uploadpicv2
AMIA_HELP_GENSOKYO_ACCESS_TOKEN=
AMIA_HELP_UPLOAD_TIMEOUT_SECONDS=15
AMIA_HELP_IMAGE_CACHE_TTL_SECONDS=3600
AMIA_HELP_IMAGE_CACHE_MAX_ENTRIES=64
AMIA_HELP_BUTTON_PAGE_SIZE=12
AMIA_HELP_BUTTON_COMMAND_PREFIX=/

RENDER_BACKEND=playwright
```

### 配置说明

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `AMIA_HELP_PREFIX_ENABLED` | `true` | 是否显示帮助前缀 |
| `AMIA_HELP_PREFIX_TEXT` | `欢迎使用 Amia_晓山瑞希。` | 自定义前缀 |
| `AMIA_HELP_DOCS_URL` | 空 | 外部帮助文档地址 |
| `AMIA_HELP_GROUP_URL` | 空 | 官方群邀请链接 |
| `AMIA_HELP_GROUP_ID` | 空 | 交流群号文本 |
| `AMIA_HELP_QBIND_TEXT` | `使用前请先完成 qbind 绑定。` | qbind 提示 |
| `AMIA_HELP_FOOTER_TEXT` | `Amia_晓山瑞希 Powered By HX-Wrdzgzs` | 图片页脚 |
| `AMIA_HELP_MARKDOWN_MODE` | `auto` | `auto` 自动探测；`on` 强制启用；`off` 禁用 Gensokyo Markdown |
| `AMIA_HELP_GENSOKYO_UPLOAD_URL` | `http://127.0.0.1:15630/uploadpicv2` | Gensokyo 图片上传接口 |
| `AMIA_HELP_GENSOKYO_ACCESS_TOKEN` | 空 | 上传接口 Bearer Token |
| `AMIA_HELP_UPLOAD_TIMEOUT_SECONDS` | `15` | 图片上传超时，最低 1 秒 |
| `AMIA_HELP_IMAGE_CACHE_TTL_SECONDS` | `3600` | 上传结果缓存 TTL |
| `AMIA_HELP_IMAGE_CACHE_MAX_ENTRIES` | `64` | 缓存最大条目数，最大限制 64 |
| `AMIA_HELP_BUTTON_PAGE_SIZE` | `12` | 每页按钮数量，范围 1–12 |
| `AMIA_HELP_BUTTON_COMMAND_PREFIX` | `/` | Keyboard 生成命令使用的前缀 |

所有这些设置都会优先读取进程环境变量；若未设置，再读取 NoneBot driver 的 dotenv 配置。

## 官方群链接行为

设置 `AMIA_HELP_GROUP_URL` 后：

- Gensokyo Markdown 卡片会在“官方网站”下一行显示“加入官方群”链接；
- 普通图片回退消息会在图片前的前缀文本中显示该链接；
- Markdown 前缀不会重复插入同一群链接。

邀请链接和访问令牌只应保存在部署机环境变量或 NoneBot dotenv 中，不要提交到 Git。

## 图片上传保护

Gensokyo 上传前会进行以下检查：

- 图片不能为空；
- 图片大小不得超过 10 MiB；
- 必须能够读取图片尺寸；
- 上传接口必须返回 2xx；
- URL 必须是有效的 `http://` 或 `https://` 公网形式；
- width/height 必须是正整数。

相同图片会按上传地址 + SHA-256 内容哈希命中缓存，避免短时间内重复上传。

## 目录中的关键文件

```text
__init__.py          插件元数据、/help matcher 与顶层异常回退
config.py            环境变量 / NoneBot dotenv 配置
gensokyo.py          分页、渲染、上传、Gensokyo/普通 OneBot 消息适配
compat.py            Markdown / Keyboard 兼容载荷
menu.py              amia-core CapabilityProvider 聚合
templates/help.html  本地帮助图片模板
tests/               单元测试
CHANGELOG.md         版本更新记录
```

## 测试

在 MizukiBot/Amia 项目环境中可执行：

```powershell
& '.venv/Scripts/python.exe' -m unittest discover -s src/plugins/Amia-plugin-help/tests -v
& '.venv/Scripts/python.exe' -m unittest discover -s src/plugins/pjskhelp/tests -v
& '.venv/Scripts/python.exe' -m compileall -q src/plugins/Amia-plugin-help src/plugins/pjskhelp
```

测试覆盖包括：

- 帮助参数解析；
- 0/1/12/13/25/41 条目的分页边界；
- Keyboard 行列与翻页按钮；
- Gensokyo Markdown 载荷；
- 普通图片回退；
- 上传缓存与异常边界；
- NoneBot dotenv 配置读取；
- renderer 失败后的重启与重试；
- 官方群链接位置与去重；
- PJSK 帮助入口不被通用 `/help` 误捕获。

真实 QQ 客户端中的按钮行为、Playwright 浏览器环境和 Gensokyo 图床仍应在部署机进行集成验证。

## 更新日志

完整更新记录见 [CHANGELOG.md](./CHANGELOG.md)。

当前 016 版本主要包含：Gensokyo Markdown 分页、动态 Keyboard、NapCat/普通 OneBot 回退、官方群链接配置、NoneBot dotenv 读取，以及 htmlrender 截图恢复机制。
