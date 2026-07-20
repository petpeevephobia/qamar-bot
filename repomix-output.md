This file is a merged representation of the entire codebase, combined into a single document by Repomix.

# File Summary

## Purpose
This file contains a packed representation of the entire repository's contents.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
```
.github/
  workflows/
    fly-deploy.yml
brain/
  qamar_role.txt
  tags.txt
  template.md
modules/
  __init__.py
  authorize_drive.py
  drive_client.py
  oauth_app.py
  rate_limit_notify.py
  user_errors.py
.dockerignore
.gitignore
.replit
Dockerfile
fly.toml
main.py
pyproject.toml
README.md
requirements.txt
```

# Files

## File: .github/workflows/fly-deploy.yml
````yaml
# See https://fly.io/docs/app-guides/continuous-deployment-with-github-actions/

name: Fly Deploy
on:
  push:
    branches:
      - main
jobs:
  deploy:
    name: Deploy app
    runs-on: ubuntu-latest
    concurrency: deploy-group    # optional: ensure only one action runs at a time
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
````

## File: brain/qamar_role.txt
````
You are Qamar, a no-nonsense, chill AI assistant for a busy Gen Z founder. You’re casual, very sarcastic, and keep it real—like a best friend who actually gets shit done. Tone is straightforward, easygoing, with just enough personality to keep things interesting. No fluff, no corporate speak.

You help your user:

Remember key ideas and decisions (you keep highlights of what they say).

Summarize voice notes into quick, clear takeaways.

Manage their calendar and tasks without nagging.

Give useful, honest advice (with a splash of sarcasm when appropriate).

Surf the internet if you don’t know something, so your answers aren’t just guesses.

Personality & Tone:

Chill but sharp; a bit sarcastic but supportive. Tell it like it is; don't sugar-coat responses.

Talk like a member of Gen Z. Use Gen Z slang sparingly — keep it natural, never forced.

No over-the-top hype or enthusiasm. You're nonchalant.

Mirror the user’s vibe—if they swear, you can swear back, but keep it tasteful.

Don't sound robotic or preachy.

Take a forward-thinking view. You think 5 steps ahead of the user. Predict what the user may need.

How you behave:

Stay cool even if the user vents.

Break down big stuff into easy chunks if they’re stressed.

Keep responses short and punchy, no essays.

Reference past highlights only when it adds value.

Ask follow-up questions if you need more info.

Your core jobs:
1. Personal Assistant Brain

Transcribe and summarize voice notes.

Track tasks and remind about stale ones.

Manage calendar events smoothly.

Check and update schedule.

Give quick daily recaps.

2. Client Manager Brain

Log and track leads.

Turn client voice notes into briefs.

Repurpose content into smaller pieces.

Remember client project details.

What you don’t do:

Don’t pretend you’re human; you’re a bot with personality.

No medical/legal/financial advice.

Don’t be a therapist.

Don’t just repeat what the user says.

Don’t get formal—always keep chill as your baseline.

Don't use any text formatting in your output. No asterisks (*) and such.

Bonus:
If you don’t know something, look it up online before making stuff up. Keep your answers real and relevant. Add the direct links of where you get your sources from for each response you produce from a search query, as well as the date of when the information was posted online, if possible.
````

## File: modules/__init__.py
````python
"""Qamar bot support modules (Drive OAuth, errors, rate-limit notifications)."""
````

## File: modules/authorize_drive.py
````python
"""Print the web OAuth URL (run main.py first so :8080 is listening)."""

import os

from dotenv import load_dotenv

from modules.drive_client import build_reauth_url

load_dotenv()

if __name__ == "__main__":
    url = build_reauth_url()
    print("Make sure Qamar is running (python main.py), then open this URL in your browser:")
    print(url)
````

## File: modules/oauth_app.py
````python
"""FastAPI routes for Google Drive web OAuth (Fly.io + local)."""



import os



from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request

from fastapi.responses import HTMLResponse, RedirectResponse



from google_auth_oauthlib.flow import Flow



from modules.drive_client import (

    create_oauth_flow,

    get_drive_service,

    save_credentials,

)



load_dotenv()



# Local dev uses http:// redirect URIs; oauthlib requires this for non-HTTPS callbacks.

_redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback")

if _redirect_uri.startswith("http://"):

    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")



app = FastAPI(title="Qamar OAuth")

_pending_flows: dict[str, Flow] = {}





def _check_link_secret(secret: str | None) -> None:

    expected = os.getenv("OAUTH_LINK_SECRET", "")

    if not expected or secret != expected:

        raise HTTPException(status_code=403, detail="Invalid or missing secret.")





def _callback_url(request: Request) -> str:

    url = str(request.url)

    if request.headers.get("x-forwarded-proto") == "https" and url.startswith("http://"):

        url = "https://" + url[7:]

    return url





@app.get("/")

def health():

    return {"ok": True, "service": "qamar-bot"}





@app.get("/oauth/start")

def oauth_start(secret: str | None = None):

    _check_link_secret(secret)

    flow = create_oauth_flow()

    auth_url, state = flow.authorization_url(

        access_type="offline",

        include_granted_scopes="true",

        prompt="consent",

    )

    _pending_flows[state] = flow

    return RedirectResponse(auth_url)





@app.get("/oauth/callback")

def oauth_callback(request: Request):

    state = request.query_params.get("state")

    flow = _pending_flows.pop(state, None) if state else None

    if not flow:

        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")



    if request.query_params.get("error"):

        raise HTTPException(

            status_code=400,

            detail=request.query_params.get("error_description", "OAuth denied."),

        )



    flow.fetch_token(authorization_response=_callback_url(request))

    save_credentials(flow.credentials)



    try:

        service = get_drive_service()

        about = service.about().get(fields="user").execute()

        email = about.get("user", {}).get("emailAddress", "your account")

    except Exception:

        email = "your account"



    return HTMLResponse(

        f"<h1>Google Drive connected</h1>"

        f"<p>Signed in as <strong>{email}</strong>.</p>"

        f"<p>You can close this tab and return to Telegram.</p>"

    )
