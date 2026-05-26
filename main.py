# System
import os
import re
import datetime
import tempfile
import threading
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
from drive_client import (
    delete_note_by_id,
    download_note_content,
    get_drive_service,
    get_most_recent_note,
    list_vault_notes,
    save_note_to_drive,
)
from oauth_app import app as fastapi_app
from user_errors import drive_reauth_message, format_user_error

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
                        "This is the end of the template. "
                        f"Right now the date and time are {datetime.datetime.now(TZ):%d-%m-%Y %H:%M}. This is the user's idea: {transcript_text}"
                    ),
                    config=types.GenerateContentConfig(system_instruction=qamar_system_prompt),
                )
            except Exception as e:
                print(f"[ERROR {now}] Gemini note generation failed: {e}")
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


if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reauth", reauth))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(
        CallbackQueryHandler(delete_callback, pattern=f"^({DELETE_CONFIRM}|{DELETE_CANCEL})$")
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print(f"Qamar is live (OAuth server on port {HTTP_PORT}).")
    app.run_polling()
