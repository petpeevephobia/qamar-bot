# Qamar

A personal Telegram bot that captures ideas when you're away from your laptop — voice notes in, organised notes out.

## Why

I think better out loud, especially when ideas hit and I don't have Obsidian handy. Qamar lets me send a quick voice message from my phone and turns it into a structured note in my vault, so nothing gets lost between walks, commutes, and late-night brain dumps.

## What it does

Qamar receives voice messages, transcribes them, and uses an LLM to shape the content for your note template: title, tags, and maturity (`baby` / `teen` / `adult`, defaulting to baby). Notes land in the **6 - Full Notes** folder in Obsidian; tags keep everything searchable.

Today the bot runs on Telegram with voice transcription and conversational replies. Obsidian note creation and the full templating flow are the core workflow being built toward.

**Stack:** Python, Telegram, OpenAI (transcription + generation). Planned: Gemini, Obsidian API, MVC-style structure.

## On the horizon

- RAG over existing Obsidian notes to help ideate on new projects (problem statements, SWOT, stack-aware suggestions for Python, TypeScript, Go, SQL)
