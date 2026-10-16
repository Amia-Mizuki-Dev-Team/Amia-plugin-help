# 更新日志

本文件记录 `Amia-plugin-help` 的重要变更。当前代码版本标记为 **016**。

## [016] - 2026-10-06

本轮更新集中在帮助菜单的 Gensokyo Markdown/Keyboard 交互、普通 OneBot 回退链路、配置读取与图片渲染稳定性。

### 新增

- 新增 Gensokyo Markdown 帮助卡片分页：
  - 首页与插件详情均按页展示；
  - 默认每页最多 12 项；
  - Keyboard 每行最多 3 个按钮；
  - 支持 `/help --page N` 与 `/help <插件序号> --page N`。
- 新增动态 Keyboard，按钮可直接进入插件、功能详情或切换页面。
- 新增 `AMIA_HELP_GROUP_URL` 配置，用于在帮助卡片中显示“加入官方群”链接。
- 新增图片上传缓存，按图片内容哈希复用 Gensokyo `uploadpicv2` 结果，并限制缓存大小。
- 新增 htmlrender 截图串行锁，避免并发截图互相影响。

### 调整

- 帮助数据改为直接聚合已加载插件的 `PluginMetadata`、`extra.menu_data` 与 `amia-core` 的 `CapabilityProvider`。
- PicMenu Next 不再作为生产运行时依赖；帮助图片由本插件本地模板直接渲染。
- Gensokyo Markdown 正文不再重复展开 Keyboard 按钮命令，缩短消息体；不支持 Keyboard 时仍通过按钮的 `unsupport_tips` 或普通消息回退提供可执行命令。
- “很忙”功能从帮助菜单展示列表中隐藏。
- `AMIA_HELP_GROUP_URL` 在 Gensokyo Markdown 中调整到“官方网站”下一行；普通图片回退仍在图片前的前缀文本中展示。
- 帮助卡片标题限制为最多两行，并限制卡片最大高度，避免长插件名撑高整页。
- `/help` 继续作为通用帮助入口；`pjsk帮助` 仍由独立 PJSK 帮助插件处理。

### 修复

- 修复仅从 `os.environ` 读取配置的问题：现在也会读取 NoneBot driver 的 dotenv 配置。
- 修复 Gensokyo/普通 OneBot 场景中帮助图片与按钮回退链路不一致的问题。
- 修复 Keyboard 命令提示在 Markdown 正文中重复显示的问题。
- 修复官方群链接重复或位置不符合预期的问题。
- 修复 htmlrender/Playwright 共享浏览器会话异常后直接退化为纯文本的问题。

### 稳定性

- htmlrender 首次截图失败时会：
  1. 记录异常类型；
  2. 关闭并重建共享 renderer；
  3. 使用 `device_scale_factor=1.0` 重试；
  4. 将截图超时放宽到 60 秒。
- Gensokyo 图片上传会校验：
  - 图片非空且不超过 10 MiB；
  - 本地可读取图片尺寸；
  - HTTP 状态码有效；
  - 返回 URL 必须是公开的 HTTP/HTTPS 地址；
  - width/height 必须是正整数。
- Gensokyo 自动识别结果带 300 秒缓存，避免每次帮助请求都调用版本探测 API。

### 配置

本轮涉及的主要配置项：

- `AMIA_HELP_MARKDOWN_MODE=auto|on|off`
- `AMIA_HELP_GENSOKYO_UPLOAD_URL`
- `AMIA_HELP_GENSOKYO_ACCESS_TOKEN`
- `AMIA_HELP_UPLOAD_TIMEOUT_SECONDS`
- `AMIA_HELP_IMAGE_CACHE_TTL_SECONDS`
- `AMIA_HELP_IMAGE_CACHE_MAX_ENTRIES`
- `AMIA_HELP_BUTTON_PAGE_SIZE`
- `AMIA_HELP_BUTTON_COMMAND_PREFIX`
- `AMIA_HELP_PREFIX_ENABLED`
- `AMIA_HELP_PREFIX_TEXT`
- `AMIA_HELP_DOCS_URL`
- `AMIA_HELP_GROUP_URL`
- `AMIA_HELP_GROUP_ID`
- `AMIA_HELP_QBIND_TEXT`
- `AMIA_HELP_FOOTER_TEXT`

邀请链接与访问令牌只应保存在部署机环境变量或 NoneBot dotenv 配置中，不应提交到仓库。

### 本轮参考提交

- `0a387c6` — add Gensokyo markdown help pagination
- `4f599cc` — restore dynamic image menu and NapCat fallback
- `7918f4e` — hide busy command from menu
- `614a6e2` — remove visible keyboard command hints
- `053ce78` — add configurable official group link
- `d0aa773` — read dotenv settings from NoneBot config
- `361a43f` — place official group link under website，并补强渲染重试与卡片布局

> 这是仓库首次建立独立 CHANGELOG；更早版本暂不在此文件中追溯。
