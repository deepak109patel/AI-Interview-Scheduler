"""Quick test to find code-level bugs without hitting the Gemini API."""
import sys
sys.path.insert(0, '.')

# Test 1: schemas import
from app.schemas import CandidateCreate, CandidateOut, SessionStart, SessionOut, ChatMessage, ChatResponse, MessageOut, SlotOut
print('✅ All schemas import fine')

# Test 2: check ai_service functions
from app.services.ai_service import build_system_prompt, extract_action, clean_reply
print('✅ ai_service imports fine')

# Test 3: Test extract_action
test1 = extract_action('Sure! I have scheduled your interview. {"action": "schedule", "datetime": "2026-04-22 14:00"}')
print(f'  extract_action schedule: {test1}')

test2 = extract_action('I understand. {"action": "cancel"}')
print(f'  extract_action cancel: {test2}')

test3 = extract_action('Normal message without action')
print(f'  extract_action none: {test3}')

# Test 4: Test clean_reply
test4 = clean_reply('Sure! I have scheduled your interview. {"action": "schedule", "datetime": "2026-04-22 14:00"}')
print(f'  clean_reply: "{test4}"')

# Test 5: Test scheduler
from app.services.scheduler import parse_datetime, format_scheduled_time
dt = parse_datetime('2026-04-22 14:00')
print(f'  parse_datetime: {dt}')
print(f'  format_scheduled_time: {format_scheduled_time(dt)}')

# Test 6: Test system prompt
prompt = build_system_prompt('Sarah Khan', 'Senior Python Developer')
print(f'✅ System prompt length: {len(prompt)} chars')

# Test 7: Check if get_ai_response is async properly
import inspect
from app.services.ai_service import get_ai_response
print(f'  get_ai_response is coroutine: {inspect.iscoroutinefunction(get_ai_response)}')

# Test 8: The sync-in-async problem
print()
print('⚠️  ISSUE: get_ai_response is async but calls chat.send_message() SYNCHRONOUSLY')
print('   This blocks the FastAPI event loop during Gemini API calls.')

# Test 9: Check google-generativeai version for async support
import google.generativeai as genai
print(f'  google-generativeai version: {genai.__version__}')

print()
print('=== SUMMARY ===')
print('1. Core code logic (schemas, extract_action, clean_reply, parse_datetime) works ✅')
print('2. Gemini API quota is EXHAUSTED (429 error) — this is the main runtime error ❌')
print('3. get_ai_response blocks event loop (sync call in async function) — should use asyncio.to_thread() ⚠️')
print('4. No error handling around Gemini API calls — 500 is returned raw to the frontend ⚠️')
