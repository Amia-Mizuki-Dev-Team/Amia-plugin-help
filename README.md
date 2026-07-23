# Amia-plugin-help

`Amia-plugin-help` 是 Mizuki Bot 的文字帮助前置插件。

它在主图片帮助或分类帮助插件处理 `help` 指令之前，先发送一段简短文字说明，并通过 `block=False` 让同一条消息继续交给后续帮助插件。

本插件不是完整帮助菜单，也不负责维护所有业务插件的指令列表。

当前状态：有可运行的前置帮助实现，但尚未形成完整帮助系统。后续统一帮助应优先消费各插件提供的 `CapabilityProvider`。

## 插件作用

```text
用户发送 help
      ↓
Amia-plugin-help 发送简短文字说明
      ↓ block=False
后续图片帮助或分类帮助继续处理
```

它适合放置：

- Bot 使用入口；
- 文档地址；
- 交流群说明；
- qbind 提示；
- 少量全局注意事项。

详细指令分类应由主帮助菜单或各业务插件负责。

## 当前指令

```text
help
帮助
```

只有无参数形式发送前置文字：

```text
/help
帮助
```

有参数时跳过：

```text
/help 7
/help economy
帮助 economy
```

这样后续帮助插件可以自行处理分类或页码参数。

## Matcher 配置

当前关键配置：

```python
priority=1
block=False
```

处理函数必须使用：

```python
await matcher.send(...)
```

不要使用：

```python
await matcher.finish(...)
```

`finish()` 会结束事件传播，可能导致后续图片帮助或分类帮助无法执行。

## 执行顺序要求

前置文字插件应先运行，后续完整帮助插件再运行。

维护时必须确认：

- 本插件优先级仍为 `1`；
- 后续帮助插件使用更大的 priority；
- 本插件保持 `block=False`；
- 后续插件不会因为本插件已发送消息而错误跳过；
- 同一条指令不会被多个完整帮助插件重复回复。

修改 priority 或 block 前必须做完整命令链测试。

## 当前文案

当前文字直接写在 `__init__.py` 中，包含：

- Bot 使用入口；
- 群聊使用说明；
- PJSK 私聊限制；
- qbind 绑定提示；
- 文档或网站入口。

这种方式可以运行，但存在：

- 修改文案必须改代码；
- URL、群号容易过期；
- 无法按环境切换；
- 可能与主帮助菜单命名不一致；
- 不方便单独测试模板。

## 推荐配置化

后续可以使用：

```env
AMIA_HELP_PREFIX_ENABLED=true
AMIA_HELP_DOCS_URL=
AMIA_HELP_GROUP_ID=
AMIA_HELP_QBIND_TEXT=
```

较长文字建议放入独立模板文件，而不是塞进单个环境变量。

示例目录：

```text
__init__.py
config.py
renderer.py
templates/
  prefix.txt
tests/
  test_help_chain.py
```

职责：

- `config.py`：开关、URL、群号等配置；
- `renderer.py`：组合用户可见文字；
- `templates/`：前置说明模板；
- `tests/`：参数判断和命令链测试。

## 与其他插件的边界

本插件当前不依赖：

- amia-core；
- SQLite；
- qbind 数据库；
- Economy；
- Send。

它可以在文案中提示用户使用 qbind，但不能直接读取 qbind 数据或判断绑定状态。

完整业务帮助不应复制进本仓库。例如 Economy 指令变化时，应由 Economy 自己或统一能力索引更新，而不是手工维护两份超长列表。

## 后续能力索引方向

以后如需自动生成帮助菜单，可以由各插件通过 `CapabilityProvider` 暴露：

```text
插件名称
功能分类
指令名称
参数说明
权限节点
可用上下文
```

Help 再统一消费这些能力，而不是继续硬编码全部插件说明。

这属于后续架构方向，当前版本尚未实现。

## 测试

至少覆盖：

- `/help` 发送前置文字；
- `帮助` 别名可用；
- `/help 7` 不发送前置文字；
- `/help economy` 不发送前置文字；
- handler 结束后事件继续传播；
- 后续帮助 matcher 能继续执行；
- 配置关闭时不发送；
- 空模板安全跳过；
- 文案不包含失效 URL、内部地址或敏感信息。

## 已知限制

- 文案仍硬编码；
- 没有配置类；
- 没有自动能力索引；
- 缺少完整命令链测试；
- URL 和群号需要人工维护。

## 推荐开发顺序

1. 将文字移到模板；
2. 拆分 URL、群号和 qbind 提示配置；
3. 增加无参数和有参数测试；
4. 增加后续 matcher 继续执行的集成测试；
5. 最后再评估 CapabilityProvider 自动索引。

## 维护边界

- 保持前置文字简短；
- 不复制整份业务帮助菜单；
- 不在代码中写 token、管理员账号或内部地址；
- 不随意修改 priority 和 block；
- 外部入口变化时及时同步文案；
- 当前仓库尚未确定公开许可证。
