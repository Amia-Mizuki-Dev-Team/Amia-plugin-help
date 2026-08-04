import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from compat import (
    build_file_segment_payload,
    build_help_outbound,
    build_markdown_keyboard_payload,
    normalize_message_segments,
    remove_bot_mentions,
    safe_local_media_path,
)
from config import render_prefix_text
from menu import build_amiya_menu, collect_capabilities


class CapabilityProvider:
    def get_supported_capabilities(self):
        return ["zeta", "alpha", "alpha"]


class Registry:
    def get_capability_providers(self):
        return {"synthetic-r010": CapabilityProvider()}


class Segment:
    type = "markdown"
    data = {"content": "# Help"}


class Release010HelpTests(unittest.TestCase):
    def test_string_array_and_extended_cq_segments(self):
        self.assertEqual(
            normalize_message_segments("help"),
            [{"type": "text", "data": {"text": "help"}}],
        )
        self.assertEqual(
            normalize_message_segments(
                ["help", {"type": "at", "data": {"qq": "bot-r010"}}]
            ),
            [
                {"type": "text", "data": {"text": "help"}},
                {"type": "at", "data": {"qq": "bot-r010"}},
            ],
        )
        segments = normalize_message_segments(
            "[CQ:card,type=xml]x[CQ:input_notify,body=ok][CQ:stream,id=s1]"
        )
        self.assertEqual([item["type"] for item in segments], ["card", "text", "input_notify", "stream"])
        self.assertEqual(segments[0]["data"]["type"], "xml")
        self.assertEqual(remove_bot_mentions(segments, "bot-r010"), segments)
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

    def test_markdown_keyboard_and_local_image_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_markdown_keyboard_payload(
                "# Help",
                [[{"label": "Economy", "local_image": "icons/economy.png"}]],
                media_root=root,
            )
            button = payload["keyboard"]["content"]["rows"][0]["buttons"][0]
            self.assertTrue(button["local_image"].endswith("economy.png"))
            with self.assertRaises(ValueError):
                safe_local_media_path(root, "../outside.png")

    def test_gensokyo_file_payload_uses_file_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.log"
            payload = build_file_segment_payload(path)
            self.assertEqual(payload["type"], "file")
            self.assertTrue(payload["data"]["file"].startswith("file:///"))

    def test_markdown_degrades_to_text_without_capability(self):
        result = build_help_outbound(
            "# Help\n![image](local.png)",
            supports_markdown=False,
            supports_keyboard=False,
        )
        self.assertEqual(result["mode"], "text")
        self.assertTrue(result["degraded"])
        self.assertNotIn("local.png", result["message"])

    def test_capability_menu_is_stable_and_external(self):
        capabilities = collect_capabilities(Registry())
        self.assertEqual(
            capabilities,
            [{"provider": "synthetic-r010", "capabilities": ["alpha", "zeta"]}],
        )
        self.assertEqual(
            build_amiya_menu(capabilities)["plugins"][0]["id"], "synthetic-r010"
        )

    def test_prefix_has_no_embedded_account_or_group(self):
        self.assertNotIn("105 396 4431", render_prefix_text())

    def test_plugin_import_and_matcher_registration(self):
        import nonebot

        nonebot.init()
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "amia_help_release010",
            root / "__init__.py",
            submodule_search_locations=[str(root)],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.mizuki_text_help.priority, 1)
        self.assertFalse(module.mizuki_text_help.block)
        self.assertIsNotNone(module.ensure_picmenu_loaded())
        self.assertEqual(module.PICMENU_COMMIT, "a0f8f729927c947e315f5719cfd1cd2720b2ee0c")


if __name__ == "__main__":
    unittest.main()
