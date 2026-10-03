import importlib.util
import json
import sys
import tempfile
from dataclasses import replace
from types import SimpleNamespace
import unittest
from pathlib import Path

from nonebot.adapters.onebot.v11 import Message, MessageSegment

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
from config import MarkdownHelpConfig, render_prefix_text
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

            # The OneBot V11 segment must retain Release015's nested data.data
            # object after serialization, not only in the intermediate payload.
            segment = MessageSegment("markdown", {"data": payload})
            serialized = [{"type": item.type, "data": item.data} for item in Message([segment])]
            self.assertEqual(serialized[0]["data"]["data"]["markdown"]["content"], "# Help")
            json.dumps(serialized, ensure_ascii=False)

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
        prefix = render_prefix_text()
        self.assertNotIn("105 396 4431", prefix)
        self.assertIn("欢迎使用 Amia_晓山瑞希。", prefix)
        self.assertNotIn("帮助菜单由", prefix)

    def test_picmenu_footer_override_is_explicit(self):
        css = (PLUGIN_ROOT / "picmenu_footer.css").read_text(encoding="utf-8")
        self.assertIn('content: "Powered By HX-Wrdzgzs";', css)
        self.assertNotIn("LgCuwukii", css)

    def test_plugin_import_and_matcher_registration(self):
        import nonebot

        nonebot.init()
        # PicMenu requires the parent Alconna plugin.  Loading it explicitly
        # mirrors the normal project plugin-directory startup in this isolated
        # module-import test.
        nonebot.load_plugin("nonebot_plugin_alconna")
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
        self.assertEqual(module.mizuki_text_help.priority, 0)
        self.assertFalse(module.mizuki_text_help.block)
        self.assertIsNotNone(module.ensure_picmenu_loaded())
        self.assertEqual(module.PICMENU_COMMIT, "a0f8f729927c947e315f5719cfd1cd2720b2ee0c")

        gensokyo = sys.modules[f"{spec.name}.gensokyo"]
        self.__class__.gensokyo = gensokyo

        for count in (0, 1, 5, 6, 20, 21, 40, 41):
            infos_for_count = [
                SimpleNamespace(name=f"插件 {index}") for index in range(1, count + 1)
            ]
            rows_for_count, count_window = gensokyo.build_index_keyboard(
                infos_for_count, 1
            )
            count_buttons = [button for row in rows_for_count for button in row]
            entry_buttons = [
                button
                for button in count_buttons
                if button["id"].startswith("plugin-")
            ]
            expected_entries = min(12, count)
            self.assertEqual(len(entry_buttons), expected_entries)
            self.assertLessEqual(len(rows_for_count), 5)
            self.assertTrue(all(len(row) <= 3 for row in rows_for_count))
            if count <= 12:
                self.assertEqual(count_window.total_pages, 1)
                self.assertFalse(any(button["id"].startswith("nav-") for button in count_buttons))
            else:
                self.assertEqual(count_window.total_pages, (count + 11) // 12)
                self.assertTrue(any(button["id"] == "nav-next-1" for button in count_buttons))

        infos = [SimpleNamespace(name=f"插件 {index}") for index in range(1, 42)]
        rows, window = gensokyo.build_index_keyboard(infos, 1)
        buttons = [button for row in rows for button in row]
        self.assertEqual(window.total_pages, 4)
        self.assertEqual(len(buttons), 13)  # 12 entries + 下一页
        self.assertEqual(buttons[0]["action"]["data"], "/help 1")
        self.assertEqual(buttons[-1]["action"]["data"], "/help --page 2")
        self.assertLessEqual(len(rows), 5)
        self.assertTrue(all(len(row) <= 3 for row in rows))

        last_rows, last_window = gensokyo.build_index_keyboard(infos, 4)
        last_buttons = [button for row in last_rows for button in row]
        self.assertEqual(last_window.start, 36)
        self.assertEqual(last_buttons[0]["action"]["data"], "/help 37")
        self.assertEqual(last_buttons[-1]["action"]["data"], "/help --page 1")

        info = SimpleNamespace(
            pm_data=[SimpleNamespace(func=f"功能 {index}") for index in range(1, 22)]
        )
        detail_rows, detail_window = gensokyo.build_detail_keyboard(info, 2, 1)
        detail_buttons = [button for row in detail_rows for button in row]
        self.assertEqual(detail_window.total_pages, 2)
        self.assertEqual(detail_buttons[0]["action"]["data"], "/help 3 1")
        self.assertEqual(detail_buttons[-1]["action"]["data"], "/help 3 --page 2")
        self.assertTrue(all(len(row) <= 3 for row in detail_rows))

        last_detail_rows, _ = gensokyo.build_detail_keyboard(info, 2, 2)
        last_detail_buttons = [button for row in last_detail_rows for button in row]
        self.assertIn(
            "/help 3 --page 1",
            [button["action"]["data"] for button in last_detail_buttons],
        )

        self.assertEqual(
            gensokyo.parse_page_request("--page 2"),
            gensokyo.PageRequest(None, 2),
        )
        self.assertEqual(
            gensokyo.parse_page_request("3 --page 2"),
            gensokyo.PageRequest("3", 2),
        )
        self.assertIsNone(gensokyo.parse_page_request("economy"))
        self.assertEqual(gensokyo._short_label("Amia Core"), "Core")
        self.assertEqual(gensokyo._short_label("Mizuki 文字帮助"), "文字帮助")
        page_text = gensokyo._page_text(
            "帮助菜单",
            gensokyo.PageWindow(page=1, total_pages=2, start=0, end=20, valid=True),
            22,
        )
        self.assertIn(
            "官方网站：[help.mizuki.top](https://help.mizuki.top)",
            page_text,
        )

    def test_z_upload_cache_and_failure_boundaries(self):
        """Exercise the bounded uploader without contacting a real Gensokyo host."""

        gensokyo = getattr(self.__class__, "gensokyo", None)
        self.assertIsNotNone(gensokyo, "plugin import test must load the adapter module")

        import asyncio
        import base64
        import httpx

        raw = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        config = MarkdownHelpConfig(
            upload_url="http://upload.test/upload",
            access_token="test-token",
            image_cache_ttl_seconds=3600,
            image_cache_max_entries=64,
        )

        class FakeResponse:
            def __init__(self, status_code=200, payload=None):
                self.status_code = status_code
                self._payload = payload or {
                    "url": "https://cdn.example.test/help.png",
                    "width": 1,
                    "height": 1,
                }

            def json(self):
                if isinstance(self._payload, BaseException):
                    raise self._payload
                return self._payload

        class FakeClient:
            calls = []
            status_code = 200
            payload = None
            error = None

            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def post(self, url, data, headers):
                type(self).calls.append(
                    {"url": url, "data": data, "headers": headers}
                )
                if type(self).error is not None:
                    raise type(self).error
                return FakeResponse(type(self).status_code, type(self).payload)

        async def exercise():
            original_client = gensokyo.httpx.AsyncClient
            gensokyo.httpx.AsyncClient = FakeClient
            gensokyo._UPLOAD_CACHE.clear()
            gensokyo._UPLOAD_LOCK = None
            try:
                first = await gensokyo.upload_image(raw, config)
                second = await gensokyo.upload_image(raw, config)
                self.assertEqual(first, second)
                self.assertEqual(len(FakeClient.calls), 1)
                self.assertEqual(
                    FakeClient.calls[0]["headers"]["Authorization"],
                    f"Bearer {config.access_token}",
                )

                expired_config = replace(config, image_cache_ttl_seconds=0)
                await gensokyo.upload_image(raw, expired_config)
                await gensokyo.upload_image(raw, expired_config)
                self.assertEqual(len(FakeClient.calls), 3)

                concurrent_config = replace(
                    config, upload_url="http://upload.test/concurrent"
                )
                concurrent_results = await asyncio.gather(
                    *[
                        gensokyo.upload_image(raw, concurrent_config)
                        for _ in range(4)
                    ]
                )
                self.assertTrue(all(result is not None for result in concurrent_results))
                self.assertEqual(
                    len(
                        [
                            call
                            for call in FakeClient.calls
                            if call["url"] == concurrent_config.upload_url
                        ]
                    ),
                    1,
                )

                FakeClient.status_code = 401
                self.assertIsNone(
                    await gensokyo.upload_image(
                        raw, replace(config, upload_url="http://upload.test/401")
                    )
                )

                FakeClient.status_code = 200
                FakeClient.payload = {
                    "url": "file:///private/help.png",
                    "width": 1,
                    "height": 1,
                }
                self.assertIsNone(
                    await gensokyo.upload_image(
                        raw, replace(config, upload_url="http://upload.test/invalid-url")
                    )
                )

                FakeClient.payload = {
                    "url": "https://cdn.example.test/help.png",
                    "width": 0,
                    "height": 1,
                }
                self.assertIsNone(
                    await gensokyo.upload_image(
                        raw, replace(config, upload_url="http://upload.test/invalid-size")
                    )
                )

                FakeClient.error = httpx.ReadTimeout("timeout")
                self.assertIsNone(
                    await gensokyo.upload_image(
                        raw, replace(config, upload_url="http://upload.test/timeout")
                    )
                )

                self.assertIsNone(
                    await gensokyo.upload_image(
                        b"x" * (gensokyo.MAX_IMAGE_BYTES + 1), config
                    )
                )
            finally:
                gensokyo.httpx.AsyncClient = original_client
                gensokyo._UPLOAD_CACHE.clear()
                gensokyo._UPLOAD_LOCK = None

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
