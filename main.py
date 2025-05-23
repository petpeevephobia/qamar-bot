import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import tempfile
from openai import OpenAI, Audio
import json





# Environment setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ORG_KEY = os.getenv("ORG_KEY")
client = OpenAI(api_key=OPENAI_API_KEY, organization=ORG_KEY)
# Set memory file
MEMORY_FILE = "memory.json"
# TTS Settings
voice = "echo"  # or "shimmer", "echo", etc.

# Load Qamar's role from separate file
with open("qamar_role.txt", "r") as f:
    qamar_system_prompt = f.read()
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}
def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)
# Load memory at runtime
qamar_memory = load_memory()

# Set web surfing
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
def web_search(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": 3
    }
    response = requests.get(url, params=params)
    data = response.json()

    snippets = []
    if "items" in data:
        for item in data["items"]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            snippets.append(f"- {title}\n  {snippet}\n  {link}")
    else:
        snippets.append("No relevant web results found.")

    return "\n".join(snippets)




















# /start COMMAND
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! I'm Qamar, your voice + text assistant. Send me a voice note or type /daily."
    )





# /daily COMMAND
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "This is your daily summary. (We’ll hook up GPT and calendar soon)")





# HANDLE VOICE MESSAGES
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
        await file.download_to_drive(custom_path=tmp.name)
        tmp.flush()

        with open(tmp.name, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en"
            )

    user_text = transcript.text
    # DEBUG
    # await update.message.reply_text(f"You said: {user_text}")

    user_id = str(update.message.from_user.id)




    
    # WEB SEARCH
    search_triggers = ["search", "look up", "google", "find out", "what is", "who is"]

    def is_search_intent(text):
        text_lower = text.lower()
        return any(text_lower.startswith(trigger) for trigger in search_triggers)

    if is_search_intent(user_text):
        # Extract query from text
        for trigger in search_triggers:
            if user_text.lower().startswith(trigger):
                query = user_text[len(trigger):].strip()
                break

        # Run web search
        search_results = web_search(query)

        # Build prompt with search results
        prompt = (
            f"User wants fresh info on: '{query}'. Here are the latest search snippets:\n"
            f"{search_results}\n"
            "Answer casually, directly, and keep it chill like a Gen Z assistant."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": qamar_system_prompt},
                {"role": "user", "content": prompt}
            ]
        )

        reply_text = response.choices[0].message.content
        # Generate audio file
        # Generate speech from reply_text using OpenAI TTS
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=reply_text
        )


        
        # Save audio to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as speech_file:
            speech_file.write(speech_response.content)
            speech_path = speech_file.name
        # Send audio as a voice message
        with open(speech_path, "rb") as audio:
            await update.message.reply_voice(voice=audio)

        # Send text as a reply
        await update.message.reply_text(reply_text)



    
    else:
        # Normal Qamar flow: Summarization + memory
        user_id = str(update.message.from_user.id)
        # Create new highlights container, if don't have yet
        if user_id not in qamar_memory:
            qamar_memory[user_id] = {}
        if "highlights" not in qamar_memory[user_id]:
            qamar_memory[user_id]["highlights"] = []
    
        # STORE IN MEMORY
        summary_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a smart assistant. Summarize this message as a short, memorable highlight or insight. Don't respond to it:"},
                {"role": "user", "content": transcript.text}
            ]
        )
    
        # Extract the summary and store in highlight variable
        highlight = summary_response.choices[0].message.content.strip()
    
        if highlight and highlight not in qamar_memory[user_id]["highlights"]:
            qamar_memory[user_id]["highlights"].append(highlight)
            # If highlight is not exact same as past ones, add to memory
            save_memory(qamar_memory)




        
        # Reduce memory overload whenever recalled
        MAX_HIGHLIGHTS = 15
        if len(qamar_memory[user_id]["highlights"]) > MAX_HIGHLIGHTS:
            qamar_memory[user_id]["highlights"] = qamar_memory[user_id]["highlights"][-MAX_HIGHLIGHTS:]
            save_memory(qamar_memory)
    
        highlights = "\n- ".join(qamar_memory[user_id]["highlights"])
        memory_context = f"Here are the important things this user has said before:\n- {highlights}"




        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": qamar_system_prompt},
                {"role": "user", "content": f"{memory_context}\n\nRespond to this: {transcript.text}"}
            ]
        )
    
        reply_text = response.choices[0].message.content




        
        # Generate speech from reply_text using OpenAI TTS
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=reply_text
        )
        # Save audio to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as speech_file:
            speech_file.write(speech_response.content)
            speech_path = speech_file.name
        # Send audio as a voice message
        with open(speech_path, "rb") as audio:
            await update.message.reply_voice(voice=audio)
        # Send text as a reply
        await update.message.reply_text(reply_text)










if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Qamar is live.")
    app.run_polling()