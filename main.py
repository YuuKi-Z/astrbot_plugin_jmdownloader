"""AstrBot / OneBot v11 handlers for the installed NoneBot 1.0.4 feature set."""

import asyncio
import re
import time
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Image, Node, Nodes, Plain
from astrbot.api.star import Context, Star, StarTools, register

from .service import JmService
from .state import StateStore, atomic_json

COMMAND_PATTERN = re.compile(
    r"(?i)^/?(?:(jm\s*(?:解除拉黑|设置文件夹|启用群|禁用群|下一页|禁用tag|禁用id|黑名单|下载|查询|搜索|拉黑|帮助|次数))|(开启jm|关闭jm))(?=\s|\d|$)(.*)$"
)
PUBLIC = {"jm下载", "jm查询", "jm搜索", "jm下一页", "jm次数"}
GLOBAL_ADMIN = {"jm启用群", "jm禁用群", "开启jm", "jm禁用id", "jm禁用tag"}
HELP = """JM 下载器
jm下载 <jm号> / jm查询 <jm号>
jm搜索 <关键词> / jm下一页 / jm次数
jm设置文件夹 <名称> / jm拉黑 @成员 / jm解除拉黑 @成员 / jm黑名单
开启jm / 关闭jm（发送“确认”或使用“关闭jm 确认”）
超级用户：jm启用群 <群号...> / jm禁用群 <群号...>
超级用户：jm禁用id <jm号...> / jm禁用tag <标签...>
命令支持 JM 大写、jm 下一页和 / 前缀。"""