````

## File: modules/rate_limit_notify.py
````python
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
````

## File: .replit
````
entrypoint = "main.py"
modules = ["python-3.11"]

[nix]
channel = "stable-24_05"

[unitTest]
language = "python3"

[gitHubImport]
requiredFiles = [".replit", "replit.nix"]

[deployment]
run = ["python3", "main.py"]
deploymentTarget = "cloudrun"
````

## File: Dockerfile
````dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
````

## File: brain/template.md
````markdown
{{date}} {{time}}
Tags:
Maturity: baby/teen/adult
>baby = content needs development, teen = content is quite developed, adult = content is very developed.

___
# {{Title}}

# References
N/A
````

## File: modules/drive_client.py
````python
"""Google Drive uploads using OAuth user credentials (personal Drive quota)."""

import io
import json
import os
import time
from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

load_dotenv()

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
GOOGLE_OAUTH_CLIENT_SECRETS = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "credentials.json")
GOOGLE_OAUTH_TOKEN = os.getenv("GOOGLE_OAUTH_TOKEN", "token.json")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")

_drive_service = None

_DEBUG_LOG_PATH = "debug-5b8722.log"


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "5b8722",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # #endregion


class DriveAuthRequiredError(Exception):
    """Raised when Google Drive needs a new OAuth login."""

    def __init__(self, message: str | None = None):
        self.reauth_url = build_reauth_url()
        super().__init__(message or "Google Drive login required.")


def build_reauth_url() -> str:
    base = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
    # base = os.getenv("BASE_URL", "https://qamar-bot.fly.dev").rstrip("/")
    secret = os.getenv("OAUTH_LINK_SECRET", "")
    if not secret:
        raise ValueError("OAUTH_LINK_SECRET must be set in .env")
    return f"{base}/oauth/start?secret={secret}"


def _parse_token_json_string(raw: str) -> tuple[dict, str]:
    """Parse OAuth token JSON from env; tolerate common Fly/shell quoting mistakes."""
    raw = raw.strip().lstrip("\ufeff")
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1].strip()

    candidates: list[tuple[str, str]] = [("direct", raw)]
    if raw.startswith("{{") and raw.endswith("}}"):
        candidates.append(("strip_double_brace", raw[1:-1]))
    if raw.startswith("{{"):
        candidates.append(("strip_leading_brace", raw[1:]))

    last_error: json.JSONDecodeError | None = None
    for method, candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as e:
            last_error = e
            continue
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError as e:
                last_error = e
                continue
        if isinstance(parsed, dict):
            return parsed, method
    if last_error:
        raise last_error
    raise json.JSONDecodeError("Invalid OAuth token JSON", raw, 0)


def _load_token_data() -> dict | None:
    env_json = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    # #region agent log
    _agent_debug_log(
        "E",
        "drive_client.py:_load_token_data",
        "token source check",
        {
            "has_env_json": bool(env_json),
            "env_json_len": len(env_json) if env_json else 0,
            "env_starts_with_brace": env_json.strip().startswith("{") if env_json else False,
            "env_starts_with_double_brace": env_json.strip().startswith("{{") if env_json else False,
            "env_has_single_quotes": "'" in env_json if env_json else False,
            "token_file_exists": os.path.exists(GOOGLE_OAUTH_TOKEN),
            "token_file_path": GOOGLE_OAUTH_TOKEN,
        },
    )
    # #endregion
    if env_json:
        try:
            parsed, parse_method = _parse_token_json_string(env_json)
            # #region agent log
            _agent_debug_log(
                "E",
                "drive_client.py:_load_token_data",
                "env json parsed ok",
                {
                    "parse_method": parse_method,
                    "keys": sorted(parsed.keys()) if isinstance(parsed, dict) else "not_dict",
                },
            )
            # #endregion
            return parsed
        except json.JSONDecodeError as e:
            # #region agent log
            _agent_debug_log(
                "E",
                "drive_client.py:_load_token_data",
                "env json parse failed",
                {
                    "error": str(e),
                    "error_pos": e.pos,
                    "env_json_len": len(env_json),
                    "prefix_ord": [ord(c) for c in env_json.strip()[:4]],
                },
            )
            # #endregion
            raise
    if os.path.exists(GOOGLE_OAUTH_TOKEN):
        with open(GOOGLE_OAUTH_TOKEN, encoding="utf-8") as f:
            file_data = json.load(f)
        # #region agent log
        _agent_debug_log(
            "F",
            "drive_client.py:_load_token_data",
            "token loaded from file",
            {"keys": sorted(file_data.keys()) if isinstance(file_data, dict) else "not_dict"},
        )
        # #endregion
        return file_data
    # #region agent log
    _agent_debug_log("G", "drive_client.py:_load_token_data", "no token source found", {})
    # #endregion
    return None


def save_credentials(creds: Credentials) -> None:
    token_json = creds.to_json()
    token_dir = os.path.dirname(GOOGLE_OAUTH_TOKEN)
    if token_dir:
        os.makedirs(token_dir, exist_ok=True)
    with open(GOOGLE_OAUTH_TOKEN, "w", encoding="utf-8") as f:
        f.write(token_json)
    os.environ["GOOGLE_OAUTH_TOKEN_JSON"] = token_json
    invalidate_drive_service()


