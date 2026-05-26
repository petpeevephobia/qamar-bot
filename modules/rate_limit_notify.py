"""Track Groq/Gemini daily rate limits and notify users at Pacific midnight."""

import json
import os
import tempfile
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from telegram import Bot
from telegram.error import TelegramError

PACIFIC = ZoneInfo("America/Los_Angeles")
FLAGS_FILE = "brain/rate_limit_notify.json"

Provider = Literal["groq", "gemini"]


def pacific_today() -> date:
    return datetime.now(PACIFIC).date()


def format_reset_countdown() -> str:
    now = datetime.now(PACIFIC)
    next_midnight = datetime.combine(now.date() + timedelta(days=1), time.min, PACIFIC)
    delta = next_midnight - now
    total_minutes = int(delta.total_seconds()) // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes}m"


def _load_flags() -> dict[str, dict]:
    if not os.path.exists(FLAGS_FILE):
        return {}
    try:
        with open(FLAGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"[WARN] {FLAGS_FILE} is not a JSON object; ignoring")
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] Could not read {FLAGS_FILE}: {e}")
        return {}


def _save_flags(flags: dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(FLAGS_FILE), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(FLAGS_FILE), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(flags, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, FLAGS_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def mark_rate_limited(user_id: int, provider: Provider) -> None:
    today = pacific_today().isoformat()
    flags = _load_flags()
    key = str(user_id)
    entry = flags.get(key)
    if entry and entry.get("date") == today:
        providers = set(entry.get("providers", []))
        providers.add(provider)
        entry["providers"] = sorted(providers)
    else:
        flags[key] = {"date": today, "providers": [provider]}
    _save_flags(flags)


def _midnight_reset_message(providers: list[str]) -> str:
    has_groq = "groq" in providers
    has_gemini = "gemini" in providers
    if has_groq and has_gemini:
        limit_text = "Groq and Gemini limits have"
    elif has_groq:
        limit_text = "Groq limits have"
    else:
        limit_text = "Gemini limits have"
    return (
        f"Good news — your daily {limit_text} reset (midnight Pacific). "
        "You can send voice notes again."
    )


async def send_midnight_reset_notifications(bot: Bot) -> None:
    yesterday = (pacific_today() - timedelta(days=1)).isoformat()
    flags = _load_flags()
    notified_keys: list[str] = []

    for user_id, entry in flags.items():
        if not isinstance(entry, dict) or entry.get("date") != yesterday:
            continue
        providers = entry.get("providers", [])
        if not providers:
            continue
        text = _midnight_reset_message(providers)
        try:
            await bot.send_message(chat_id=int(user_id), text=text)
            print(f"[INFO] Midnight rate-limit reset notified user {user_id}")
            notified_keys.append(user_id)
        except TelegramError as e:
            print(f"[WARN] Could not notify user {user_id} at midnight: {e}")

    if notified_keys:
        for key in notified_keys:
            flags.pop(key, None)
        _save_flags(flags)
