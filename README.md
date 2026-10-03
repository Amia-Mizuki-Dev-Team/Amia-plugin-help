# Amia-plugin-help

Amia 的帮助入口、菜单聚合层和 Gensokyo-NewQQ Release015 出站适配层。完整图片菜单由 PicMenu Next 提供，本仓库不复制其源码。

## 架构

```text
用户发送 help / 帮助 / @Bot help
              │
              ├─ Amia 前置 Matcher：分页扩展优先，普通查询交给 PicMenu
              ├─ CapabilityProvider：聚合各插件菜单能力
              ├─ Release015 适配层：Markdown 图片、动态 Keyboard、上传和降级
              └─ PicMenu Next：渲染首页、分类页和功能详情
```

PicMenu 的三个模板都可以选择 `amia_gensokyo`。模板先复用默认模板生成最终帮助图，再从同一次渲染得到的可见插件/功能数据生成按钮，因此不会维护第二套插件清单。普通 `/help`、`/help 3`、`/help 3 2` 仍由 PicMenu 原 matcher 处理；分页扩展使用 `/help --page 2` 和 `/help 3 --page 2`。

## PicMenu Next 上游

- 仓库：[`lgc-NB2Dev/nonebot-plugin-picmenu-next`](https://github.com/lgc-NB2Dev/nonebot-plugin-picmenu-next)
- 分支：`master`
- 固定提交：`a0f8f729927c947e315f5719cfd1cd2720b2ee0c`
- 许可证：MIT

部署必须安装固定提交，不能依赖浮动分支：

```text
nonebot-plugin-picmenu-next @ git+https://github.com/lgc-NB2Dev/nonebot-plugin-picmenu-next.git@a0f8f729927c947e315f5719cfd1cd2720b2ee0c
```

如果复制或修改上游源码，必须保留 MIT 版权和许可声明。本仓库当前只依赖上游，不包含其源码树。

## 当前能力

- `help`、`帮助` 和 `@Bot help` 前置入口；
- PicMenu 三级菜单、模糊/拼音搜索和外部菜单数据接入；
- 聚合 `amia-core` 的 `CapabilityProvider`；
- Gensokyo Release015 原生 Markdown 图文卡片和标准 `keyboard.content.rows`；
- Markdown 卡片包含可点击的官方帮助入口 [`help.mizuki.top`](https://help.mizuki.top)；
- 按当前可见插件/功能动态生成按钮，每页最多 12 个条目、每行 3 个按钮；
- 分页导航覆盖全部条目，不补空按钮，不丢弃第 21 个以后的插件；
- 图片由 PicMenu 默认模板产生，上传前提取原始 JPEG 字节；
- 处理字符串、数组和映射形式的消息段；
- 校验本地媒体路径，拒绝目录穿越；
- Markdown、Keyboard、图床或 Provider 不可用时降级为原 PicMenu 图片；
- 单个 Provider 失败不会破坏整个帮助菜单。

## 配置

```env
AMIA_HELP_PREFIX_ENABLED=true
AMIA_HELP_PREFIX_TEXT=欢迎使用 Amia_晓山瑞希。
AMIA_HELP_DOCS_URL=
AMIA_HELP_GROUP_ID=
AMIA_HELP_QBIND_TEXT=使用前请先完成 qbind 绑定。

# Gensokyo Markdown（建议与 Gensokyo 的 config.yml 一起通过进程环境注入）
AMIA_HELP_MARKDOWN_MODE=auto
AMIA_HELP_GENSOKYO_UPLOAD_URL=http://127.0.0.1:15630/uploadpicv2
AMIA_HELP_GENSOKYO_ACCESS_TOKEN=
AMIA_HELP_UPLOAD_TIMEOUT_SECONDS=15
AMIA_HELP_IMAGE_CACHE_TTL_SECONDS=3600
AMIA_HELP_IMAGE_CACHE_MAX_ENTRIES=64
AMIA_HELP_BUTTON_PAGE_SIZE=12
AMIA_HELP_BUTTON_COMMAND_PREFIX=/

# PicMenu Next
PMN_INDEX_TEMPLATE=amia_gensokyo
PMN_DETAIL_TEMPLATE=amia_gensokyo
PMN_FUNC_DETAIL_TEMPLATE=amia_gensokyo
# 可选：覆盖 PicMenu 图片底部默认署名（路径按 H:\Amia-Develop 部署目录解析）
PMN_DEFAULT_ADDITIONAL_CSS=[".\\src\\plugins\\Amia-plugin-help\\picmenu_footer.css"]
```

`AMIA_HELP_GENSOKYO_ACCESS_TOKEN` 不能提交到 Git。生产环境应从本机未跟踪 `.env` 或进程环境注入；如果 Gensokyo 图床要求令牌而上传失败，会自动回退原 PicMenu 图片。页大小会被限制在 `1..12`。`picmenu_footer.css` 只覆盖图片底部署名，不修改 PicMenu 上游包。

## 目录职责

- `__init__.py`：插件元数据、分页 Matcher 和 PicMenu 加载；
- `menu.py`：固定上游信息、PicMenu 可用性检查和菜单聚合；
- `compat.py`：OneBot/Gensokyo 消息规范化、Markdown/Keyboard/文件载荷和降级；
- `config.py`：前置提示和 Markdown 适配配置；
- `gensokyo.py`：模板、分页、图床上传、Gensokyo 检测和原生卡片构建；
- `tests/test_release010.py`：离线兼容、动态分页和载荷回归测试（文件名保留以兼容既有调用）。

## 测试

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
git diff --check
```

离线测试覆盖插件加载、Matcher 注册、字符串/数组消息、Markdown、Keyboard、本地路径安全、文本降级、CapabilityProvider 聚合和 0/1/5/6/20/21/40/41 条目的动态分页。运行时仍需要 Gensokyo 图床、QQ API 和真实客户端分别验证；本地测试不能代替真实 QQ 客户端中的发送、显示和按钮点击。

## 验证边界

以下项目没有实机证据时必须保持 `NOT RUN` 或 `unverified`：

- `@Bot` 在真实 Gensokyo 事件中的剥离；
- Markdown 图片在 QQ 客户端中的显示；
- Keyboard 显示和点击；
- 本地图片上传；
- 图床、Markdown 和 Keyboard 失败后的真实降级；
- PicMenu 与前置 Matcher 是否出现重复回复。

兼容状态以 `compatibility.yml` 为准，自动化通过不能直接写成生产环境已验证。
