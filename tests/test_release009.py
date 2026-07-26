import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from compat import (
    build_help_outbound,
    build_markdown_keyboard_payload,
    normalize_message_segments,
    safe_local_media_path,
)
from config import render_prefix_text
from menu import build_amiya_menu, collect_capabilities


class CapabilityProvider:
    def get_supported_capabilities(self):
        return ["zeta", "alpha", "alpha"]


class Registry:
    def get_capability_providers(self):
        return {"synthetic-r009": CapabilityProvider()}


class Segment:
    type = "markdown"
    data = {"content": "# Help"}


class Release009HelpTests(unittest.TestCase):
    def test_string_and_array_messages_are_normalized(self):
        self.assertEqual(
            normalize_message_segments("help"),
            [{"type": "text", "data": {"text": "help"}}],
        )
        self.assertEqual(
            normalize_message_segments(
                ["help", {"type": "at", "data": {"qq": "bot-r009"}}]
            ),
            [
                {"type": "text", "data": {"text": "help"}},
                {"type": "at", "data": {"qq": "bot-r009"}},
            ],
        )
        self.assertEqual(
            normalize_message_segments(Segment()),
            [{"type": "markdown", "data": {"content": "# Help"}}],
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
            [{"provider": "synthetic-r009", "capabilities": ["alpha", "zeta"]}],
        )
        self.assertEqual(
            build_amiya_menu(capabilities)["plugins"][0]["id"], "synthetic-r009"
        )

    def test_prefix_has_no_embedded_account_or_group(self):
        self.assertNotIn("105 396 4431", render_prefix_text())

    def test_plugin_import_and_matcher_registration(self):
        import nonebot

        nonebot.init()
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "amia_help_release009",
            root / "__init__.py",
            submodule_search_locations=[str(root)],
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.mizuki_text_help.priority, 1)
        self.assertFalse(module.mizuki_text_help.block)
        self.assertEqual(module.PICMENU_COMMIT, "241c4c34889ecaba08de07296d63981e5c7e100b")


if __name__ == "__main__":
    unittest.main()