def create_oauth_flow() -> Flow:
    if not os.path.exists(GOOGLE_OAUTH_CLIENT_SECRETS):
        raise FileNotFoundError(
            f"Missing {GOOGLE_OAUTH_CLIENT_SECRETS}. "
            "Create a Web OAuth client in Google Cloud Console and download credentials.json."
        )
    return Flow.from_client_secrets_file(
        GOOGLE_OAUTH_CLIENT_SECRETS,
        scopes=DRIVE_SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
    )


def get_drive_credentials() -> Credentials:
    try:
        token_data = _load_token_data()
    except json.JSONDecodeError:
        # #region agent log
        _agent_debug_log(
            "E",
            "drive_client.py:get_drive_credentials",
            "re-raising JSONDecodeError from token load",
            {},
        )
        # #endregion
        raise
    creds = None
    if token_data:
        creds = Credentials.from_authorized_user_info(token_data, DRIVE_SCOPES)

    if creds and creds.valid:
        # #region agent log
        _agent_debug_log("H", "drive_client.py:get_drive_credentials", "credentials valid", {})
        # #endregion
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
            # #region agent log
            _agent_debug_log("H", "drive_client.py:get_drive_credentials", "credentials refreshed", {})
            # #endregion
            return creds
        except RefreshError as e:
            # #region agent log
            _agent_debug_log(
                "H",
                "drive_client.py:get_drive_credentials",
                "refresh failed",
                {"error": type(e).__name__},
            )
            # #endregion
            raise DriveAuthRequiredError(
                "Google Drive refresh token expired or revoked."
            ) from e

    # #region agent log
    _agent_debug_log(
        "G",
        "drive_client.py:get_drive_credentials",
        "no valid credentials",
        {"had_token_data": bool(token_data), "creds_created": creds is not None},
    )
    # #endregion
    raise DriveAuthRequiredError("No valid Google Drive token. Re-authorize to continue.")


def invalidate_drive_service() -> None:
    global _drive_service
    _drive_service = None


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        try:
            _drive_service = build("drive", "v3", credentials=get_drive_credentials())
            # #region agent log
            _agent_debug_log("H", "drive_client.py:get_drive_service", "drive service built", {})
            # #endregion
        except Exception as e:
            # #region agent log
            _agent_debug_log(
                "E",
                "drive_client.py:get_drive_service",
                "drive service build failed",
                {"error_type": type(e).__name__, "error": str(e)},
            )
            # #endregion
            raise
    return _drive_service


def upload_markdown(
    drive_service,
    markdown: str,
    upload_filename: str,
    folder_id: str,
) -> dict:
    media = MediaIoBaseUpload(
        io.BytesIO(markdown.encode("utf-8")),
        mimetype="text/markdown",
        resumable=False,
    )
    body = {"name": upload_filename, "parents": [folder_id]}
    return (
        drive_service.files()
        .create(body=body, media_body=media, fields="id,name")
        .execute()
    )


def save_note_to_drive(drive_service, markdown: str, upload_filename: str) -> str:
    if not GOOGLE_DRIVE_FOLDER_ID:
        raise ValueError(
            "GOOGLE_DRIVE_FOLDER_ID is not set in .env — add the folder ID from your Drive URL."
        )
    upload_markdown(
        drive_service,
        markdown,
        upload_filename,
        GOOGLE_DRIVE_FOLDER_ID,
    )
    return upload_filename


def _vault_md_query() -> str:
    if not GOOGLE_DRIVE_FOLDER_ID:
        raise ValueError(
            "GOOGLE_DRIVE_FOLDER_ID is not set in .env. Add the folder ID from your Drive URL."
        )
    return (
        f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed=false and "
        "(mimeType='text/markdown' or name contains '.md')"
    )


def list_vault_notes(drive_service) -> list[dict]:
    """Return {id, name} for every markdown note in the vault folder."""
    notes: list[dict] = []
    page_token = None
    while True:
        results = (
            drive_service.files()
            .list(
                q=_vault_md_query(),
                fields="nextPageToken, files(id, name, createdTime)",
                pageSize=100,
                pageToken=page_token,
            )
            .execute()
        )
        notes.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return notes


def download_note_content(drive_service, file_id: str) -> str:
    request = drive_service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue().decode("utf-8")


def get_most_recent_note(drive_service) -> dict | None:
    """Return {id, name, createdTime} for the newest markdown file in the vault, or None."""
    results = (
        drive_service.files()
        .list(
            q=_vault_md_query(),
            orderBy="createdTime desc",
            pageSize=1,
            fields="files(id, name, createdTime)",
        )
        .execute()
    )
    files = results.get("files", [])
    return files[0] if files else None


def delete_note_by_id(drive_service, file_id: str) -> str:
    """Permanently delete a Drive file by id. Returns the deleted file's name."""
    meta = drive_service.files().get(fileId=file_id, fields="name").execute()
    drive_service.files().delete(fileId=file_id).execute()
    return meta["name"]
````

## File: modules/user_errors.py
````python
"""Map exceptions to short, human-readable Telegram replies."""

import json
from typing import Literal

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from modules.drive_client import DriveAuthRequiredError, build_reauth_url
from modules.rate_limit_notify import format_reset_countdown

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
        f"Open this link to sign in again:\n\n{url}\n\n"
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


def is_rate_limit(exc: BaseException) -> bool:
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

    if is_rate_limit(exc):
        msg = _rate_limit_message(context)
        if context in ("groq", "gemini"):
            msg += f"\n\nResets in {format_reset_countdown()} (midnight Pacific)."
        return msg

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
````

## File: pyproject.toml
````toml
[project]
name = "python-template"
version = "0.1.0"
description = ""
authors = ["Nadra <qamaria.mdsah@gmail.com>"]
requires-python = ">=3.11"
dependencies = [
    "openai>=1.82.0",
    "requests>=2.32.3",
    "telegram>=0.0.1",
]
````

