# System
import os
import re
import datetime
import tempfile
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    save_notes_index,
    load_notes_index,
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
    results = []
    
    # Use ThreadPoolExecutor safely with explicit futures mapping
    with ThreadPoolExecutor(max_workers=5) as executor:  # Lower max_workers to 5 to prevent Drive API rate limits
        future_to_note = {
            executor.submit(fetch_single_note_metadata, drive_service, note): note 
            for note in all_notes
        }
        
        for future in as_completed(future_to_note):
            res = future.result()
            if res is not None:
                results.append(res)
                
    return results



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



# /draft process after selecting post type/note refresh
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
        post_type = data.split(":")[1]

        # 1. Load instantly from local cache file instead of fetching Drive API
        all_notes = load_notes_index()

        # DEBUG
        for n in all_notes:
            print(f"Note: '{n.get('name')}' | Tags: {n.get('tags')}")
        print("---------------------------------------------------\n")

        # If index is empty (e.g. initial run before syncing), perform fallback fetch and save
        if not all_notes:
            await query.edit_message_text("index file empty. scanning drive vault for first time...")
            drive_service = get_drive_service()
            all_notes = get_all_vault_notes_concurrently(drive_service)
            save_notes_index(all_notes)

        # 2. Filter using local tag metadata
        matching_notes = []
        for note in all_notes:
            is_book = "book" in note.get("tags", [])
            if (post_type == "book" and is_book) or (post_type == "thought" and not is_book):
                matching_notes.append(note)

        if not matching_notes:
            await query.edit_message_text(
                f"no notes found matching the '{'book' if post_type == 'book' else 'burning thought'}' type. try running /sync"
            )
            return

        # 3. Select 3 random and sort latest first
        chosen_sample = random.sample(matching_notes, min(3, len(matching_notes)))
        chosen_sample.sort(key=lambda x: x.get("createdTime", ""), reverse=True)

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

        # except Exception as e:
        #     print(f"[ERROR] Note categorisation failed: {e}")
        #     await query.edit_message_text(format_user_error(e, context="drive_lookup"))


# take user's number reply to draft post
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


# generate post draft with template
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
                "Slide 3: Most popular quotes from that book based on Goodreads.com\n"
                "Slide 4: Personal pinion and feelings about the book in my own words (rely on content within the note)\n"
                "Slide 5: Would I read it again?\n"
            )
        else:
            framework = (
                "Format of the burning thought slides:\n"
                "Slide 1: Irresistible one-liner hook\n"
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
            "- Write the content from a personal prnoun perspective, using 'I' and 'me'. Not 'you'. \n"
            "- Separate each slide's content using a line with exactly three hyphens: '---'."
        )

        full_system_prompt = qamar_system_prompt + "\n\n" + instructions

        drive_service = get_drive_service()
        full_content = download_note_content(drive_service, selected_note["id"])

        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=(
                f"Here is the Obsidian note content:\n\n{full_content}\n\n"
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


# /sync: cache obsidian notes
async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to trigger a manual scan of Google Drive and save local notes index."""
    msg = await update.message.reply_text("🔄 scanning google drive vault and updating index...")
    
    try:
        drive_service = get_drive_service()
        # Scan drive and extract tags
        all_notes = get_all_vault_notes_concurrently(drive_service)
        
        # Save to local brain/notes_index.json
        save_notes_index(all_notes)
        
        await msg.edit_text(f"✅ synced successfully! indexed **{len(all_notes)}** notes.", parse_mode="Markdown")
    except Exception as e:
        print(f"[ERROR] Sync failed: {e}")
        await msg.edit_text(f"❌ failed to sync notes: {e}")

        





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
    app.add_handler(CommandHandler("sync", sync))
    
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