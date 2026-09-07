from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"
SOURCES_FILE = PROJECT_ROOT / "sources.yml"


def ensure_dirs() -> None:
    for path in (RAW_DIR, PROCESSED_DIR, REPORTS_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_sources() -> dict[str, Any]:
    with SOURCES_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    path = Path(path)
    if not path.exists():
        return values

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]

            values[key] = value
            os.environ.setdefault(key, value)

    return values


def get_env_value(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def today_string() -> str:
    return datetime.now().astimezone().date().isoformat()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return slug or f"source-{stable_id(value)}"


def stable_id(*parts: str) -> str:
    raw = "||".join(part or "" for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip().lower()
    title = re.sub(r"[^\w\s\u4e00-\u9fff]", "", title)
    return title


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def google_news_rss_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
