import asyncio
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from config import (
    DEFAULT_FOOTER_TEXT,
    prefix_enabled,
    render_footer_text,
    render_prefix_text,
)


class HelpTests(unittest.TestCase):
    def test_footer_text_defaults_to_requested_branding_and_is_configurable(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(render_footer_text(), DEFAULT_FOOTER_TEXT)
        with patch.dict(
            os.environ,
            {"AMIA_HELP_FOOTER_TEXT": "Custom footer"},
            clear=False,
        ):
            self.assertEqual(render_footer_text(), "Custom footer")

    def test_prefix_text_is_configurable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AMIA_HELP_PREFIX_TEXT": "Amia help",
                "AMIA_HELP_DOCS_URL": "https://help.example.test",
                "AMIA_HELP_GROUP_URL": "https://group.example.test/invite",
                "AMIA_HELP_QBIND_TEXT": "",
                "AMIA_HELP_GROUP_ID": "12345",
            },
            clear=False,
        ):
            self.assertTrue(prefix_enabled())
            self.assertEqual(
                render_prefix_text(),
                "Amia help\n"
                "帮助文档：https://help.example.test\n"
                "官方群：[加入官方群](https://group.example.test/invite)\n"
                "交流群：12345",
            )

    def test_plugin_loads_without_picmenu_dependency(self) -> None:
        import nonebot

        nonebot.init()
        package_name = "amia_help_text_only"
        spec = importlib.util.spec_from_file_location(
            package_name,
            PLUGIN_ROOT / "__init__.py",
            submodule_search_locations=[str(PLUGIN_ROOT)],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        try:
            spec.loader.exec_module(module)
            self.assertEqual(module.mizuki_text_help.priority, 0)
            self.assertTrue(module.mizuki_text_help.block)
            self.assertNotIn("nonebot_plugin_picmenu_next", sys.modules)
            self.assertNotIn("PICMENU", module.__dict__)
        finally:
            sys.modules.pop(package_name, None)
            sys.modules.pop(f"{package_name}.config", None)

    def test_index_and_detail_buttons_are_paged(self) -> None:  # noqa: PLR0915
        import nonebot

        nonebot.init()
        package_name = "amia_help_paging_test"
        spec = importlib.util.spec_from_file_location(
            package_name,
            PLUGIN_ROOT / "__init__.py",
            submodule_search_locations=[str(PLUGIN_ROOT)],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        try:
            spec.loader.exec_module(module)
            gensokyo = sys.modules[f"{package_name}.gensokyo"]
            infos = [SimpleNamespace(name=f"插件 {index}") for index in range(1, 42)]
            rows, window = gensokyo.build_index_keyboard(infos, 1)
            buttons = [button for row in rows for button in row]
            self.assertEqual(window.total_pages, 4)
            self.assertEqual(buttons[0]["action"]["data"], "/help 1")
            self.assertEqual(buttons[-1]["action"]["data"], "/help --page 2")
            self.assertEqual(
                gensokyo.parse_page_request("3 --page 2"),
                gensokyo.PageRequest("3", 2),
            )
            self.assertEqual(
                gensokyo.parse_help_request("3 2"),
                gensokyo.HelpRequest(plugin_index=3, function_index=2),
            )
            info = SimpleNamespace(
                pm_data=[
                    SimpleNamespace(func=f"功能 {index}") for index in range(1, 22)
                ]
            )
            detail_rows, detail_window = gensokyo.build_detail_keyboard(info, 2, 1)
            detail_buttons = [button for row in detail_rows for button in row]
            self.assertEqual(detail_window.total_pages, 2)
            self.assertEqual(detail_buttons[0]["action"]["data"], "/help 3 1")
            self.assertIn(
                "/help 3 --page 2",
                [button["action"]["data"] for button in detail_buttons],
            )

            for count, expected_pages in ((0, 1), (1, 1), (12, 1), (13, 2), (25, 3)):
                current_infos = [
                    SimpleNamespace(name=f"动态插件 {index}")
                    for index in range(1, count + 1)
                ]
                current_rows, current_window = gensokyo.build_index_keyboard(
                    current_infos,
                    1,
                )
                current_buttons = [
                    button for row in current_rows for button in row
                ]
                self.assertEqual(current_window.total_pages, expected_pages)
                self.assertEqual(
                    len(
                        [
                            button
                            for button in current_buttons
                            if button["id"].startswith("plugin-")
                        ]
                    ),
                    min(count, 12),
                )
                self.assertEqual(
                    len({button["id"] for button in current_buttons}),
                    len(current_buttons),
                )
                if expected_pages > 1:
                    self.assertIn(
                        "/help --page 2",
                        [button["action"]["data"] for button in current_buttons],
                    )
                    last_rows, last_window = gensokyo.build_index_keyboard(
                        current_infos,
                        expected_pages,
                    )
                    last_buttons = [
                        button for row in last_rows for button in row
                    ]
                    self.assertEqual(last_window.page, expected_pages)
                    self.assertIn(
                        "/help --page 1",
                        [button["action"]["data"] for button in last_buttons],
                    )

            async def fake_is_gensokyo_bot(_bot: object) -> bool:
                return True

            async def fake_upload_image(
                _raw: bytes,
                _config: object,
            ) -> object:
                return gensokyo.UploadedImage(
                    url="https://cdn.example.test/help.png",
                    width=810,
                    height=540,
                )

            with (
                patch.object(gensokyo, "is_gensokyo_bot", fake_is_gensokyo_bot),
                patch.object(gensokyo, "upload_image", fake_upload_image),
            ):
                message = asyncio.run(
                    gensokyo._render_card(
                        SimpleNamespace(),
                        b"rendered-image",
                        title="帮助菜单",
                        window=window,
                        total=len(infos),
                        rows=rows,
                        include_prefix=True,
                    )
                )
            self.assertEqual(message[0].type, "markdown")
            card = message[0].data["data"]
            self.assertIn(
                "https://cdn.example.test/help.png", card["markdown"]["content"]
            )
            self.assertNotIn(
                "按钮命令（键盘不可用时发送）", card["markdown"]["content"]
            )
            self.assertNotIn("插件 1：/help 1", card["markdown"]["content"])
            self.assertEqual(len(card["keyboard"]["content"]["rows"]), len(rows))
            self.assertEqual(
                card["keyboard"]["content"]["rows"][0]["buttons"][0]["action"][
                    "unsupport_tips"
                ],
                "请手动发送：/help 1",
            )

            captured: dict[str, object] = {}

            async def fake_render_template(**templates: object) -> bytes:
                captured.update(templates)
                return b"rendered"

            with patch.object(gensokyo, "_render_template", fake_render_template):
                rendered = asyncio.run(
                    gensokyo.render_index_image(
                        infos,
                        window,
                        gensokyo.MarkdownHelpConfig(),
                    )
                )
            self.assertEqual(rendered, b"rendered")
            self.assertEqual(captured["footer_text"], DEFAULT_FOOTER_TEXT)
        finally:
            for name in list(sys.modules):
                if name == package_name or name.startswith(f"{package_name}."):
                    sys.modules.pop(name, None)

    def test_plugin_metadata_and_capability_entries_are_collected(self) -> None:
        import nonebot
        from nonebot.plugin import PluginMetadata

        nonebot.init()
        package_name = "amia_help_collect_test"
        spec = importlib.util.spec_from_file_location(
            package_name,
            PLUGIN_ROOT / "__init__.py",
            submodule_search_locations=[str(PLUGIN_ROOT)],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        try:
            spec.loader.exec_module(module)
            gensokyo = sys.modules[f"{package_name}.gensokyo"]
            plugin = SimpleNamespace(
                name="economy",
                module_name="economy",
                metadata=PluginMetadata(
                    name="Amia Economy",
                    description="经济功能",
                    usage="签到\n商城",
                    extra={
                        "menu_data": [
                            {
                                "func": "签到",
                                "trigger_condition": "签到",
                                "brief_des": "每日签到",
                            }
                        ]
                    },
                ),
            )
            infos = gensokyo.collect_help_infos([plugin])
            self.assertEqual(len(infos), 1)
            self.assertEqual(infos[0].name, "Amia Economy")
            self.assertEqual(infos[0].pm_data[0]["func"], "签到")
            self.assertNotIn("nonebot_plugin_picmenu_next", sys.modules)

            hidden_plugin = SimpleNamespace(
                name="busy",
                module_name="busy",
                metadata=PluginMetadata(
                    name="Busy Plugin",
                    description="忙碌功能",
                    usage="很忙",
                    extra={
                        "menu_data": [
                            {
                                "func": "很忙",
                                "trigger_condition": "很忙",
                            },
                            {
                                "func": "保留功能",
                                "trigger_condition": "保留功能",
                            },
                        ]
                    },
                ),
            )
            hidden_infos = gensokyo.collect_help_infos([hidden_plugin])
            self.assertEqual(
                [item["func"] for item in hidden_infos[0].pm_data],
                ["保留功能"],
            )
        finally:
            for name in list(sys.modules):
                if name == package_name or name.startswith(f"{package_name}."):
                    sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