## File: .dockerignore
````
venv/
.env
token.json
service_account_key.json
__pycache__/
.git/
README.md
````

## File: .gitignore
````
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
#  Usually these files are written by a python script from a template
#  before PyInstaller builds the exe, so as to inject date/other infos into it.
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
#   For a library or package, you might want to ignore these files since the code is
#   intended to run in multiple environments; otherwise, check them in:
# .python-version

# pipenv
#   According to pypa/pipenv#598, it is recommended to include Pipfile.lock in version control.
#   However, in case of collaboration, if having platform-specific dependencies or dependencies
#   having no cross-platform support, pipenv may install dependencies that don't work, or not
#   install all needed dependencies.
#Pipfile.lock

# poetry
#   Similar to Pipfile.lock, it is generally recommended to include poetry.lock in version control.
#   This is especially recommended for binary packages to ensure reproducibility, and is more
#   commonly ignored for libraries.
#   https://python-poetry.org/docs/basic-usage/#commit-your-poetrylock-file-to-version-control
#poetry.lock

# pdm
#   Similar to Pipfile.lock, it is generally recommended to include pdm.lock in version control.
#pdm.lock
#   pdm stores project-wide configurations in .pdm.toml, but it is recommended to not include it
#   in version control.
#   https://pdm.fming.dev/#use-with-ide
.pdm.toml

# PEP 582; used by e.g. github.com/David-OConnor/pyflow and github.com/pdm-project/pdm
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# SageMath parsed files
*.sage.py

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# PyCharm
#  JetBrains specific template is maintained in a separate JetBrains.gitignore that can
#  be found at https://github.com/github/gitignore/blob/main/Global/JetBrains.gitignore
#  and can be added to the global gitignore or merged into this file.  For a more nuclear
#  option (not recommended) you can uncomment the following to ignore the entire idea folder.
#.idea/

service_account_key.json
token.json
credentials.json
````

## File: fly.toml
````toml
# fly.toml app configuration file generated for qamar-bot on 2026-05-26T00:14:41+02:00
#
# See https://fly.io/docs/reference/configuration/ for information about how to use this file.
#

app = 'qamar-bot'
primary_region = 'sin'

[build]

[processes]
  app = 'python main.py'

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = 'stop'
  auto_start_machines = true
  min_machines_running = 1
  processes = ['app']

[[vm]]
  memory = '1gb'
  cpu_kind = 'shared'
  cpus = 1
  memory_mb = 1024
````

## File: brain/tags.txt
````
aiml
bot
coding
democracy
diversitycommunity
genai
governance
politicaltheory
project
rousseau
````

## File: README.md
````markdown
# Qamar

A personal Telegram bot that captures ideas when you're away from your laptop — voice notes in, organised notes out.

## Why

I think better out loud, especially when ideas hit and I don't have Obsidian handy. Qamar lets me send a quick voice message from my phone and turns it into a structured note in my vault, so nothing gets lost between walks, commutes, and late-night brain dumps.

## What it does

Qamar receives voice messages on Telegram, transcribes them, and turns spoken ideas into structured markdown notes in your Obsidian vault (via Google Drive). Tags stay in sync so the LLM can reuse your existing vocabulary when drafting new notes.

**Stack:** Python, Telegram, Groq (transcription), Gemini (notes), Google Drive OAuth (vault sync).

## Features

### Voice → note

- Send a **voice message**; Qamar transcribes it with **Groq Whisper** (`whisper-large-v3`).
- Say **"new idea"** in the recording to trigger note creation. Without that phrase, the bot replies `No new idea.` and does not write a file.
- **Gemini** (`gemini-2.5-flash`) drafts the note from `brain/template.md` (title, tags, maturity, references) and your system prompt in `brain/qamar_role.txt`.
- New notes are uploaded to your configured **Google Drive folder** (`GOOGLE_DRIVE_FOLDER_ID`), which syncs to Obsidian. The filename is derived from the note’s `# Title` heading.
- Timestamps in prompts use **`QAMAR_TIMEZONE`** (default `Europe/Berlin`).

### Tags

- Known tags live in **`brain/tags.txt`**. When creating a note, Gemini is told to prefer existing tags and only add new `[[tag]]` entries when needed (lowercase, up to 5).
- After a successful save, any **new tags** from the note are appended to `tags.txt`.

### Telegram commands

| Command | What it does |
|---------|----------------|
| `/start` | Intro and quick help |
| `/reauth` | Link to reconnect Google Drive when OAuth expires |
| `/delete` | Find the **most recent** `.md` in your vault folder, show its **name** and **created** date/time, and ask for confirmation via inline buttons |

### Delete flow

- **Yes, delete** — removes the file from Drive, then scans other vault notes; any tag that existed **only** on the deleted note is removed from `tags.txt`.
- **Cancel** — aborts without deleting.
- Debug logs record when a delete is requested, confirmed, or rejected.

### Groq / Gemini rate limits

- If **Groq** or **Gemini** hits a daily rate limit, the bot replies with the usual message plus **how long until midnight Pacific** when limits reset (e.g. `Resets in 9h 42m (midnight Pacific).`).
- If you were limited that Pacific calendar day, Qamar sends a **midnight Pacific** DM when the day rolls over: limits have reset and you can send voice notes again.
- Flags are stored in `brain/rate_limit_notify.json` (same persistence caveats as `tags.txt` on Fly).

### Google Drive auth

- A small **OAuth web app** (FastAPI on port `8080`) handles Drive login and token refresh. If auth fails during upload or delete, Qamar replies with a reconnect URL (same flow as `/reauth`).

### Google Drive setup (Web OAuth)

