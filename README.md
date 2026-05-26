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
6. Run `python main.py`, then open the URL from `python authorize_drive.py` (or send `/reauth` in Telegram).

When Drive auth expires, the bot replies with a reconnect link or use `/reauth`.

**Fly secrets:** set `BASE_URL`, `OAUTH_REDIRECT_URI`, `OAUTH_LINK_SECRET`, and optionally `GOOGLE_OAUTH_TOKEN_JSON` after first auth.

## On the horizon

- RAG over existing Obsidian notes to help ideate on new projects (problem statements, SWOT, stack-aware suggestions for Python, TypeScript, Go, SQL)
- Error message to the user in quote for Gemini or Groq Whisper exceeds for the day
- Sync exisiting tags in Obsidian to  tags in `tags.txt` so Qamar is always aware of tags that may be manually added or deleted