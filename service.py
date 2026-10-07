"""Blocking jmcomic calls run in a worker and share one lifecycle lock."""

import asyncio
import io
import shutil
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, ImageFilter


def build_option(config: dict, cache: Path) -> dict:
    plugins = {
        "after_photo": [
            {"plugin": "img2pdf", "kwargs": {"pdf_dir": str(cache), "filename_rule": "Pid"}}
        ],
    }
    if config.get("jmcomic_username") and config.get("jmcomic_password"):
        plugins["after_init"] = [
            {
                "plugin": "login",
                "kwargs": {
                    "username": config["jmcomic_username"],
                    "password": config["jmcomic_password"],
                },
            }
        ]
    return {
        "log": bool(config.get("jmcomic_log", False)),
        "client": {
            "impl": "api",
            "retry_times": 1,
            "postman": {"meta_data": {"proxies": config.get("jmcomic_proxies", "system")}},
        },
        "download": {
            "image": {"suffix": ".jpg"},
            "threading": {"image": int(config.get("jmcomic_thread_count", 10))},
        },
        "dir_rule": {"base_dir": str(cache), "rule": "Bd_Pid"},
        "plugins": plugins,
    }


class JmService:
    def __init__(self, config: dict, cache: Path):
        self.config = config
        self.cache = cache.resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()
        self.option = None
        self.client = None

    def _initialize(self):
        if self.client is None:
            from jmcomic import JmOption

            from .compat import register_compatible_client

            options = build_option(self.config, self.cache)
            options["client"]["impl"] = register_compatible_client()
            option = JmOption.construct(options)
            client = option.build_jm_client()
            self.option, self.client = option, client

    async def _worker(self, function, *args):
        async with self.lock:
            task = asyncio.create_task(asyncio.to_thread(function, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # A Python thread cannot be cancelled: finish before releasing
                # the lock, so cleanup/reload never deletes an active download.
                try:
                    await task
                finally:
                    raise

    def _photo(self, photo_id: str):
        self._initialize()
        return self.client.get_photo_detail(photo_id)

    async def photo(self, photo_id: str):
        return await self._worker(self._photo, photo_id)

    def _search(self, query: str, page: int):
        self._initialize()
        return [
            str(value) for value in self.client.search_site(search_query=query, page=page).iter_id()
        ]

    async def search(self, query: str, page: int = 1):
        return await self._worker(self._search, query, page)

    def _download(self, photo) -> Path:
        from jmcomic import JmDownloader

        self._initialize()
        pdf = self.cache / f"{photo.id}.pdf"
        if not pdf.is_file() or pdf.stat().st_size == 0:
            with JmDownloader(self.option) as downloader:
                downloader.download_by_photo_detail(photo)
        if not pdf.is_file() or pdf.stat().st_size == 0:
            raise RuntimeError("下载结束后未生成 PDF")
        return pdf

    async def download(self, photo) -> Path:
        return await self._worker(self._download, photo)

    def _download_for_upload(self, photo, destination: Path) -> Path:
        return self._prepare_upload(self._download(photo), destination)

    async def download_for_upload(self, photo, destination: Path) -> Path:
        return await self._worker(self._download_for_upload, photo, destination)

    def _prepare_upload(self, pdf: Path, destination: Path) -> Path:
        # The upload copy also lives outside cache and stays alive until the
        # protocol server completes the upload, even during nightly cleanup.
        destination.mkdir(parents=True, exist_ok=True)
        result = destination / f"{pdf.stem}_{uuid4().hex}.pdf"
        shutil.copyfile(pdf, result)
        if self.config.get("jmcomic_modify_real_md5", False):
            with result.open("ab") as stream:
                stream.write(f"\n% JM transfer {uuid4().hex}\n".encode("ascii"))
        return result

    async def prepare_upload(self, pdf: Path, destination: Path) -> Path:
        return await self._worker(self._prepare_upload, pdf, destination)

    def _clear_cache(self):
        # Only delete direct children of this plugin's own resolved cache.
        for child in self.cache.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        self.client, self.option = None, None

    async def clear_cache(self):
        await self._worker(self._clear_cache)

    async def cover(self, photo_id: str) -> bytes | None:
        from jmcomic import JmModuleConfig

        proxy = self.config.get("jmcomic_proxies", "system")
        options = {"timeout": 12, "follow_redirects": True, "trust_env": proxy == "system"}
        if proxy and proxy != "system":
            options["proxy"] = proxy
        async with httpx.AsyncClient(**options) as client:
            for domain in JmModuleConfig.DOMAIN_IMAGE_LIST:
                try:
                    response = await client.get(f"https://{domain}/media/albums/{photo_id}.jpg")
                    response.raise_for_status()
                    return await asyncio.to_thread(self._blur, response.content)
                except (httpx.HTTPError, OSError, ValueError):
                    continue
        return None

    @staticmethod
    def _blur(content: bytes) -> bytes:
        with Image.open(io.BytesIO(content)) as image:
            image = image.convert("RGB")
            image.thumbnail((600, 900))
            image = image.filter(ImageFilter.GaussianBlur(radius=7))
            result = io.BytesIO()
            image.save(result, "JPEG")
            return result.getvalue()