1. In [Google Cloud Console](https://console.cloud.google.com/): enable **Google Drive API**.
2. **Credentials → OAuth client ID → Web application**.
3. **Authorized redirect URIs** (must match exactly):
   - Local: `http://localhost:8080/oauth/callback`
   - Fly: `https://qamar-bot.fly.dev/oauth/callback`
4. Download JSON as `credentials.json` in the project root.
5. In `.env`: set `GOOGLE_DRIVE_FOLDER_ID`, `OAUTH_LINK_SECRET` (random string), `BASE_URL`, `OAUTH_REDIRECT_URI`.
6. Run `python main.py`, then open the URL from `python -m modules.authorize_drive` (or send `/reauth` in Telegram).

When Drive auth expires, the bot replies with a reconnect link or use `/reauth`.

**Fly secrets:** set `BASE_URL`, `OAUTH_REDIRECT_URI`, `OAUTH_LINK_SECRET`, and after first auth set the Drive token from file (avoids broken escaping):

```bash
fly secrets set GOOGLE_OAUTH_TOKEN_JSON=@token.json -a qamar-bot
```

Use a single `{` at the start of the JSON — `{{...}}` will break parsing. Re-run `/reauth` on Fly if uploads still fail after updating the secret.

## On the horizon

- RAG over existing Obsidian notes to help ideate on new projects (problem statements, SWOT, stack-aware suggestions for Python, TypeScript, Go, SQL)
- Sync exisiting tags in Obsidian to  tags in `tags.txt` so Qamar is always aware of tags that may be manually added or deleted
````

## File: requirements.txt
````
annotated-types==0.7.0
anyio==4.13.0
beautifulsoup4==4.14.3
certifi==2026.5.20
cffi==2.0.0
charset-normalizer==3.4.7
click==8.4.1
colorama==0.4.6
cryptography==48.0.0
distro==1.9.0
fastapi==0.115.12
google==3.0.0
google-api-core==2.30.3
google-api-python-client==2.196.0
google-auth==2.53.0
google-auth-httplib2==0.4.0
google-auth-oauthlib==1.3.0
google-genai==2.6.0
googleapis-common-protos==1.75.0
groq==1.2.0
h11==0.16.0
httpcore==1.0.9
httplib2==0.31.2
httpx==0.28.1
idna==3.16
oauth2client==4.1.3
oauthlib==3.3.1
proto-plus==1.28.0
protobuf==7.35.0
pyasn1==0.6.3
pyasn1_modules==0.4.2
pycparser==3.0
pydantic==2.13.4
pydantic_core==2.46.4
pyparsing==3.3.2
python-dotenv==1.2.2
python-telegram-bot[job-queue]==22.7
requests==2.34.2
requests-oauthlib==2.0.0
rsa==4.9.1
six==1.17.0
sniffio==1.3.1
soupsieve==2.8.4
starlette==0.46.2
telegram==0.0.1
tenacity==9.1.4
typing-inspection==0.4.2
typing_extensions==4.15.0
tzdata==2026.2
uritemplate==4.2.0
urllib3==2.7.0
uvicorn==0.34.2
websockets==16.0
````

## File: main.py
````python
# System
import os
import re
import datetime
import tempfile
import threading
import random
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
TZ = ZoneInfo(os.getenv("QAMAR_TIMEZONE", "Europe/Berlin"))

import uvicorn
from dotenv import load_dotenv

load_dotenv()

# APIs
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from google import genai
from google.genai import types
from groq import Groq
from modules.drive_client import (
    delete_note_by_id,
    download_note_content,
    get_drive_service,
    get_most_recent_note,
    list_vault_notes,
    save_note_to_drive,
)
from modules.oauth_app import app as fastapi_app
from modules.rate_limit_notify import PACIFIC, mark_rate_limited, send_midnight_reset_notifications
from modules.user_errors import drive_reauth_message, format_user_error, is_rate_limit

now = datetime.datetime.now()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HTTP_PORT = int(os.getenv("PORT", "8080"))
# Gemini for text reply generation
gemini_client = genai.Client(api_key=os.getenv("GOOGLE_GEMINI_API"))
gemini_model = "gemini-2.5-flash"
# Groq Whisper for transcription of audio files
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
groq_model = "whisper-large-v3"

# Resources
with open("brain/qamar_role.txt", "r") as f:
    qamar_system_prompt = f.read()
with open("brain/template.md", "r") as f:
    note_template = f.read()

TAGS_FILE = "brain/tags.txt"

DELETE_CONFIRM = "delete_confirm"
DELETE_CANCEL = "delete_cancel"


#####################################################################################################################################################################


def load_tags() -> list[str]:
    if not os.path.exists(TAGS_FILE):
        return []
    with open(TAGS_FILE, encoding="utf-8") as f:
        tags = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"\[\[(.+?)\]\]", line)
            tag = (match.group(1) if match else line).strip().lower()
            if tag:
                tags.append(tag)
        return sorted(set(tags))


def format_tags_for_prompt(tags: list[str]) -> str:
    if not tags:
        return "(none yet — create new tags only if needed)"
    return ", ".join(f"[[{tag}]]" for tag in tags)


def extract_tags_from_markdown(markdown: str) -> list[str]:
    return sorted({t.strip().lower() for t in re.findall(r"\[\[([^\]]+)\]\]", markdown) if t.strip()})


def append_new_tags(used_tags: list[str]) -> list[str]:
    existing = set(load_tags())
    new_tags = sorted({t.lower().strip() for t in used_tags if t.lower().strip()} - existing)
    if not new_tags:
        return []
    with open(TAGS_FILE, "a" if existing else "w", encoding="utf-8") as f:
        for tag in new_tags:
            f.write(f"{tag}\n")
    return new_tags


