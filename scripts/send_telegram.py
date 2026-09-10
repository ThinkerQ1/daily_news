from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

from utils import PROJECT_ROOT, REPORTS_DIR


DEFAULT_PROXY = "socks5h://127.0.0.1:7897"
ENV_FILES = [
    PROJECT_ROOT / ".env.example",
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / ".env.dailynews",
]
REPORT_PATTERN = "daily-tech-news-*.md"


class TelegramSendError(RuntimeError):
    pass


def find_latest_report() -> Path:
    reports = sorted(
        REPORTS_DIR.glob(REPORT_PATTERN),
        key=lambda path: path.name,
        reverse=True,
    )
    if not reports:
        raise TelegramSendError(
            f"No report found in {REPORTS_DIR} matching {REPORT_PATTERN}"
        )
    return reports[0]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
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
    return values


def load_telegram_config() -> tuple[dict[str, str], list[str]]:
    config: dict[str, str] = {}
    warnings: list[str] = []

    for path in ENV_FILES:
        file_values = _read_env_file(path)
        if file_values:
            config.update(file_values)
            if path.name == ".env.example" and any(key.startswith("TELEGRAM_") for key in file_values):
                warnings.append(
                    "Using legacy .env.example Telegram config. Move secrets to .env.dailynews "
                    "with DAILYNEWS_TELEGRAM_* keys to avoid OpenClaw/Codex conflicts."
                )

    for key in ("BOT_TOKEN", "CHAT_ID", "PROXY"):
        prefixed_key = f"DAILYNEWS_TELEGRAM_{key}"
        if os.environ.get(prefixed_key):
            config[prefixed_key] = os.environ[prefixed_key]

    if os.environ.get("DAILYNEWS_ALLOW_GENERIC_TELEGRAM_ENV") == "1":
        for key in ("BOT_TOKEN", "CHAT_ID", "PROXY"):
            generic_key = f"TELEGRAM_{key}"
            if os.environ.get(generic_key):
                config[generic_key] = os.environ[generic_key]
    return config, warnings


def _config_value(config: dict[str, str], name: str, required: bool = True, default: str = "") -> str:
    value = (config.get(f"DAILYNEWS_{name}") or config.get(name) or default).strip()
    if not value:
        if not required:
            return ""
        raise TelegramSendError(f"Missing required environment variable: {name}")
    return value


def _redact_token(message: str, token: str) -> str:
    return message.replace(token, "<redacted>").replace(
        f"/bot{token}", "/bot<redacted>"
    )


def send_report(report_path: Path) -> Path:
    config, warnings = load_telegram_config()
    for warning in warnings:
        print(f"Telegram config warning: {warning}", file=sys.stderr)

    report_path = Path(report_path)
    if not report_path.exists():
        raise TelegramSendError(f"Report file not found: {report_path}")
    if not report_path.is_file():
        raise TelegramSendError(f"Report path is not a file: {report_path}")

    token = _config_value(config, "TELEGRAM_BOT_TOKEN")
    chat_id = _config_value(config, "TELEGRAM_CHAT_ID")
    proxy = _config_value(config, "TELEGRAM_PROXY", required=False, default=DEFAULT_PROXY)
    proxy = proxy or DEFAULT_PROXY

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    data = {
        "chat_id": chat_id,
        "caption": f"今日推送已生成：{report_path.name}",
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        with report_path.open("rb") as report_file:
            response = requests.post(
                url,
                data=data,
                files={"document": (report_path.name, report_file, "text/markdown")},
                proxies=proxies,
                timeout=60,
            )
    except requests.RequestException as exc:
        message = _redact_token(str(exc), token)
        raise TelegramSendError(f"Telegram request failed: {message}") from exc

    if not response.ok:
        raise TelegramSendError(
            "Telegram request failed: "
            f"HTTP {response.status_code} {response.text}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise TelegramSendError(
            f"Telegram response is not valid JSON: {response.text}"
        ) from exc

    if not payload.get("ok"):
        raise TelegramSendError(f"Telegram API returned failure: {payload}")

    return report_path


def send_latest_report(report_path: Path | None = None) -> Path:
    return send_report(report_path or find_latest_report())


def main() -> int:
    try:
        report_path = send_latest_report()
    except TelegramSendError as exc:
        print(f"Telegram send failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Telegram send failed with unexpected error: {exc}", file=sys.stderr)
        return 1

    print(f"Telegram report sent: {report_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
