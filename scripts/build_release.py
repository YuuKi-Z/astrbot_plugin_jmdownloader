"""Create an installable archive using an explicit, secret-free file list."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "astrbot_plugin_jmdownloader"
FILES = [
    "__init__.py",
    "main.py",
    "state.py",
    "service.py",
    "compat.py",
    "migrate.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
    "logo.png",
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    "tests/test_migration.py",
    "tests/test_plugin.py",
    "scripts/build_release.py",
]


def main():
    destination = ROOT / "dist" / f"{NAME}-1.0.2.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, arcname=f"{NAME}/{name}")
    print(
        json.dumps(
            {
                "archive": str(destination),
                "files": len(FILES),
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