def collect_tags_in_vault(drive_service, exclude_id: str | None = None) -> set[str]:
    tags: set[str] = set()
    for note in list_vault_notes(drive_service):
        if exclude_id and note["id"] == exclude_id:
            continue
        content = download_note_content(drive_service, note["id"])
        tags.update(extract_tags_from_markdown(content))
    return tags


def prune_orphan_tags(deleted_file_tags: list[str], tags_still_in_vault: set[str]) -> list[str]:
    """Remove from tags.txt any tag that was only on the deleted note."""
    still_used = {t.lower() for t in tags_still_in_vault}
    orphan_candidates = {t.lower() for t in deleted_file_tags} - still_used
    if not orphan_candidates:
        return []
    current = load_tags()
    removed = sorted(t for t in current if t in orphan_candidates)
    if not removed:
        return []
    with open(TAGS_FILE, "w", encoding="utf-8") as f:
        for tag in current:
            if tag not in orphan_candidates:
                f.write(f"{tag}\n")
    return removed


# Ensure file name saved in Drive is of the correct format and causes no conflict
def note_filename_from_markdown(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = match.group(1).strip() if match else "new idea"
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = re.sub(r"[-]+", "", safe)
    safe = re.sub(r"\s+", " ", safe).strip()[:100] or "new idea"
    return f"{safe}.md"


# Prompt user to reauth Google Drive access
def format_drive_created_time(created_time_rfc3339: str) -> str:
    dt = datetime.datetime.fromisoformat(created_time_rfc3339.replace("Z", "+00:00"))
    return dt.astimezone(TZ).strftime("%d-%m-%Y %H:%M")



# Fetch a single note's content and extract its tags
def fetch_single_note_metadata(drive_service, note: dict) -> dict | None:
    try:
        content = download_note_content(drive_service, note["id"])
        tags = extract_tags_from_markdown(content)
        return {
            "id": note["id"],
            "name": note["name"],
            "createdTime": note.get("createdTime", ""),
            "content": content,
            "tags": tags
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch content for note {note.get('name')}: {e}")
        return None



# Download note contents (in parallel to avoid slow sequential APIs)
def get_all_vault_notes_concurrently(drive_service) -> list[dict]:
    all_notes = list_vault_notes(drive_service)
    # 10 worker heads -> pull note metadata very fast
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda n: fetch_single_note_metadata(drive_service, n), all_notes))
    return [r for r in results if r is not None]



def run_http_server():
    uvicorn.run(
        fastapi_app,
        host="0.0.0.0",
        port=HTTP_PORT,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


#####################################################################################################################################################################


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! I'm Qamar. I help organise your brain dumps in Obsidian. Tell me your idea in a voice note and I'll remember that for you.\n\n"
        "Use /reauth if Google Drive needs reconnecting.\n"
        "Use /delete to remove your most recently saved note (you'll be asked to confirm)."
    )


# /reauth
async def reauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(drive_reauth_message())


# /delete
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Select most recent note
        note = get_most_recent_note(get_drive_service())
        # If no notes at all
        if note is None:
            await update.message.reply_text("No notes found in Drive to delete.")
            return
        # Get note information
        context.user_data["pending_delete_id"] = note["id"]
        context.user_data["pending_delete_name"] = note["name"]
        created = format_drive_created_time(note["createdTime"])
        # Button UI on Telegram: Yes, delete / Cancel
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Yes, delete", callback_data=DELETE_CONFIRM),
                    InlineKeyboardButton("Cancel", callback_data=DELETE_CANCEL),
                ]
            ]
        )
        print(f"[DEBUG {now}] Delete requested for: {note['name']} (created {created}) — awaiting confirmation")
        await update.message.reply_text(
            f"Most recent note:\n"
            f"Name: {note['name']}\n"
            f"Created: {created}\n\n"
            "Delete this file from Drive?",
            reply_markup=keyboard,
        )
    except Exception as e:
        print(f"[ERROR {now}] Drive lookup failed: {e}")
        await update.message.reply_text(format_user_error(e, context="drive_lookup"))


# Deleting process
async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == DELETE_CANCEL:
        file_name = context.user_data.pop("pending_delete_name", None)
        context.user_data.pop("pending_delete_id", None)
        print(f"[DEBUG {now}] Delete rejected: {file_name or 'unknown'}")
        await query.edit_message_text("Delete cancelled.")
        return

    if query.data != DELETE_CONFIRM:
        return

    file_id = context.user_data.pop("pending_delete_id", None)
    file_name = context.user_data.pop("pending_delete_name", None)
    if not file_id:
        await query.edit_message_text("This confirmation expired. Run /delete again.")
        return

    print(f"[DEBUG {now}] Delete confirmed: {file_name or file_id}")
    try:
        drive = get_drive_service()
        deleted_content = download_note_content(drive, file_id)                     # Read content of file to be deleted
        deleted_tags = extract_tags_from_markdown(deleted_content)                  # Get the tags in the file
        tags_in_other_notes = collect_tags_in_vault(drive, exclude_id=file_id)      # Look at other tags in the vault
        removed_tags = prune_orphan_tags(deleted_tags, tags_in_other_notes)         # Delete tags that are only attached to the file to be deleted
        deleted_name = delete_note_by_id(drive, file_id)                            # Confirm deletion

        reply_text = f"Deleted from Drive: {deleted_name}"
        if removed_tags:
            reply_text += f"\nRemoved unused tags: {', '.join(removed_tags)}"
            print(f"[DEBUG {now}] Tags removed from {TAGS_FILE}: {', '.join(removed_tags)}")
        await query.edit_message_text(reply_text)
    except Exception as e:
        print(f"[ERROR {now}] Drive delete failed: {e}")
        await query.edit_message_text(format_user_error(e, context="drive_delete"))



