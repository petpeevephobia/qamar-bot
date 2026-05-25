"""FastAPI routes for Google Drive web OAuth (Fly.io + local)."""



import os



from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request

from fastapi.responses import HTMLResponse, RedirectResponse



from google_auth_oauthlib.flow import Flow



from drive_client import (

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


