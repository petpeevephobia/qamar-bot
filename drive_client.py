"""Google Drive uploads using OAuth user credentials (personal Drive quota)."""

import io
import json
import os
from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

load_dotenv()

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
GOOGLE_OAUTH_CLIENT_SECRETS = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "credentials.json")
GOOGLE_OAUTH_TOKEN = os.getenv("GOOGLE_OAUTH_TOKEN", "token.json")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")

_drive_service = None


class DriveAuthRequiredError(Exception):
    """Raised when Google Drive needs a new OAuth login."""

    def __init__(self, message: str | None = None):
        self.reauth_url = build_reauth_url()
        super().__init__(message or "Google Drive login required.")


def build_reauth_url() -> str:
    base = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
    secret = os.getenv("OAUTH_LINK_SECRET", "")
    if not secret:
        raise ValueError("OAUTH_LINK_SECRET must be set in .env")
    return f"{base}/oauth/start?secret={secret}"


def _load_token_data() -> dict | None:
    env_json = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    if env_json:
        return json.loads(env_json)
    if os.path.exists(GOOGLE_OAUTH_TOKEN):
        with open(GOOGLE_OAUTH_TOKEN, encoding="utf-8") as f:
            return json.load(f)
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
    token_data = _load_token_data()
    creds = None
    if token_data:
        creds = Credentials.from_authorized_user_info(token_data, DRIVE_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
            return creds
        except RefreshError as e:
            raise DriveAuthRequiredError(
                "Google Drive refresh token expired or revoked."
            ) from e

    raise DriveAuthRequiredError("No valid Google Drive token. Re-authorize to continue.")


def invalidate_drive_service() -> None:
    global _drive_service
    _drive_service = None


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        _drive_service = build("drive", "v3", credentials=get_drive_credentials())
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