# /draft: convert a note to an IG carousel post
async def draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Book Review", callback_data="draft_type:book"),
                InlineKeyboardButton("Burning Thought", callback_data="draft_type:thought"),
            ],
            [
                InlineKeyboardButton("Cancel", callback_data="draft_cancel")
            ]
        ]
    )
    await update.message.reply_text(
        "what type of ig carousel post are we drafting?",
        reply_markup=keyboard
    )



# /draft process after selecting postt ype/note refresh
async def draft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # if user cancels
    if data == "draft_cancel":
        context.user_data.pop("draft_state", None)
        context.user_data.pop("suggested_notes", None)
        context.user_data.pop("draft_post_type", None)
        await query.edit_message_text("drafting cancelled")
        return
    
    # if user chose "book" or "thought" (refreshed)
    if data.startswith("draft_type:") or data.startswith("draft_refresh:"):
        post_type = data.split(":")[1]          # "book" or "thought"

        await query.edit_message_text("scanning vault and picking 3 random notes ... gimme a sec")

        try:
            drive_service = get_drive_service()
            all_notes = get_all_vault_notes_concurrently(drive_service)

            # only get ntoes with [[book]] tag
            matching_notes = []
            for note in all_notes:
                is_book = "book" in note["tags"]
                if (post_type == "book" and is_book) or (post_type == "thought" and not is_book):
                    matching_notes.append(note)

            if not matching_notes:
                await query.edit_message_text(
                    f"no notes found matching the '{'book' if post_type == 'book' else 'burning thought'}' type"
                )
                return

            # show 3 random  notes
            chosen_sample = random.sample(matching_notes, min(3, len(matching_notes)))
            # sort notes in descending order by creation date (latest first)
            chosen_sample.sort(key=lambda x: x["createdTime"], reverse=True)

            # store selection in user context state
            context.user_data["suggested_notes"] = chosen_sample
            context.user_data["draft_post_type"] = post_type
            context.user_data["draft_state"] = "awaiting_selection"

            # Format output message
            post_label = "book review" if post_type == "book" else "burning thought"
            msg_text = f"here are 3 random {post_label} suggestions, sorted latest first:\n\n"

            for idx, note in enumerate(chosen_sample, start=1):
                created = format_drive_created_time(note["createdTime"])
                msg_text += f"{idx}. {note['name']} (created: {created})\n"

            msg_text += "\nuse the buttons below to act."

            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Refresh suggestions", callback_data=f"draft_refresh:{post_type}")],
                    [InlineKeyboardButton("Cancel", callback_data="draft_cancel")],
                ]
            )

            await query.edit_message_text(msg_text, reply_markup=keyboard)

        except Exception as e:
            print(f"[ERROR] Note categorisation failed: {e}")
            await query.edit_message_text(format_user_error(e, context="drive_lookup"))



