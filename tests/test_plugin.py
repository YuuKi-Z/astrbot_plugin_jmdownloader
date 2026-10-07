"""Exercise the real handlers with fake protocol calls; sends no QQ messages.

On an AstrBot host, the real API classes/decorators are used. Elsewhere, small
stubs let us verify the port's business rules without installing AstrBot itself.
"""

import asyncio
import importlib
import importlib.util
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    if importlib.util.find_spec("astrbot") is None:

        class Component:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.__dict__.update(kwargs)

        class Image(Component):
            @staticmethod
            def fromBytes(content):
                return Image(content)

        class Star:
            def __init__(self, context):
                self.context = context

        def decorator(*args, **kwargs):
            return lambda function: function

        definitions = {
            "astrbot": {},
            "astrbot.api": {"AstrBotConfig": dict, "logger": logging.getLogger("test")},
            "astrbot.api.event": {
                "AstrMessageEvent": object,
                "MessageChain": Component,
                "filter": types.SimpleNamespace(
                    regex=decorator,
                    platform_adapter_type=decorator,
                    PlatformAdapterType=types.SimpleNamespace(AIOCQHTTP="aiocqhttp"),
                ),
            },
            "astrbot.api.message_components": {
                "At": Component,
                "Image": Image,
                "Node": Component,
                "Nodes": Component,
                "Plain": Component,
            },
            "astrbot.api.star": {
                "Context": object,
                "Star": Star,
                "StarTools": types.SimpleNamespace(get_data_dir=lambda name: ROOT / "unused"),
                "register": decorator,
            },
        }
        for name, values in definitions.items():
            module = types.ModuleType(name)
            module.__dict__.update(values)
            sys.modules[name] = module
    package = types.ModuleType("jm_port_test")
    package.__path__ = [str(ROOT)]
    sys.modules[package.__name__] = package
    return importlib.import_module("jm_port_test.main")


plugin_module = load_plugin()


class FakeBot:
    def __init__(self):
        self.calls = []
        self.roles = {}
        self.fail_upload = False

    async def call_action(self, action, **kwargs):
        self.calls.append((action, kwargs))
        if action == "get_group_member_info":
            return {"role": self.roles.get(str(kwargs["user_id"]), "member")}
        if action == "get_group_root_files":
            return {"folders": [{"folder_name": "documents", "folder_id": "folder"}]}
        if action == "create_group_file_folder":
            return {"groupItem": {"folderInfo": {"folderId": "new-folder"}}}
        if action.startswith("upload_") and self.fail_upload:
            raise RuntimeError("simulated upload failure")
        return {}


class FakeEvent:
    def __init__(self, message, bot, group="123", user="456", admin=False):
        self.message = message
        self.bot = bot
        self.group, self.user, self.admin = group, user, admin
        self.unified_msg_origin = f"test:{group or user}"
        self.sent = []
        self.stopped = False

    def get_message_str(self):
        return self.message

    def get_sender_id(self):
        return self.user

    def get_group_id(self):
        return self.group

    def get_self_id(self):
        return "999"

    def get_messages(self):
        return []

    def is_admin(self):
        return self.admin

    def stop_event(self):
        self.stopped = True

    def plain_result(self, text):
        return text

    async def send(self, message):
        self.sent.append(message)


class FakeService:
    def __init__(self):
        self.calls = []
        self.lock = asyncio.Lock()

    async def photo(self, photo_id):
        self.calls.append(("photo", photo_id))
        return types.SimpleNamespace(
            id=photo_id, title="test document", author="test", tags=["test"]
        )

    async def download_for_upload(self, photo, destination):
        self.calls.append(("download", photo.id))
        destination.mkdir(parents=True, exist_ok=True)
        pdf = destination / f"{photo.id}_test.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return pdf

    async def cover(self, photo_id):
        return None

    async def search(self, query, page=1):
        self.calls.append(("search", query, page))
        return [str(800000 + number) for number in range(15)]


