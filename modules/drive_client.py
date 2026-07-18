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
