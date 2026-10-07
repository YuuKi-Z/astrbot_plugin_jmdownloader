import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from migrate import import_snapshot, snapshot_from_env  # noqa: E402
from service import JmService, build_option  # noqa: E402
from state import StateStore  # noqa: E402


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.snapshot = {
            "config": {
                "jmcomic_user_limits": 37,
                "jmcomic_username": "user",
                "jmcomic_password": 'a:#{}" & value',
            },
            "data": {
                "123": {
                    "enabled": True,
                    "blacklist": ["456"],
                    "folder_id": "folder",
                    "extra": {"unknown": 1},
                },
                "user_limits": {"456": 36},
                "restricted_tags": [],
                "restricted_ids": [],
                "future_field": ["retained"],
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_import_preserves_entire_json_and_credentials(self):
        result = import_snapshot(self.snapshot, self.root)
        self.assertEqual(
            json.loads(Path(result["data_file"]).read_text(encoding="utf-8")), self.snapshot["data"]
        )
        config = json.loads(Path(result["config_file"]).read_text(encoding="utf-8"))
        option = build_option(config, self.root / "cache")
        self.assertEqual(
            option["plugins"]["after_init"][0]["kwargs"]["password"],
            self.snapshot["config"]["jmcomic_password"],
        )
        self.assertEqual(StateStore(Path(result["data_file"]), config).remaining("456"), 36)
        self.assertEqual(StateStore(Path(result["data_file"]), config).remaining("789"), 37)

    def test_existing_destination_requires_explicit_overwrite_and_is_backed_up(self):
        result = import_snapshot(self.snapshot, self.root)
        original = Path(result["data_file"]).read_bytes()
        with self.assertRaises(FileExistsError):
            import_snapshot(self.snapshot, self.root)
        self.snapshot["data"]["user_limits"]["456"] = 12
        result = import_snapshot(self.snapshot, self.root, overwrite=True)
        self.assertEqual(
            (Path(result["previous_destination_backup"]) / "jmcomic_data.json").read_bytes(),
            original,
        )

    def test_bad_existing_json_is_never_reset(self):
        file = self.root / "jmcomic_data.json"
        file.write_text("incomplete{", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            StateStore(file, {})
        self.assertEqual(file.read_text(encoding="utf-8"), "incomplete{")

    def test_empty_restriction_lists_and_unknown_fields_survive_updates(self):
        file = self.root / "jmcomic_data.json"
        file.write_text(json.dumps(self.snapshot["data"]), encoding="utf-8")
        store = StateStore(file, {"jmcomic_user_limits": 37})
        self.assertFalse(store.blocked("136494", ["獵奇"]))
        self.assertTrue(store.consume("456"))
        store.reset_limits()
        reloaded = StateStore(file, {})
        self.assertEqual(reloaded.remaining("456"), 37)
        self.assertEqual(reloaded.data["future_field"], ["retained"])
        self.assertEqual(reloaded.group("123")["extra"], {"unknown": 1})

    def test_env_layers_comments_and_superusers(self):
        base, prod, data = self.root / ".env", self.root / ".env.prod", self.root / "source.json"
        base.write_text(
            'JMCOMIC_USER_LIMITS=37 # comment\nJMCOMIC_ALLOW_GROUPS=False\nSUPERUSERS=["123"]\nJMCOMIC_PASSWORD="a#b:c"\n',
            encoding="utf-8",
        )
        prod.write_text("JMCOMIC_RESULTS_PER_PAGE=10\n", encoding="utf-8")
        data.write_text(json.dumps(self.snapshot["data"]), encoding="utf-8")
        config = snapshot_from_env([base, prod], data)["config"]
        self.assertEqual(config["jmcomic_user_limits"], 37)
        self.assertFalse(config["jmcomic_allow_groups"])
        self.assertEqual(config["jmcomic_superusers"], ["123"])
        self.assertEqual(config["jmcomic_password"], "a#b:c")
        self.assertEqual(config["jmcomic_results_per_page"], 10)

    def test_constructs_original_jmcomic_options(self):
        from jmcomic import JmOption

        option = JmOption.construct(build_option({"jmcomic_thread_count": 10}, self.root / "cache"))
        self.assertEqual(option.download.threading.image, 10)
        self.assertEqual(option.client.impl, "api")


class FileTests(unittest.IsolatedAsyncioTestCase):
    async def test_md5_variant_stays_valid_and_original_unchanged(self):
        import hashlib
        import io

        import img2pdf
        import pikepdf
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = JmService({"jmcomic_modify_real_md5": True}, root / "cache")
            image = io.BytesIO()
            Image.new("RGB", (32, 32), "white").save(image, "JPEG")
            source = service.cache / "test.pdf"
            source.write_bytes(img2pdf.convert(image.getvalue()))
            original = source.read_bytes()
            first = await service.prepare_upload(source, root / "uploads")
            second = await service.prepare_upload(source, root / "uploads")
            self.assertEqual(source.read_bytes(), original)
            self.assertNotEqual(
                hashlib.md5(first.read_bytes()).digest(), hashlib.md5(second.read_bytes()).digest()
            )
            with pikepdf.open(first) as pdf:
                self.assertEqual(len(pdf.pages), 1)
            await service.clear_cache()
            self.assertTrue(first.is_file())
            self.assertFalse(source.exists())

    async def test_cancelled_worker_finishes_before_cleanup_can_enter(self):
        import asyncio
        import threading

        with tempfile.TemporaryDirectory() as directory:
            service = JmService({}, Path(directory) / "cache")
            started, finish = threading.Event(), threading.Event()

            def blocking():
                started.set()
                finish.wait(timeout=5)

            work = asyncio.create_task(service._worker(blocking))
            await asyncio.to_thread(started.wait, 2)
            work.cancel()
            await asyncio.sleep(0)
            self.assertTrue(service.lock.locked())
            cleanup = asyncio.create_task(service.clear_cache())
            await asyncio.sleep(0)
            self.assertFalse(cleanup.done())
            finish.set()
            with self.assertRaises(asyncio.CancelledError):
                await work
            await cleanup


class ApiCompatibilityTests(unittest.TestCase):
    @staticmethod
    def response(text, status=200, url="https://example.test/setting"):
        from types import SimpleNamespace

        return SimpleNamespace(
            text=text,
            status_code=status,
            content=text.encode(),
            request=SimpleNamespace(url=url),
            url=url,
        )

    def test_bom_response_rejected_upstream_is_accepted_and_parsed(self):
        from jmcomic import JmApiClient, JmApiResp

        from compat import CompatibleJmApiClient

        response = self.response('\ufeff{"code":200,"data":[]}')
        upstream = object.__new__(JmApiClient)
        with self.assertRaises(Exception):
            upstream.raise_if_resp_should_retry(response, False)
        compatible = object.__new__(CompatibleJmApiClient)
        normalised = compatible.raise_if_resp_should_retry(response, False)
        self.assertEqual(JmApiResp(normalised, "1").json(), {"code": 200, "data": []})
        self.assertEqual(response.text[0], "\ufeff")

    def test_http_errors_and_html_still_rejected_and_default_client_unchanged(self):
        from jmcomic import JmApiClient, JmModuleConfig

        from compat import CompatibleJmApiClient, register_compatible_client

        compatible = object.__new__(CompatibleJmApiClient)
        for response in [
            self.response('\ufeff{"code":200}', status=503),
            self.response("\ufeff<html>error</html>"),
        ]:
            with self.assertRaises(Exception):
                compatible.raise_if_resp_should_retry(response, False)
        register_compatible_client()
        self.assertIs(JmModuleConfig.REGISTRY_CLIENT["api"], JmApiClient)


if __name__ == "__main__":
    unittest.main()
