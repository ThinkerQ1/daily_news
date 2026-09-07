from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_FILE = PROJECT_ROOT / "prompts" / "openclaw" / "sspai_collect_prompt.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "openclaw"
LOG_DIR = PROJECT_ROOT / "logs" / "openclaw"
SESSION_KEY = os.getenv("OPENCLAW_SESSION_KEY", "agent:main:main")
TIMEOUT_SECONDS = 600


def _log(message: str) -> None:
    for line in str(message).splitlines() or [""]:
        print(f"[openclaw][sspai] {line}")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _output_file() -> Path:
    date_str = datetime.now().astimezone().date().isoformat()
    return OUTPUT_DIR / f"sspai_{date_str}.json"


def _ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _write_payload(payload: dict[str, Any]) -> None:
    with _output_file().open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _fallback(error: str) -> dict[str, Any]:
    payload = {
        "source": "sspai",
        "collected_at": _now_iso(),
        "items": [],
        "error": error,
    }
    _write_payload(payload)
    _log(f"fallback saved: {error}")
    return payload


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _response_text(stdout: str) -> str:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout

    payloads = result.get("result", {}).get("payloads", []) if isinstance(result, dict) else []
    if payloads and isinstance(payloads[0], dict) and isinstance(payloads[0].get("text"), str):
        return payloads[0]["text"]
    return stdout


def _published_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    return match.group(0) if match else None


def _clean_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("items is not an array")

    cleaned = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        tags = item.get("tags")
        cleaned.append(
            {
                "title": title,
                "url": url,
                "summary": str(item.get("summary") or "").strip(),
                "published_at": _published_date(item.get("published_at")),
                "source": "少数派",
                "tags": [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else [],
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return cleaned


def collect_sspai_via_openclaw() -> dict[str, Any]:
    _ensure_dirs()
    _log("collect start")

    try:
        prompt = PROMPT_FILE.read_text(encoding="utf-8")
    except Exception as exc:
        return _fallback(f"failed to read prompt: {exc}")

    command = [
        "openclaw",
        "agent",
        "--session-key",
        SESSION_KEY,
        "--message",
        prompt,
        "--json",
        "--timeout",
        str(TIMEOUT_SECONDS),
    ]

    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS + 10,
            check=False,
        )
    except FileNotFoundError:
        return _fallback("openclaw command not found")
    except subprocess.TimeoutExpired:
        return _fallback(f"openclaw timed out after {TIMEOUT_SECONDS} seconds")
    except Exception as exc:
        return _fallback(f"openclaw execution failed: {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return _fallback(f"openclaw exited with code {result.returncode}: {detail}")

    try:
        response = _strip_code_fence(_response_text(result.stdout))
        raw_payload = json.loads(response)
        if not isinstance(raw_payload, dict):
            raise ValueError("JSON top level is not an object")
        items = _clean_items(raw_payload.get("items"))
    except Exception as exc:
        return _fallback(f"invalid OpenClaw JSON: {exc}")

    payload = {
        "source": "sspai",
        "collected_at": _now_iso(),
        "items": items,
    }
    _write_payload(payload)
    _log(f"collect done: {len(items)} items saved to {_output_file()}")
    return payload


def main() -> int:
    try:
        collect_sspai_via_openclaw()
    except Exception as exc:
        _ensure_dirs()
        _fallback(f"unexpected error: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
