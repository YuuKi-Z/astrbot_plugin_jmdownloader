"""Keep the NoneBot 1.0.4 JSON structure, including unrecognised fields."""

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

DEFAULT_TAGS = ["獵奇", "重口", "YAOI", "yaoi", "男同", "血腥", "猎奇", "虐杀", "恋尸癖"]
DEFAULT_IDS = [
    "136494",
    "323666",
    "350234",
    "363848",
    "405848",
    "454278",
    "481481",
    "559716",
    "611650",
    "629252",
    "69658",
    "626487",
    "400002",
    "208092",
    "253199",
    "382596",
    "418600",
    "279464",
    "565616",
    "222458",
]


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class StateStore:
    def __init__(self, path: Path, config: dict):
        self.path = path
        self.config = config
        if path.exists():
            # Never replace an unreadable existing file with empty defaults.
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(self.data, dict):
                raise ValueError("jmcomic_data.json 必须是 JSON 对象")
        else:
            self.data = {
                "restricted_tags": DEFAULT_TAGS.copy(),
                "restricted_ids": DEFAULT_IDS.copy(),
            }
            self.save()

    def save(self):
        atomic_json(self.path, self.data)

    def group(self, group_id: str) -> dict:
        return self.data.get(str(group_id), {})

    def group_enabled(self, group_id: str) -> bool:
        return bool(
            self.group(group_id).get("enabled", self.config.get("jmcomic_allow_groups", False))
        )

    def blacklisted(self, group_id: str, user_id: str) -> bool:
        return str(user_id) in self.group(group_id).get("blacklist", [])

    def set_group(self, group_id: str, key: str, value):
        self.data.setdefault(str(group_id), {})[key] = value
        self.save()

    def set_blacklisted(self, group_id: str, user_id: str, enabled: bool):
        users = self.data.setdefault(str(group_id), {}).setdefault("blacklist", [])
        user_id = str(user_id)
        if enabled and user_id not in users:
            users.append(user_id)
        elif not enabled and user_id in users:
            users.remove(user_id)
        self.save()

    def remaining(self, user_id: str) -> int:
        return int(
            self.data.get("user_limits", {}).get(
                str(user_id), self.config.get("jmcomic_user_limits", 5)
            )
        )

    def consume(self, user_id: str) -> bool:
        remaining = self.remaining(user_id)
        if remaining <= 0:
            return False
        self.data.setdefault("user_limits", {})[str(user_id)] = remaining - 1
        self.save()
        return True

    def refund(self, user_id: str):
        self.data.setdefault("user_limits", {})[str(user_id)] = self.remaining(user_id) + 1
        self.save()

    def reset_limits(self):
        self.data["user_limits"] = {
            uid: int(self.config.get("jmcomic_user_limits", 5))
            for uid in self.data.get("user_limits", {})
        }
        self.save()

    def blocked(self, photo_id: str, tags=()) -> bool:
        ids = {str(item) for item in self.data.get("restricted_ids", DEFAULT_IDS)}
        ids.update(str(item) for item in self.data.get("forbidden_albums", []))
        restricted = set(self.data.get("restricted_tags", DEFAULT_TAGS))
        return str(photo_id) in ids or bool(restricted.intersection(tags))

    def add_restrictions(self, key: str, values: list[str]):
        entries = self.data.setdefault(
            key, deepcopy(DEFAULT_IDS if key == "restricted_ids" else DEFAULT_TAGS)
        )
        entries.extend(value for value in values if value not in entries)
        self.save()
