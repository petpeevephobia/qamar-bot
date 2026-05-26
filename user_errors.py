"""Map exceptions to short, human-readable Telegram replies."""

import json
from typing import Literal

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from drive_client import DriveAuthRequiredError, build_reauth_url

Context = Literal[
    "groq",
    "gemini",
    "drive_upload",
    "drive_delete",
    "drive_lookup",
]


def drive_reauth_message() -> str:
    try:
        url = build_reauth_url()
    except ValueError:
        return (
            "Google Drive needs to be reconnected, but the reconnect link is not configured "
            "(OAUTH_LINK_SECRET). Fix that in .env / Fly secrets and restart the bot."
        )
    return (
        "Google Drive is not connected or your login expired.\n"
        f"Open this link to sign in again:\n{url}\n\n"
        "Or send /reauth in this chat for the same link."
    )


def _http_status(exc: BaseException) -> int | None:
    if isinstance(exc, HttpError):
        return int(exc.resp.status)
    for attr in ("status_code", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_rate_limit(exc: BaseException) -> bool:
    status = _http_status(exc)
    if status == 429:
        return True
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "resourceexhausted" in name:
        return True
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in (
            "rate limit",
            "rate_limit",
            "too many requests",
            "quota exceeded",
            "resource exhausted",
            "requests per",
        )
    )


def _is_auth_error(exc: BaseException) -> bool:
    if isinstance(exc, (DriveAuthRequiredError, RefreshError)):
        return True
    status = _http_status(exc)
    if status in (401, 403):
        return True
    if isinstance(exc, json.JSONDecodeError):
        return True
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in (
            "invalid_grant",
            "token has been expired",
            "token has been revoked",
            "login required",
            "invalid credentials",
            "unauthorized",
        )
    )


def _rate_limit_message(context: Context) -> str:
    if context == "groq":
        return (
            "Groq (voice transcription) hit its rate or usage limit. "
            "Wait a few minutes and send your voice note again."
        )
    if context == "gemini":
        return (
            "Gemini (note writing) hit its rate or usage limit. "
            "Wait a few minutes and try your voice note again."
        )
    if context == "drive_upload":
        return (
            "Google Drive is limiting uploads right now. "
            "Your idea was drafted but not saved — try again in a few minutes."
        )
    if context == "drive_delete":
        return (
            "Google Drive is limiting requests right now. "
            "Wait a few minutes and run /delete again."
        )
    return (
        "Google Drive is limiting requests right now. "
        "Wait a few minutes and try again."
    )


def _generic_drive_message(context: Context) -> str:
    if context == "drive_upload":
        return (
            "Your note was drafted but could not be saved to Google Drive. "
            "Try again in a moment, or send /reauth if Drive asks you to sign in."
        )
    if context == "drive_delete":
        return "Could not delete the note on Google Drive. Try again or send /reauth."
    return "Could not reach Google Drive. Try again or send /reauth."


def _generic_provider_message(context: Context) -> str:
    if context == "groq":
        return (
            "Voice transcription failed (Groq). "
            "Check your connection and API key, then try again."
        )
    if context == "gemini":
        return (
            "Note generation failed (Gemini). "
            "Check your connection and API key, then try again."
        )
    return "Something went wrong. Please try again in a moment."


def format_user_error(exc: BaseException, *, context: Context) -> str:
    """Turn an exception into a message safe to send on Telegram."""
    if isinstance(exc, DriveAuthRequiredError):
        return drive_reauth_message()

    if isinstance(exc, RefreshError) or _is_auth_error(exc):
        if context.startswith("drive") or isinstance(exc, json.JSONDecodeError):
            if isinstance(exc, json.JSONDecodeError):
                return (
                    "Google Drive login data on the server is invalid (bad token JSON). "
                    "Send /reauth to sign in again. If you deploy on Fly, update "
                    "GOOGLE_OAUTH_TOKEN_JSON from token.json after reauth."
                )
            return drive_reauth_message()

    if _is_rate_limit(exc):
        return _rate_limit_message(context)

    if isinstance(exc, ValueError) and context.startswith("drive"):
        msg = str(exc).lower()
        if "google_drive_folder_id" in msg or "folder_id" in msg:
            return (
                "Google Drive folder is not configured (GOOGLE_DRIVE_FOLDER_ID). "
                "Add it in .env or Fly secrets and restart the bot."
            )

    if context.startswith("drive"):
        return _generic_drive_message(context)

    return _generic_provider_message(context)