class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = {
            "jmcomic_user_limits": 5,
            "jmcomic_allow_groups": False,
            "jmcomic_superusers": ["100"],
            "jmcomic_results_per_page": 10,
        }
        # Match the real AstrBot path layout: data/plugin_data/plugin_name.
        directory = self.root / "data" / "plugin_data" / "astrbot_plugin_jmdownloader"
        with patch.object(plugin_module.StarTools, "get_data_dir", return_value=directory):
            self.plugin = plugin_module.JmDownloaderPlugin(types.SimpleNamespace(), self.config)
        self.plugin.store.set_group("123", "enabled", True)
        self.plugin.service = FakeService()
        self.bot = FakeBot()

    async def asyncTearDown(self):
        await self.plugin.terminate()
        self.temporary.cleanup()

    async def run_command(self, message, **kwargs):
        event = FakeEvent(message, self.bot, **kwargs)
        await self.plugin.jm_command(event)
        return event

    async def test_download_keeps_folder_uses_shared_path_and_cleans_upload(self):
        self.plugin.store.set_group("123", "folder_id", "preserved-folder")
        event = await self.run_command("JM下载 12345")
        action, params = self.bot.calls[-1]
        self.assertEqual(action, "upload_group_file")
        self.assertEqual(params["folder_id"], "preserved-folder")
        self.assertEqual(params["name"], "12345.pdf")
        self.assertEqual(self.plugin.store.remaining("456"), 4)
        self.assertFalse(Path(params["file"]).exists())
        self.assertTrue(event.stopped)

    async def test_upload_failure_refunds_quota(self):
        self.bot.fail_upload = True
        event = await self.run_command("jm下载12345")
        self.assertEqual(self.plugin.store.remaining("456"), 5)
        self.assertIn("操作失败", event.sent[-1])
        self.assertFalse(list((self.plugin.data_dir / "uploads").glob("*.pdf")))

    async def test_disabled_and_blacklisted_groups_do_not_request_network(self):
        event = await self.run_command("jm查询 12345", group="222")
        self.assertFalse(event.stopped)
        self.plugin.store.set_blacklisted("123", "456", True)
        await self.run_command("jm下载 12345")
        self.assertEqual(self.plugin.service.calls, [])

    async def test_zero_quota_and_superuser_exemption(self):
        self.plugin.store.data["user_limits"] = {"456": 0, "100": 0}
        await self.run_command("jm下载 12345")
        self.assertEqual(self.plugin.service.calls, [])
        await self.run_command("jm下载 12345", user="100")
        self.assertEqual(self.plugin.store.remaining("100"), 0)
        self.assertEqual(self.bot.calls[-1][0], "upload_group_file")

    async def test_concurrent_downloads_cannot_overspend(self):
        self.plugin.store.data["user_limits"] = {"456": 1}
        await asyncio.gather(self.run_command("jm下载 12345"), self.run_command("jm下载 12346"))
        self.assertEqual(sum(action == "upload_group_file" for action, _ in self.bot.calls), 1)
        self.assertEqual(self.plugin.store.remaining("456"), 0)

    async def test_blocked_id_preserves_original_punishment_and_no_charge(self):
        await self.run_command("jm下载 136494")
        self.assertTrue(self.plugin.store.blacklisted("123", "456"))
        self.assertEqual(self.plugin.store.remaining("456"), 5)
        self.assertEqual(self.bot.calls[-1][0], "set_group_ban")
        self.assertEqual(self.plugin.service.calls, [])

    async def test_private_file_api_and_path_mapping(self):
        self.config["onebot_file_base"] = "/shared/data"
        await self.run_command("/jm下载 12345", group="")
        action, params = self.bot.calls[-1]
        self.assertEqual(action, "upload_private_file")
        self.assertEqual(params["user_id"], 456)
        self.assertTrue(
            params["file"].startswith(
                "/shared/data/plugin_data/astrbot_plugin_jmdownloader/uploads/"
            )
        )

    async def test_group_admin_cannot_blacklist_other_admin(self):
        self.bot.roles = {"456": "admin", "789": "owner"}
        await self.run_command("jm拉黑 789")
        self.assertFalse(self.plugin.store.blacklisted("123", "789"))
        self.bot.roles["789"] = "member"
        await self.run_command("jm拉黑 789")
        self.assertTrue(self.plugin.store.blacklisted("123", "789"))

    async def test_close_confirmation_is_scoped_to_requesting_user(self):
        self.bot.roles["456"] = "admin"
        await self.run_command("关闭JM")
        other = FakeEvent("确认", self.bot, user="789")
        await self.plugin.confirm_close(other)
        self.assertFalse(other.stopped)
        self.assertTrue(self.plugin.store.group_enabled("123"))
        event = FakeEvent("确认", self.bot)
        await self.plugin.confirm_close(event)
        self.assertFalse(self.plugin.store.group_enabled("123"))

    async def test_only_superuser_can_enable_groups_and_original_superuser_works(self):
        await self.run_command("jm启用群 222")
        self.assertFalse(self.plugin.store.group_enabled("222"))
        await self.run_command("jm启用群 222 333", user="100")
        self.assertTrue(self.plugin.store.group_enabled("222"))
        self.assertTrue(self.plugin.store.group_enabled("333"))

    async def test_search_paging_and_session_isolation(self):
        await self.run_command("jm搜索 test")
        other = await self.run_command("jm 下一页", group="", user="456")
        self.assertIn("没有进行中的搜索", other.sent[-1])
        second = await self.run_command("JM 下一页")
        self.assertIn("已发送所有搜索结果", second.sent[-1])
        self.assertFalse(self.plugin.searches)

    async def test_folder_lookup_and_creation(self):
        self.bot.roles["456"] = "owner"
        await self.run_command("jm设置文件夹 documents")
        self.assertEqual(self.plugin.store.group("123")["folder_id"], "folder")
        await self.run_command("jm设置文件夹 new documents")
        self.assertEqual(self.plugin.store.group("123")["folder_id"], "new-folder")

    def test_command_boundaries(self):
        for text in [
            "jm下载 12345",
            "JM查询12345",
            "/jm搜索 word word",
            "jm 下一页",
            "关闭jm 确认",
        ]:
            self.assertIsNotNone(plugin_module.COMMAND_PATTERN.fullmatch(text))
        for text in ["jm下载abcdef", "请问 jm下载 12345", "jm搜索关键字"]:
            self.assertIsNone(plugin_module.COMMAND_PATTERN.fullmatch(text))


if __name__ == "__main__":
    unittest.main()