@register(
    "astrbot_plugin_jmdownloader",
    "YuuKi-Z",
    "JM 下载器，保留 NoneBot2 配置与数据",
    "1.0.0",
)
class JmDownloaderPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_jmdownloader")
        self.store = StateStore(self.data_dir / "jmcomic_data.json", config)
        self.service = JmService(config, self.data_dir / "cache")
        self.searches = {}
        self.confirmations = {}
        self.download_lock = asyncio.Lock()
        self.search_lock = asyncio.Lock()
        self.maintenance_task = None
        self.stopping = False
        self.active_handlers = set()

    async def initialize(self):
        self.maintenance_task = asyncio.create_task(self._maintenance())
        logger.info("JM 下载器已加载；沿用 NoneBot2 数据结构，登录在首次请求时执行")

    async def terminate(self):
        self.stopping = True
        if self.maintenance_task:
            self.maintenance_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.maintenance_task
        # An in-flight handler includes the upload; keep its temporary copy
        # alive and let it finish before the plugin is replaced.
        current = asyncio.current_task()
        pending = [task for task in self.active_handlers if task is not current]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        async with self.service.lock:
            pass

    def _superuser(self, event: AstrMessageEvent) -> bool:
        return event.is_admin() or event.get_sender_id() in {
            str(uid) for uid in self.config.get("jmcomic_superusers", [])
        }

    @staticmethod
    def _session(event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:{event.get_sender_id()}"

    async def _say(self, event, text: str):
        await event.send(event.plain_result(text))

    async def _group_admin(self, event, target: str | None = None) -> bool:
        if self._superuser(event):
            return True
        if not event.get_group_id():
            return False
        operator = await event.bot.call_action(
            "get_group_member_info",
            group_id=int(event.get_group_id()),
            user_id=int(event.get_sender_id()),
        )
        role = operator.get("role", "member")
        if role == "owner":
            return True
        if role != "admin":
            return False
        if target is None:
            return True
        member = await event.bot.call_action(
            "get_group_member_info", group_id=int(event.get_group_id()), user_id=int(target)
        )
        return member.get("role", "member") not in {"admin", "owner"}

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.regex(COMMAND_PATTERN)
    async def jm_command(self, event: AstrMessageEvent):
        match = COMMAND_PATTERN.fullmatch(event.get_message_str().strip())
        if not match or self.stopping:
            return
        command = re.sub(r"\s+", "", match.group(1) or match.group(2)).lower()
        argument = match.group(3).strip()
        group, user = event.get_group_id(), event.get_sender_id()
        if command in PUBLIC and group:
            if not self.store.group_enabled(group) or self.store.blacklisted(group, user):
                return
        event.stop_event()
        task = asyncio.current_task()
        self.active_handlers.add(task)
        try:
            if command == "jm帮助":
                await self._say(event, HELP)
            elif command in {"jm下载", "jm查询"}:
                photo_id = argument.removeprefix("jm").removeprefix("JM")
                if not re.fullmatch(r"[0-9]+", photo_id):
                    await self._say(event, "请输入要下载或查询的 jm 号，例如 jm下载 123456")
                    return
                if command == "jm下载":
                    async with self.download_lock:
                        await self._download(event, photo_id)
                else:
                    photo = await self.service.photo(photo_id)
                    await self._send_photos(event, [photo])
            elif command == "jm次数":
                await self._say(
                    event,
                    "超级用户不受次数限制"
                    if self._superuser(event)
                    else f"你本周还有 {self.store.remaining(user)} 次下载次数",
                )
            elif command in {"jm搜索", "jm下一页"}:
                async with self.search_lock:
                    await self._search(event, argument, command == "jm下一页")
            else:
                await self._manage(event, command, argument)
        except Exception as exc:
            # JM errors may contain login POST bodies. Log the exception type
            # only; never print credentials or raw HTTP responses.
            logger.error("JM 请求失败 (%s)", type(exc).__name__)
            message = (
                "未查找到本子"
                if type(exc).__name__ == "MissingAlbumPhotoException"
                else "操作失败，请检查 JM 网络、登录配置或协议端文件上传设置"
            )
            await self._say(event, message)
        finally:
            self.active_handlers.discard(task)

    async def _download(self, event, photo_id: str):
        user, group = event.get_sender_id(), event.get_group_id()
        superuser = self._superuser(event)
        if not superuser and self.store.remaining(user) <= 0:
            await self._say(event, "你的下载次数已经用完了！")
            return
        if self.store.blocked(photo_id):
            await self._blocked(event)
            return
        photo = await self.service.photo(photo_id)
        if self.store.blocked(str(photo.id), photo.tags):
            await self._blocked(event)
            return
        charged = False
        upload_path = None
        try:
            if not superuser:
                charged = self.store.consume(user)
                if not charged:
                    await self._say(event, "你的下载次数已经用完了！")
                    return
            remaining = "" if superuser else f"\n你本周还有 {self.store.remaining(user)} 次下载次数"
            await self._say(event, self._description(photo) + "\n开始下载..." + remaining)
            upload_path = await self.service.download_for_upload(photo, self.data_dir / "uploads")
            protocol_file = str(upload_path)
            local_prefix = str(self.data_dir.parent.parent.resolve())
            protocol_prefix = str(self.config.get("onebot_file_base", "")).rstrip("/")
            if protocol_prefix:
                relative = upload_path.relative_to(local_prefix)
                protocol_file = protocol_prefix + "/" + relative.as_posix()
            if group:
                params = {"group_id": int(group), "file": protocol_file, "name": f"{photo.id}.pdf"}
                folder = self.store.group(group).get("folder_id")
                if folder:
                    params["folder_id"] = folder
                await event.bot.call_action("upload_group_file", **params)
            else:
                await event.bot.call_action(
                    "upload_private_file",
                    user_id=int(user),
                    file=protocol_file,
                    name=f"{photo.id}.pdf",
                )
        except BaseException:
            # Failed network/download/upload attempts do not consume quota.
            if charged:
                self.store.refund(user)
            raise
        finally:
            if upload_path:
                upload_path.unlink(missing_ok=True)

    async def _blocked(self, event):
        message = "该本子（或其 tag）被禁止下载！"
        if event.get_group_id() and not self._superuser(event):
            self.store.set_blacklisted(event.get_group_id(), event.get_sender_id(), True)
            with suppress(Exception):
                await event.bot.call_action(
                    "set_group_ban",
                    group_id=int(event.get_group_id()),
                    user_id=int(event.get_sender_id()),
                    duration=86400,
                )
            message += "你已被加入本群 jm 黑名单"
        await self._say(event, message)

    @staticmethod
    def _description(photo):
        return f"jm{photo.id} | {photo.title}\n🎨 作者: {photo.author}\n🔖 标签: " + " ".join(
            f"#{tag}" for tag in photo.tags
        )

    async def _send_photos(self, event, photos):
        nodes = []
        for photo in photos:
            if self.store.blocked(str(photo.id), photo.tags):
                content = [
                    Plain(self.config.get("jmcomic_blocked_message", "猫猫吃掉了一个不豪吃的本子"))
                ]
            else:
                content = [Plain(self._description(photo))]
                cover = await self.service.cover(str(photo.id))
                if cover:
                    content.append(Image.fromBytes(cover))
            nodes.append(Node(content=content, name="jm查询结果", uin=str(event.get_self_id())))
        if nodes:
            await event.send(MessageChain([Nodes(nodes)]))
        else:
            await self._say(event, "未搜索到本子")

    async def _search(self, event, query: str, next_page: bool):
        key = self._session(event)
        state = self.searches.get(key)
        if next_page:
            if not state or time.monotonic() - state["created"] > 1800:
                self.searches.pop(key, None)
                await self._say(event, "没有进行中的搜索，请先使用 jm搜索")
                return
        else:
            if not query:
                await self._say(event, "请输入要搜索的内容")
                return
            await self._say(event, "正在搜索中...")
            ids = await self.service.search(query)
            state = {
                "query": query,
                "ids": ids,
                "index": 0,
                "page": 1,
                "more": len(ids) == 80,
                "created": time.monotonic(),
            }
            self.searches[key] = state
        count = max(1, min(80, int(self.config.get("jmcomic_results_per_page", 20))))
        end = state["index"] + count
        while end > len(state["ids"]) and state["more"]:
            state["page"] += 1
            ids = await self.service.search(state["query"], state["page"])
            new_ids = [value for value in ids if value not in state["ids"]]
            state["ids"].extend(new_ids)
            state["more"] = len(ids) == 80 and bool(new_ids)
        selected = state["ids"][state["index"] : end]
        photos = []
        for photo_id in selected:
            try:
                photos.append(await self.service.photo(photo_id))
            except Exception as exc:
                logger.warning("JM 搜索条目无法读取 (%s)", type(exc).__name__)
        await self._send_photos(event, photos)
        state["index"] = end
        if end < len(state["ids"]) or state["more"]:
            await self._say(event, "搜索有更多结果，使用 jm下一页 查看更多")
        else:
            self.searches.pop(key, None)
            await self._say(event, "已发送所有搜索结果")

    async def _manage(self, event, command: str, argument: str):
        group = event.get_group_id()
        if command in GLOBAL_ADMIN and not self._superuser(event):
            await self._say(event, "权限不足，需要超级用户权限")
            return
        if command in {"jm启用群", "jm禁用群"}:
            ids = [value for value in argument.split() if re.fullmatch(r"[0-9]+", value)]
            for group_id in ids:
                self.store.set_group(group_id, "enabled", command == "jm启用群")
            await self._say(
                event,
                ("已处理以下群：" + " ".join(ids)) if ids else "请输入群号，多个群号以空格分隔",
            )
            return
        if command in {"jm禁用id", "jm禁用tag"}:
            values = argument.split()
            if command == "jm禁用id":
                values = [value for value in values if re.fullmatch(r"[0-9]+", value)]
            if values:
                self.store.add_restrictions(
                    "restricted_ids" if command == "jm禁用id" else "restricted_tags", values
                )
            await self._say(
                event,
                "已加入禁止列表：" + " ".join(values) if values else "请输入要屏蔽的 jm 号或标签",
            )
            return
        if not group:
            await self._say(event, "此命令仅支持群聊")
            return
        if command == "开启jm":
            self.store.set_group(group, "enabled", True)
            await self._say(event, "已启用本群 jm 功能！")
            return
        if not await self._group_admin(event):
            await self._say(event, "权限不足，需要群管理员或群主权限")
            return
        if command == "关闭jm":
            key = self._session(event)
            if argument == "确认":
                self.confirmations.pop(key, None)
                self.store.set_group(group, "enabled", False)
                await self._say(event, "已禁用本群 jm 功能！")
            else:
                self.confirmations[key] = time.monotonic()
                await self._say(
                    event, "禁用后需要超级用户重新开启。确认关闭请在 2 分钟内发送“确认”"
                )
        elif command == "jm黑名单":
            users = self.store.group(group).get("blacklist", [])
            await self._say(
                event,
                "当前群 jm 黑名单：\n" + "\n".join(users) if users else "当前群的黑名单列表为空",
            )
        elif command in {"jm拉黑", "jm解除拉黑"}:
            targets = [
                str(segment.qq)
                for segment in event.get_messages()
                if isinstance(segment, At) and str(segment.qq) != str(event.get_self_id())
            ]
            if not targets and re.fullmatch(r"[0-9]+", argument):
                targets = [argument]
            if not targets:
                await self._say(event, "请使用 @ 指定用户，或输入用户 QQ 号")
                return
            target = targets[0]
            if not await self._group_admin(event, target):
                await self._say(event, "权限不足，群管理员只能操作普通成员")
                return
            self.store.set_blacklisted(group, target, command == "jm拉黑")
            await self._say(event, f"已{'拉黑' if command == 'jm拉黑' else '解除拉黑'} {target}")
        elif command == "jm设置文件夹":
            if not argument:
                await self._say(event, "请输入要设置的群文件夹名称")
                return
            root = await event.bot.call_action("get_group_root_files", group_id=int(group))
            folder = next(
                (
                    item.get("folder_id")
                    for item in root.get("folders", [])
                    if item.get("folder_name") == argument
                ),
                None,
            )
            if not folder:
                created = await event.bot.call_action(
                    "create_group_file_folder", group_id=int(group), folder_name=argument
                )
                if created.get("result", {}).get("retCode", 0) != 0:
                    raise RuntimeError("创建群文件夹失败")
                folder = created.get("folder_id") or created.get("groupItem", {}).get(
                    "folderInfo", {}
                ).get("folderId")
            if not folder:
                raise RuntimeError("协议端未返回群文件夹 ID")
            self.store.set_group(group, "folder_id", folder)
            await self._say(event, "已设置本群的本子储存文件夹")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.regex(r"^确认$")
    async def confirm_close(self, event: AstrMessageEvent):
        key = self._session(event)
        pending = self.confirmations.pop(key, None)
        if (
            pending is None
            or time.monotonic() - pending > 120
            or not event.get_group_id()
            or self.stopping
        ):
            return
        event.stop_event()
        try:
            await self._manage(event, "关闭jm", "确认")
        except Exception as exc:
            logger.warning("JM 关闭确认失败 (%s)", type(exc).__name__)
            await self._say(event, "关闭失败，请重新尝试")

    async def _maintenance(self):
        clock = ZoneInfo(self.config.get("timezone", "Asia/Shanghai"))
        marker_path = self.data_dir / "maintenance.json"
        if marker_path.exists():
            import json

            markers = json.loads(marker_path.read_text(encoding="utf-8"))
        else:
            now = datetime.now(clock)
            markers = {"week": now.strftime("%G-%V"), "cache_day": now.date().isoformat()}
            atomic_json(marker_path, markers)
        while True:
            try:
                now = datetime.now(clock)
                week, day = now.strftime("%G-%V"), now.date().isoformat()
                if markers.get("week") != week:
                    # Reset after in-flight reservations/uploads have settled.
                    async with self.download_lock:
                        self.store.reset_limits()
                        markers["week"] = week
                if now.hour >= 3 and markers.get("cache_day") != day:
                    await self.service.clear_cache()
                    markers["cache_day"] = day
                atomic_json(marker_path, markers)
                cutoff = time.monotonic() - 1800
                self.searches = {
                    key: value for key, value in self.searches.items() if value["created"] >= cutoff
                }
                self.confirmations = {
                    key: value
                    for key, value in self.confirmations.items()
                    if time.monotonic() - value <= 120
                }
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("JM 定时维护失败 (%s)", type(exc).__name__)
            await asyncio.sleep(60)
