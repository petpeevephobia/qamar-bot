# System
import os
import re
import datetime
import tempfile
import threading

import uvicorn
from dotenv import load_dotenv

load_dotenv()

# APIs
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types
from groq import Groq
from googleapiclient.errors import HttpError

from drive_client import DriveAuthRequiredError, build_reauth_url, get_drive_service, save_note_to_drive
from oauth_app import app as fastapi_app

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


#####################################################################################################################################################################


# Ensure file name saved in Drive is of the correct format and causes no conflict
def note_filename_from_markdown(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = match.group(1).strip() if match else "new idea"
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = re.sub(r"[-]+", "", safe)
    safe = re.sub(r"\s+", " ", safe).strip()[:100] or "new idea"
    return f"{safe}.md"


# Prompt user to reauth Google Drive access
def drive_auth_reply() -> str:
    try:
        url = build_reauth_url()
    except ValueError:
        return "Drive login expired. Set OAUTH_LINK_SECRET in .env and restart the bot."
    return f"Drive login expired. Reconnect here:\n{url}"


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
        "Use /reauth if Google Drive needs reconnecting."
    )


# /reauth
async def reauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = build_reauth_url()
    except ValueError:
        await update.message.reply_text(
            "OAUTH_LINK_SECRET is not configured. Add it to .env and restart the bot."
        )
        return
    await update.message.reply_text(f"Reconnect Google Drive:\n{url}")


# WHEN USER SENDS A VOICE MESSAGE
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.voice.file_id)

    # Download the audio file
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(custom_path=tmp.name)
        tmp.flush()

    # Groq transcribes user's audio file
    with open(tmp.name, "rb") as audio_file:
        transcript = groq_client.audio.transcriptions.create(
            file=audio_file,
            model=groq_model,
            prompt="Specify context or spelling",
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            language="en",
            temperature=0.0,
        )

    # Generate MD file
    if "new idea" in transcript.text.lower():
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=(
                "Don't reply to the user. Produce only content in a markdown file that contains "
                "the new idea shared by the user. Refine the idea where possible. Reuse as much of "
                "the user's words as possible in the markdown.\n"
                f"This is the markdown file template that you must strictly follow. For Tags, "
                "always write it as '[[tag]]' and it's only one word, all in lowercase. Add up to "
                f"5 tags. For Maturity, always set it as #baby with the hashtag symbol, also in "
                f"lowercase.: {note_template}\n"
                "This is the end of the template. "
                f"Right now the date and time are {now}. This is the user's idea: {transcript.text}"
            ),
            config=types.GenerateContentConfig(system_instruction=qamar_system_prompt),
        )

        new_note = response.text
        try:
            filename = note_filename_from_markdown(new_note)
            saved_name = save_note_to_drive(get_drive_service(), new_note, filename)
            reply_text = f"New note saved to Drive: {saved_name}"
        except DriveAuthRequiredError:
            reply_text = drive_auth_reply()
        except (HttpError, ValueError) as e:
            print(f"[ERROR {now}] Drive upload failed: {e}")
            reply_text = "New idea captured, but saving to Drive failed. Check the bot logs."
    
    
    # If user's input does NOT contain "new idea" (trigger)
    else:
        reply_text = "No new idea."
        new_note = None

    os.remove(tmp.name)

    print(f"[DEBUG {now}] User's voice input: {transcript.text}")
    if new_note:
        print(f"\n[DEBUG {now}] New MD file:\n{new_note}\n")
    print(f"[DEBUG {now}] AI message output: {reply_text}")
    
    await update.message.reply_text(reply_text)


#####################################################################################################################################################################


if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reauth", reauth))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print(f"Qamar is live (OAuth server on port {HTTP_PORT}).")
    app.run_polling()
