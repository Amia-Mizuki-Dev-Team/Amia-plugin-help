# Amia-plugin-help

`Amia-plugin-help` 是 Amia 的通用图片帮助总菜单。它把 NoneBot 已加载插件的
`PluginMetadata`、`extra.menu_data` 和 `amia-core` 的 `CapabilityProvider` 聚合成一套本地
菜单数据，然后用 `nonebot-plugin-htmlrender` 生成帮助图，并在 Gensokyo 环境中把图片和
动态 Keyboard 放在同一条 Markdown 消息里。

这里保留了原来图片菜单的交互方式，但不再把 PicMenu Next 作为生产运行时依赖。因此正式
环境不会因为缺少 `nonebot_plugin_picmenu_next` 而在导入 `Amia-plugin-help` 时崩溃。

## 交互流程

```text
/help 或 帮助
  └─ 第 1 页图片 + 12 个插件按钮（每行 3 个）+ 下一页
       ├─ /help 3       插件 3 的功能图片和按钮
       ├─ /help 3 1     功能 1 的详情图片和返回按钮
       └─ /help --page 2 首页下一页
```

首页最多展示 12 个插件；按钮数量超过 12 时自动生成分页。插件详情也按 12 个功能分页，
所以第 13 个及之后的插件或功能不会被截断。按钮使用 `AMIA_HELP_BUTTON_COMMAND_PREFIX`
配置的命令前缀，默认是 `/`。

`pjsk帮助` 仍由 `pjskhelp` 单独处理，不会接管通用 `/help`。

## 图片与消息适配

- 图片模板位于 `templates/help.html`，只使用 htmlrender，不复制或导入外部菜单插件代码；
- 普通 OneBot 适配器发送生成的图片；
- Gensokyo 适配器会先调用 `uploadpicv2`，再发送 Markdown 图片和
  `keyboard.content.rows`；上传失败时回退为图片消息；
- Markdown 正文不再重复展开按钮命令，避免首页和插件详情过长；每个按钮的
  `action.data` 与 `unsupport_tips` 仍保留在 Keyboard 载荷中，由 Gensokyo 按兼容提示处理；
- 图片页脚固定显示 `Amia_晓山瑞希 Powered By HX-Wrdzgzs`，可用
  `AMIA_HELP_FOOTER_TEXT` 覆盖；
- 图床地址、令牌、缓存和页大小都从环境变量读取，令牌不能提交到 Git；
- `RENDER_BACKEND=playwright` 时，部署机需要准备对应的 Playwright 浏览器。

## 配置

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

`AMIA_HELP_MARKDOWN_MODE=off` 可关闭 Gensokyo Markdown，仅保留图片回退；`on` 会跳过版本探测，
但仍要求 OneBot 适配器。页大小会被限制在 `1..12`。

设置 `AMIA_HELP_GROUP_URL` 后，帮助文档下一行会输出 Markdown 格式的“加入官方群”链接。
邀请链接只应放在部署机的 `.env` 中，不要提交到 Git 或打包发布物。

## 测试

```powershell
& '.venv/Scripts/python.exe' -m unittest discover -s src/plugins/Amia-plugin-help/tests -v
& '.venv/Scripts/python.exe' -m unittest discover -s src/plugins/pjskhelp/tests -v
& '.venv/Scripts/python.exe' -m compileall -q src/plugins/Amia-plugin-help src/plugins/pjskhelp
```

离线测试覆盖消息段兼容、Markdown/Keyboard 载荷、插件元数据聚合、0/1/12/13/25/41
条目的分页边界，以及 PJSK 通用帮助别名不再被误捕获。htmlrender 出图还需要在部署机上
进行 Playwright 和真实 Gensokyo 图床验证；本地单元测试不能替代 QQ 客户端中的按钮点击验证。