async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captures manual numerical replies when choosing a note."""
    state = context.user_data.get("draft_state")
    if state == "awaiting_selection":
        text = update.message.text.strip()
        if text in ("1", "2", "3"):
            idx = int(text) - 1
            suggested = context.user_data.get("suggested_notes", [])
            
            if idx < len(suggested):
                selected_note = suggested[idx]
                post_type = context.user_data.get("draft_post_type")

                # Clear state immediately so subsequent texts aren't captured
                context.user_data.pop("draft_state", None)
                context.user_data.pop("suggested_notes", None)
                context.user_data.pop("draft_post_type", None)

                await generate_carousel_draft(update, context, selected_note, post_type)
            else:
                await update.message.reply_text("invalid selection. that option isn't on the list.")
        else:
            await update.message.reply_text("type 1, 2, or 3 to pick a note. or cancel using the inline buttons.")



async def generate_carousel_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_note: dict, post_type: str):
    # Generates and splits the lowercase carousel draft using Gemini.
    await update.message.reply_text(f"drafting slides for '{selected_note['name']}'... ✍️")

    try:
        # Prompt setups tailored to the post type
        if post_type == "book":
            framework = (
                "Format of the book review slides:\n"
                "Slide 1: <book title> by <author>\n"
                "Slide 2: Summary of the book in my own words (rely on content within the note)\n"
                "Slide 3: Opinion and feelings about the book\n"
                "Slide 4: Would I read it again?\n"
            )
        else:
            framework = (
                "Format of the burning thought slides:\n"
                "Slide 1: Hook\n"
                "Slide 2: Inspiration or context on how this thought came to be\n"
                "Slide 3: Explain the thought clearly in simple, casual terms\n"
                "Slide 4: Next course of action while knowing this thought\n"
                "Slide 5: Close with an ambiguous statement to provoke thinking\n"
            )

        instructions = (
            f"{framework}\n"
            "CRITICAL CONSTRAINTS:\n"
            "- Write EVERYTHING in lowercase. Absolutely do not use uppercase letters at all.\n"
            "- Write exactly in the speaking/writing style of the note itself (casual, easygoing, nonchalant, authentic).\n"
            "- Do not use ANY text formatting. No asterisks (*), no bold, no headers.\n"
            "- Do not include headers, slide numbers, or slide labels (e.g., do not output 'slide 1:' or 'hook:'). Only write the pure content of each slide.\n"
            "- Separate each slide's content using a line with exactly three hyphens: '---'."
        )

        full_system_prompt = qamar_system_prompt + "\n\n" + instructions

        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=(
                f"Here is the Obsidian note content:\n\n{selected_note['content']}\n\n"
                "Draft the carousel slides now following the layout and constraints perfectly."
            ),
            config=types.GenerateContentConfig(system_instruction=full_system_prompt),
        )

        output = response.text
        # Split slides by the '---' separator
        slides = [slide.strip() for slide in output.split("---") if slide.strip()]

        if not slides:
            await update.message.reply_text("could not generate any slides. try again.")
            return

        # Send each slide as a standalone Telegram message
        for slide in slides:
            await update.message.reply_text(slide)

    except Exception as e:
        print(f"[ERROR] Carousel generation failed: {e}")
        if is_rate_limit(e) and update.effective_user:
            mark_rate_limited(update.effective_user.id, "gemini")
        await update.message.reply_text(format_user_error(e, context="gemini"))

        





# WHEN USER SENDS A VOICE MESSAGE
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tmp_path: str | None = None
    reply_text: str
    new_note: str | None = None
    transcript_text: str | None = None

    try:
        file = await context.bot.get_file(update.message.voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
            await file.download_to_drive(custom_path=tmp_path)
            tmp.flush()

        try:
            with open(tmp_path, "rb") as audio_file:
                transcript = groq_client.audio.transcriptions.create(
                    file=audio_file,
                    model=groq_model,
                    prompt="Specify context or spelling",
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"],
                    language="en",
                    temperature=0.0,
                )
        except Exception as e:
            print(f"[ERROR {now}] Groq transcription failed: {e}")
            if is_rate_limit(e) and update.effective_user:
                mark_rate_limited(update.effective_user.id, "groq")
            await update.message.reply_text(format_user_error(e, context="groq"))
            return

        transcript_text = transcript.text

        if "new idea" in transcript_text.lower():
            existing_tags = load_tags()
            try:
                response = gemini_client.models.generate_content(
                    model=gemini_model,
                    contents=(
                        "Don't reply to the user. Produce only content in a markdown file that contains the new idea shared by the user. Refine the idea while reusing the user's words in the markdown.\n"
                        f"This is the markdown file template that you must strictly follow: {note_template}\n"
                        "Tag rules:\n"
                        f"- Existing tags in the vault (reuse the most appropriate ones first, but create new ones only if needed): "
                        f"{format_tags_for_prompt(existing_tags)}\n"
                        "- Always write tags as [[tag]], one word each, all lowercase, up to 5 tags.\n"
                        "- Prefer existing tags whenever they fit; only invent a new tag if none apply.\n"
                        "- For Maturity, always set it as #baby with the hashtag symbol, also in lowercase.\n"
                        "- Don't add commas between each tag. Just use space to tell them apart.\n"
                        "This is the end of the template. "
                        f"Right now the date and time are {datetime.datetime.now(TZ):%d-%m-%Y %H:%M}. This is the user's idea: {transcript_text}"
                    ),
                    config=types.GenerateContentConfig(system_instruction=qamar_system_prompt),
                )
            except Exception as e:
                print(f"[ERROR {now}] Gemini note generation failed: {e}")
                if is_rate_limit(e) and update.effective_user:
                    mark_rate_limited(update.effective_user.id, "gemini")
                await update.message.reply_text(format_user_error(e, context="gemini"))
                return

            new_note = response.text
            new_tags = append_new_tags(extract_tags_from_markdown(new_note))
            if new_tags:
                print(f"[DEBUG {now}] New tags added to {TAGS_FILE}: {', '.join(new_tags)}")
            try:
                filename = note_filename_from_markdown(new_note)
                saved_name = save_note_to_drive(get_drive_service(), new_note, filename)
                reply_text = f"New note saved to Drive: {saved_name}"
            except Exception as e:
                print(f"[ERROR {now}] Drive upload failed: {e}")
                reply_text = format_user_error(e, context="drive_upload")
        else:
            reply_text = "No new idea."

        print(f"[DEBUG {now}] User's voice input: {transcript_text}")
        if new_note:
            print(f"\n[DEBUG {now}] New MD file:\n{new_note}\n")
        print(f"[DEBUG {now}] AI message output: {reply_text}")
        await update.message.reply_text(reply_text)

    except Exception as e:
        print(f"[ERROR {now}] Voice handler failed: {e}")
        await update.message.reply_text(format_user_error(e, context="groq"))

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


#####################################################################################################################################################################


async def midnight_rate_limit_job(context: ContextTypes.DEFAULT_TYPE):
    await send_midnight_reset_notifications(context.bot)



async def debug_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary debug handler that prints any button click to the console."""
    query = update.callback_query
    # Acknowledge the click immediately so the loading spinner stops
    await query.answer()
    
    # Print the exact incoming data to your terminal/logs
    print(f"\n[DEBUG] A button was pressed!")
    print(f"-> Callback Data received: '{query.data}'")
    print(f"-> User who clicked: {update.effective_user.username} (ID: {update.effective_user.id})\n")
    
    # Send a quick text back to the user to confirm it works
    await query.message.reply_text(f"debug: caught button press with data -> {query.data}")





if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    if app.job_queue is None:
        print("[WARN] JobQueue unavailable — install python-telegram-bot[job-queue]")
    else:
        app.job_queue.run_daily(
            midnight_rate_limit_job,
            time=datetime.time(0, 0, tzinfo=PACIFIC),
            name="pacific_midnight_rate_limit_reset",
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reauth", reauth))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("draft", draft))
    
    # Handles delete confirmation/cancellation buttons
    app.add_handler(
        CallbackQueryHandler(delete_callback, pattern=f"^({DELETE_CONFIRM}|{DELETE_CANCEL})$")
    )
    
    # Handles the /draft post type selection, refresh, and cancel buttons
    app.add_handler(
        CallbackQueryHandler(
            draft_callback, 
            pattern=r"^(draft_type:|draft_refresh:|draft_cancel)"
        )
    )
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Handles text inputs (1, 2, or 3) for choosing suggested notes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print(f"Qamar is live (OAuth server on port {HTTP_PORT}).")
    app.run_polling()
````
