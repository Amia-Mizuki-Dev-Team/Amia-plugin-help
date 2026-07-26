# Amia-plugin-help

`Amia-plugin-help` 是 Amia 的帮助前置与 Release009 兼容层。图片菜单主体采用外部 PicMenu Next，不复制其完整实现。

## 权威上游

- repository: [`lgc-NB2Dev/nonebot-plugin-picmenu-next`](https://github.com/lgc-NB2Dev/nonebot-plugin-picmenu-next)
- reviewed branch: `master`
- locked commit: `241c4c34889ecaba08de07296d63981e5c7e100b`
- license: MIT
- upstream status: GitHub archived/read-only; use the locked commit, not a floating branch

PicMenu Next README documents the image help interface, PicMenu-compatible three-level menus, Alconna command discovery, fuzzy/pinyin search, Markdown help, hidden controls, custom templates, Mixin extensions, and external JSON/YAML/TOML menu files.

The MIT copyright and permission notice must be retained if any upstream source or substantial portion is copied. This repository currently uses the upstream as an external dependency/reference and does not copy its source tree.

The review-pinned dependency declaration is in `requirements-release009.txt`; installation is intentionally not performed by the offline test run.

## Architecture

```text
Amia-plugin-help
  ├─ existing help/帮助 prefix matcher (priority=1, block=False)
  ├─ config.py: safe configurable prefix text
  ├─ menu.py: optional PicMenu discovery + Core CapabilityProvider aggregation
  └─ compat.py: Release009 string/array, Markdown/Keyboard, local-media safety, fallback
                 ↓
       nonebot-plugin-picmenu-next (external menu core)
```

The Amia layer does not own the complete PicMenu renderer. It prepares external-menu-compatible capability data and validates/degrades outgoing payloads before an adapter-specific sender handles them.

## Commands

The existing prefix matcher accepts:

```text
help
帮助
```

It only sends the prefix for an empty argument and keeps `block=False`, allowing PicMenu Next or another detailed help matcher to continue processing. Parameterized forms such as `help economy` are left to the detailed menu plugin.

## Configuration

```env
AMIA_HELP_PREFIX_ENABLED=true
AMIA_HELP_PREFIX_TEXT=欢迎使用 Mizuki Bot。帮助菜单由 PicMenu Next 提供。
AMIA_HELP_DOCS_URL=
AMIA_HELP_GROUP_ID=
AMIA_HELP_QBIND_TEXT=使用前请先完成 qbind 绑定。
```

No account, group, token, internal address, or production URL is embedded in the default prefix.

## Release009 compatibility boundary

`compat.py` provides offline-checkable helpers for:

- string and array message forms;
- Markdown and Keyboard payload shape;
- local keyboard image path validation under a configured root;
- Markdown-to-text degradation when Markdown is unavailable;
- capability aggregation without allowing one failing provider to break Help.

These helpers do not claim live Bot compatibility. `compatibility.yml` remains false until adapter-level Release009 tests verify the field.

## Tests

```bash
python -m unittest discover -s tests
```

The isolated Release009 suite covers plugin import/Matcher registration, synthetic string/array messages, Markdown/Keyboard, path traversal rejection, text degradation, and CapabilityProvider menu aggregation. Live Bot, image rendering, real local upload, and production group tests remain `NOT RUN - USER ENVIRONMENT REQUIRED`.
