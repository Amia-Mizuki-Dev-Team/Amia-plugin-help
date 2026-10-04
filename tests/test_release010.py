"""Regression coverage kept under the historical Release010 test filename."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from nonebot.adapters.onebot.v11 import Message, MessageSegment

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from compat import (
    build_button_fallback_text,
    build_file_segment_payload,
    build_help_outbound,
    build_markdown_keyboard_payload,
    normalize_message_segments,
    remove_bot_mentions,
    safe_local_media_path,
)
from config import MarkdownHelpConfig, render_prefix_text
from menu import build_amiya_menu, collect_capabilities


class CapabilityProvider:
    def get_supported_capabilities(self) -> list[str]:
        return ["zeta", "alpha", "alpha"]


class Registry:
    def get_capability_providers(self) -> dict[str, CapabilityProvider]:
        return {"synthetic-r010": CapabilityProvider()}


class Release010HelpTests(unittest.TestCase):
    def test_string_array_and_extended_cq_segments(self) -> None:
        self.assertEqual(
            normalize_message_segments("help"),
            [{"type": "text", "data": {"text": "help"}}],
        )
        segments = normalize_message_segments(
            "[CQ:card,type=xml]x[CQ:input_notify,body=ok][CQ:stream,id=s1]"
        )
        self.assertEqual(
            [item["type"] for item in segments],
            ["card", "text", "input_notify", "stream"],
        )
        self.assertEqual(
            remove_bot_mentions(
                [
                    {"type": "at", "data": {"user_id": "bot-r010"}},
                    {"type": "text", "data": {"text": "help"}},
                ],
                "bot-r010",
            ),
            [{"type": "text", "data": {"text": "help"}}],
        )

    def test_markdown_keyboard_and_local_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_markdown_keyboard_payload(
                "# Help",
                [[{"label": "Economy", "action": {"data": "/help 1"}}]],
                media_root=root,
            )
            button = payload["keyboard"]["content"]["rows"][0]["buttons"][0]
            self.assertEqual(button["render_data"]["label"], "Economy")
            self.assertEqual(button["action"]["data"], "/help 1")
            with self.assertRaises(ValueError):
                build_markdown_keyboard_payload(
                    "# Help",
                    [[{"label": "Economy", "local_image": "icons/economy.png"}]],
                    media_root=root,
                )
            with self.assertRaises(ValueError):
                safe_local_media_path(root, "../outside.png")

            segment = MessageSegment("markdown", {"data": payload})
            serialized = [
                {"type": item.type, "data": item.data} for item in Message([segment])
            ]
            self.assertEqual(
                serialized[0]["data"]["data"]["markdown"]["content"],
                "# Help",
            )
            json.dumps(serialized, ensure_ascii=False)

    def test_button_fallback_preserves_every_action_command(self) -> None:
        fallback = build_button_fallback_text(
            [
                [
                    {
                        "render_data": {"label": "插件 1"},
                        "action": {"data": "/help 1"},
                    },
                    {
                        "render_data": {"label": "下一页"},
                        "action": {"data": "/help --page 2"},
                    },
                ]
            ]
        )
        self.assertIn("插件 1：/help 1", fallback)
        self.assertIn("下一页：/help --page 2", fallback)

    def test_file_payload_and_text_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.log"
            payload = build_file_segment_payload(path)
            self.assertTrue(payload["data"]["file"].startswith("file:///"))
        result = build_help_outbound(
            "# Help\n![image](local.png)",
            supports_markdown=False,
            supports_keyboard=False,
        )
        self.assertEqual(result["mode"], "text")
        self.assertNotIn("local.png", result["message"])
        degraded = build_help_outbound(
            "# Help",
            [
                [
                    {
                        "render_data": {"label": "下一页"},
                        "action": {"data": "/help --page 2"},
                    }
                ]
            ],
            supports_markdown=True,
            supports_keyboard=False,
        )
        self.assertTrue(degraded["degraded"])
        self.assertIn(
            "下一页：/help --page 2",
            degraded["message"]["markdown"]["content"],
        )

    def test_capability_menu_and_pagination(self) -> None:
        capabilities = collect_capabilities(Registry())
        self.assertEqual(
            capabilities,
            [{"provider": "synthetic-r010", "capabilities": ["alpha", "zeta"]}],
        )
        self.assertEqual(
            build_amiya_menu(capabilities)["plugins"][0]["id"],
            "synthetic-r010",
        )

        import nonebot

        nonebot.init()
        package_name = "amia_help_release010"
        import importlib.util

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
            gensokyo = sys.modules[package_name + ".gensokyo"]
            infos = [SimpleNamespace(name=f"插件 {i}") for i in range(1, 42)]
            rows, window = gensokyo.build_index_keyboard(infos, 1)
            buttons = [button for row in rows for button in row]
            self.assertEqual(window.total_pages, 4)
            self.assertEqual(buttons[0]["action"]["data"], "/help 1")
            self.assertEqual(buttons[-1]["action"]["data"], "/help --page 2")
            self.assertEqual(
                gensokyo.parse_page_request("--page 2"),
                gensokyo.PageRequest(None, 2),
            )
            info = SimpleNamespace(
                pm_data=[SimpleNamespace(func=f"功能 {i}") for i in range(1, 22)]
            )
            detail_rows, detail_window = gensokyo.build_detail_keyboard(info, 2, 1)
            detail_buttons = [button for row in detail_rows for button in row]
            self.assertEqual(detail_window.total_pages, 2)
            self.assertEqual(detail_buttons[0]["action"]["data"], "/help 3 1")
            self.assertIn(
                "/help 3 --page 2",
                [button["action"]["data"] for button in detail_buttons],
            )
        finally:
            for name in list(sys.modules):
                if name == package_name or name.startswith(package_name + "."):
                    sys.modules.pop(name, None)

    def test_prefix_has_no_embedded_account_or_group(self) -> None:
        prefix = render_prefix_text()
        self.assertNotIn("105 396 4431", prefix)
        self.assertIn("欢迎使用 Amia_晓山瑞希。", prefix)

    def test_upload_config_has_safe_bounds(self) -> None:
        config = MarkdownHelpConfig(button_page_size=12)
        self.assertEqual(config.button_page_size, 12)


if __name__ == "__main__":
    unittest.main()
