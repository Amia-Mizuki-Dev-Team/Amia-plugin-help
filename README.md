# Amia-plugin-help

Amia 的帮助入口、菜单聚合层和 Gensokyo-NewQQ Release010 出站兼容层。完整图片菜单由 PicMenu Next 提供，本仓库不复制其源码。

## 架构

```text
用户发送 help / 帮助 / @Bot help
              │
              ├─ Amia 前置 Matcher：发送简短中文提示，block=False
              ├─ CapabilityProvider：聚合各插件菜单能力
              ├─ Release010 兼容层：Markdown、Keyboard、文件和降级
              └─ PicMenu Next：渲染首页、分类页和功能详情
```

前置 Matcher 不拦截 PicMenu，因此不应阻断图片菜单；带参数的 `help economy`、`help pjsk` 等查询交给详细菜单实现处理。

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

- `help`、`帮助` 和 `@Bot help` 前置提示；
- PicMenu 三级菜单、模糊/拼音搜索和外部菜单数据接入；
- 聚合 `amia-core` 的 `CapabilityProvider`；
- 处理字符串、数组和映射形式的消息段；
- 构造 Release010 Markdown、Keyboard 和文件消息载荷；
- 校验本地媒体路径，拒绝目录穿越；
- Markdown、Keyboard 或 Provider 不可用时降级为文本；
- 单个 Provider 失败不会破坏整个帮助菜单。

## 配置

```env
AMIA_HELP_PREFIX_ENABLED=true
AMIA_HELP_PREFIX_TEXT=欢迎使用 Mizuki Bot。帮助菜单由 PicMenu Next 提供。
AMIA_HELP_DOCS_URL=
AMIA_HELP_GROUP_ID=
AMIA_HELP_QBIND_TEXT=使用前请先完成 qbind 绑定。
```

默认配置不写入真实账号、群号、Token、内网地址或生产 URL。

## 目录职责

- `__init__.py`：插件元数据、前置 Matcher 和 PicMenu 加载；
- `menu.py`：固定上游信息、PicMenu 可用性检查和菜单聚合；
- `compat.py`：Release010 消息规范化、Markdown/Keyboard/文件载荷和降级；
- `config.py`：前置提示配置；
- `tests/test_release010.py`：离线兼容回归测试。

## 测试

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
git diff --check
```

离线测试覆盖插件加载、Matcher 注册、字符串/数组消息、Markdown、Keyboard、本地路径安全、文本降级和 CapabilityProvider 聚合。本地 PicMenu 页面渲染可以作为渲染证据，但不能代替真实 QQ 客户端中的发送、显示和按钮点击。

## 验证边界

以下项目没有实机证据时必须保持 `NOT RUN` 或 `unverified`：

- `@Bot` 在真实 Gensokyo 事件中的剥离；
- Markdown 图片在 QQ 客户端中的显示；
- Keyboard 显示和点击；
- 本地图片上传；
- 图床、Markdown 和 Keyboard 失败后的真实降级；
- PicMenu 与前置 Matcher 是否出现重复回复。

兼容状态以 `compatibility.yml` 为准，自动化通过不能直接写成生产环境已验证。
