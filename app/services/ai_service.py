from __future__ import annotations

import os
import json
import re
import time
import asyncio
from google import genai
from google.genai import errors as genai_errors
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

COMPANY_NAME  = os.getenv("COMPANY_NAME", "TechCorp")
RECRUITER_NAME = os.getenv("RECRUITER_NAME", "Alex")

# Models to try in order of preference
MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

# Retry settings
MAX_RETRIES = 3
BASE_DELAY = 2  # seconds


def build_system_prompt(candidate_name: str, role: str) -> str:
    return f"""You are {RECRUITER_NAME}, a warm and professional recruiter at {COMPANY_NAME}.
Your task is to schedule a 45-minute interview with {candidate_name}, who applied for the {role} position.

## Your Personality
- Friendly, concise, and encouraging
- Professional but not robotic
- Use the candidate's first name naturally

## Your Goals (in order)
1. Greet the candidate and mention their role
2. Ask for 2–3 available time slots over the next few days
3. Confirm one specific date and time
4. If they decline or are unavailable, offer alternatives or reschedule gracefully
5. If they are no longer interested, wish them well politely

## Rules
- Keep each reply under 4 sentences
- NEVER make up calendar data — only work with what the candidate tells you
- When a specific date/time is CONFIRMED by the candidate, output EXACTLY this JSON block on its own line at the END of your reply:
  {{"action": "schedule", "datetime": "YYYY-MM-DD HH:MM"}}
- When the candidate declines/cancels, output EXACTLY this JSON block on its own line:
  {{"action": "cancel"}}
- For rescheduling requests just continue the conversation normally without a JSON block
- Do NOT include the JSON block unless one of those two definitive outcomes occurs

## Current year context
The current year is 2026. Use realistic near-future dates.
"""


def _build_contents(system_prompt: str, message_history: list[dict]) -> list[dict]:
    """Convert message history to the format expected by google-genai."""
    contents = []
    for msg in message_history:
        role = msg["role"]
        # google-genai uses "user" and "model" roles
        if role not in ("user", "model"):
            role = "user"
        text = msg["parts"][0]["text"]
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents


def _sync_gemini_call(system_prompt: str, message_history: list[dict]) -> str:
    """Synchronous Gemini API call with model fallback and retry logic."""
    contents = _build_contents(system_prompt, message_history)

    for attempt in range(MAX_RETRIES):
        for model_name in MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config={
                        "system_instruction": system_prompt,
                    },
                )
                return response.text
            except Exception as e:
                error_str = str(e)
                is_quota = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                print(f"[AI] Model {model_name} attempt {attempt+1}: {type(e).__name__}: {error_str[:100]}")

                if is_quota:
                    # Try next model
                    continue
                else:
                    # Non-quota error, raise immediately
                    raise

        # All models failed this attempt — wait before retrying
        if attempt < MAX_RETRIES - 1:
            delay = BASE_DELAY * (2 ** attempt)
            print(f"[AI] All models quota-exhausted. Retrying in {delay}s...")
            time.sleep(delay)

    raise RuntimeError(
        "Gemini API quota exceeded on all models after retries. "
        "Please wait a minute or create a new API key in a different project at https://aistudio.google.com/app/apikey"
    )


async def get_ai_response(
    candidate_name: str,
    role: str,
    message_history: list[dict],
) -> str:
    """
    Send conversation history to Gemini and return the AI reply.

    message_history format: [{"role": "user"|"model", "parts": [{"text": "..."}]}]
    """
    system_prompt = build_system_prompt(candidate_name, role)

    try:
        # Run the synchronous Gemini SDK call in a thread so we don't block the event loop
        return await asyncio.to_thread(_sync_gemini_call, system_prompt, message_history)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"AI service error: {e}")


def extract_action(ai_reply: str) -> dict | None:
    """
    Look for a JSON action block in the AI reply.
    Returns {"action": "schedule", "datetime": "..."} or {"action": "cancel"} or None.
    """
    pattern = r'\{[^{}]*"action"\s*:\s*"(schedule|cancel)"[^{}]*\}'
    match = re.search(pattern, ai_reply)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def clean_reply(ai_reply: str) -> str:
    """Remove the JSON action block from the displayed reply."""
    pattern = r'\{[^{}]*"action"\s*:\s*"(schedule|cancel)"[^{}]*\}'
    return re.sub(pattern, "", ai_reply).strip()
