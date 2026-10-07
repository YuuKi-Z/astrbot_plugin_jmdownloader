"""Import an offline NoneBot snapshot into an AstrBot data directory.

No NoneBot modules are imported: migration does not start the old bot or log in.
Secrets are written to private config files, never printed or shipped in ZIPs.
"""

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .state import atomic_json
else:
    from state import atomic_json

PLUGIN = "astrbot_plugin_jmdownloader"
DEFAULT_CONFIG = {
    "jmcomic_log": False,
    "jmcomic_proxies": "system",
    "jmcomic_thread_count": 10,
    "jmcomic_username": "",
    "jmcomic_password": "",
    "jmcomic_allow_groups": False,
    "jmcomic_user_limits": 5,
    "jmcomic_modify_real_md5": False,
    "jmcomic_blocked_message": "猫猫吃掉了一个不豪吃的本子",
    "jmcomic_results_per_page": 20,
    "jmcomic_superusers": [],
    "timezone": "Asia/Shanghai",
    "onebot_file_base": "",
}


def import_snapshot(snapshot: dict, astrbot_data: Path, overwrite=False) -> dict:
    config = dict(DEFAULT_CONFIG)
    config.update(snapshot["config"])
    for key in ("jmcomic_username", "jmcomic_password"):
        config[key] = str(config.get(key) or "")
    data = snapshot["data"]
    if not isinstance(data, dict):
        raise ValueError("Source plugin data must be a JSON object")
    astrbot_data = astrbot_data.resolve()
    config_file = astrbot_data / "config" / f"{PLUGIN}_config.json"
    data_dir = astrbot_data / "plugin_data" / PLUGIN
    data_file = data_dir / "jmcomic_data.json"
    existing = [path for path in (config_file, data_file) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Destination already exists. Review it before using --overwrite.")
    backup_dir = None
    if existing:
        backup_dir = (
            data_dir / "migration_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        backup_dir.mkdir(parents=True, exist_ok=False)
        for path in existing:
            shutil.copy2(path, backup_dir / path.name)
    data_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(data_dir, 0o700)
    atomic_json(config_file, config)
    atomic_json(data_file, data)
    # Keep the complete original export outside the plugin's source directory.
    atomic_json(data_dir / "nonebot_migration_snapshot.json", snapshot)
    imported = json.loads(data_file.read_text(encoding="utf-8"))
    assert imported == data, "Migration verification failed"
    return {
        "config_file": str(config_file),
        "data_file": str(data_file),
        "groups": sum(key.isdigit() for key in imported),
        "user_limits": len(imported.get("user_limits", {})),
        "data_verified": True,
        "previous_destination_backup": str(backup_dir) if backup_dir else None,
    }


def snapshot_from_env(env_files: list[Path], data_file: Path) -> dict:
    from dotenv import dotenv_values

    values = {}
    for file in env_files:
        values.update({key.lower(): value for key, value in dotenv_values(file).items()})
    config = dict(DEFAULT_CONFIG)
    for key, default in config.items():
        if key not in values:
            continue
        raw = values[key]
        if isinstance(default, bool):
            if str(raw).lower() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                raise ValueError(f"Invalid boolean setting: {key}")
            raw = str(raw).lower() in {"true", "1", "yes", "on"}
        elif isinstance(default, int):
            raw = int(raw)
        elif isinstance(default, list):
            raw = json.loads(raw)
        config[key] = raw
    config["jmcomic_superusers"] = json.loads(values.get("superusers") or "[]")
    config["timezone"] = values.get("tz") or config["timezone"]
    return {
        "config": config,
        "data": json.loads(data_file.read_text(encoding="utf-8")),
        "source_version": "1.0.4",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--snapshot", type=Path, help="migration-export.json from the offline backup"
    )
    source.add_argument(
        "--env", type=Path, action="append", help=".env then .env.prod; later files take precedence"
    )
    parser.add_argument(
        "--source-data", type=Path, help="Original jmcomic_data.json, required with --env"
    )
    parser.add_argument("--astrbot-data", type=Path, required=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Back up existing destination settings before replacing them",
    )
    args = parser.parse_args()
    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    else:
        if not args.source_data:
            parser.error("--source-data is required with --env")
        snapshot = snapshot_from_env(args.env, args.source_data)
    print(
        json.dumps(
            import_snapshot(snapshot, args.astrbot_data, args.overwrite),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
