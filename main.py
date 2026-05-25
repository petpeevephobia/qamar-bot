import os
import json
import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import tempfile
from google import genai
from google.genai import types
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

now = datetime.datetime.now()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

gemini_client = genai.Client(api_key=os.getenv("GOOGLE_GEMINI_API"))
gemini_model = "gemini-2.5-flash"

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
groq_model = "whisper-large-v3"

# Load Qamar's role from qamar_role.txt
with open("brain/qamar_role.txt", "r") as f:
    qamar_system_prompt = f.read()
# Load Full Note  template from template.md
with open("brain/template.md", "r") as f:
    note_template = f.read()


#####################################################################################################################################################################

# Take new_note and save it to Google Drive

#####################################################################################################################################################################


# /start COMMAND
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! I'm Qamar. I help organise your brain dumps in Obsidian. Tell me your idea in a voice note and I'll remember that for you."
    )



# HANDLE VOICE MESSAGES
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.voice.file_id)

    # Download user's voice message
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(custom_path=tmp.name)
        tmp.flush()

    # AI listens to user voice message
    with open(tmp.name, "rb") as audio_file:
        # Create a transcription of the audio file
        # To print only the transcription text, you'd use print(transcription.text)
        transcript = groq_client.audio.transcriptions.create(
            file=audio_file,                                                                                # Required audio file
            model=groq_model,                                                                               # Required model to use for transcription
            prompt="Specify context or spelling",                                                           # Optional
            response_format="verbose_json",                                                                 # Optional
            timestamp_granularities = ["word", "segment"],                                                  # Optional (must set response_format to "json" to use and can specify "word", "segment" (default), or both)
            language="en",                                                                                  # Optional
            temperature=0.0                                                                                 # Optional
            )


    # Check for trigger phrase "new idea", and produce MD file
    if "new idea" in transcript.text.lower():

        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=f"Don't reply to the user. Produce only content in a markdown file that contains the new idea shared by the user. Refine the idea where possible. Reuse as much of the user's words as possible in the markdown.\
            \nThis is the markdown file template that you must strictly follow. For Tags, always write it as '[[tag]]' and it only is one word. Add up to 5 tags.: {note_template}\
            \nThis is the end of the template. Right now the date and time are {now}. This is the user's idea: {transcript.text}",
            config=types.GenerateContentConfig(
                system_instruction=qamar_system_prompt
            )
        )

        new_note = response.text
        reply_text = "New note created in Obsidian."

    # If no trigger phrase, do nothing
    else:
        # response = gemini_client.models.generate_content(
        #     model=gemini_model,
        #     contents=f"Respond to this: {transcript.text}",
        #     config=types.GenerateContentConfig(
        #         system_instruction=qamar_system_prompt
        #     )
        # )
        # reply_text = response.text
        reply_text = "No new idea."
    # Delete user's audio file
    os.remove(tmp.name)



    print(f"[DEBUG {now}] User's voice input: {transcript.text}")
    print(f"\n[DEBUG {now}] New MD file:\n{new_note}\n")
    print(f"[DEBUG {now}] AI message output: {reply_text}")
    # Send text as a reply
    await update.message.reply_text(reply_text)


#####################################################################################################################################################################


if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Qamar is live.")
    app.run_polling()