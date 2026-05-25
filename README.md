# Qamar

A personal Telegram bot that captures ideas when you're away from your laptop — voice notes in, organised notes out.

## Why

I think better out loud, especially when ideas hit and I don't have Obsidian handy. Qamar lets me send a quick voice message from my phone and turns it into a structured note in my vault, so nothing gets lost between walks, commutes, and late-night brain dumps.

## What it does

Qamar receives voice messages, transcribes them, and uses an LLM to shape the content for your note template: title, tags, and maturity (`baby` / `teen` / `adult`, defaulting to baby). Notes land in the **6 - Full Notes** folder in Obsidian; tags keep everything searchable.

Today the bot runs on Telegram with voice transcription and conversational replies. Obsidian note creation and the full templating flow are the core workflow being built toward.

**Stack:** Python, Telegram, Groq (transcription), Gemini (notes), Google Drive OAuth (vault sync).

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
