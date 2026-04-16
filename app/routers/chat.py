from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from app.schemas import ChatMessage, ChatResponse, SlotOut
from app.database import get_db, get_next_id, clean_doc
from app.services.ai_service import get_ai_response, extract_action, clean_reply
from app.services.scheduler import parse_datetime, format_scheduled_time
from datetime import datetime

router = APIRouter(tags=["Chat & Slots"])


# ─── Helper: load conversation history from DB ────────────────────────────────

async def load_history(session_id: str, db) -> list[dict]:
    """Load conversation history in Gemini's expected format."""
    history = []
    async for doc in db.messages.find({"session_id": session_id}).sort("created_at", 1):
        # Gemini uses "model" instead of "assistant"
        gemini_role = "model" if doc["role"] == "assistant" else "user"
        history.append({"role": gemini_role, "parts": [{"text": doc["content"]}]})
    return history


# ─── POST /chat/{session_id} — main conversation endpoint ────────────────────

@router.post("/chat/{session_id}", response_model=ChatResponse)
async def chat(
    session_id: str,
    payload: ChatMessage,
    db=Depends(get_db),
):
    """
    Send a message from the candidate and get an AI recruiter response.
    Automatically handles scheduling and cancellation based on the AI reply.
    """
    # 1. Validate session
    session = await db.sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Session is already '{session['status']}'. Start a new session.",
        )

    # Get candidate info
    candidate = await db.candidates.find_one({"id": session["candidate_id"]})
    candidate_name = candidate["name"]
    role = candidate["role"]
    candidate_id = session["candidate_id"]

    # 2. Save user message to DB
    msg_id = await get_next_id("messages")
    await db.messages.insert_one({
        "id": msg_id,
        "session_id": session_id,
        "role": "user",
        "content": payload.message,
        "created_at": datetime.utcnow().isoformat(),
    })

    # 3. Load full history (now includes the message we just saved)
    history = await load_history(session_id, db)

    # 4. Get AI response
    try:
        ai_reply_raw = await get_ai_response(candidate_name, role, history)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 5. Parse action from AI reply
    action = extract_action(ai_reply_raw)
    display_reply = clean_reply(ai_reply_raw)

    # 6. Save assistant message to DB
    msg_id = await get_next_id("messages")
    await db.messages.insert_one({
        "id": msg_id,
        "session_id": session_id,
        "role": "assistant",
        "content": display_reply,
        "created_at": datetime.utcnow().isoformat(),
    })

    # 7. Handle actions
    scheduled_time_str = None
    session_status = "active"

    if action:
        if action["action"] == "schedule":
            dt = parse_datetime(action.get("datetime", ""))
            if dt:
                scheduled_time_str = dt.isoformat()
                # Save slot
                slot_id = await get_next_id("interview_slots")
                await db.interview_slots.insert_one({
                    "id": slot_id,
                    "session_id": session_id,
                    "candidate_id": candidate_id,
                    "scheduled_time": scheduled_time_str,
                    "duration_minutes": 45,
                    "location": "Google Meet link will be sent via email",
                    "status": "confirmed",
                    "notes": None,
                    "created_at": datetime.utcnow().isoformat(),
                })
                # Update session status
                await db.sessions.update_one(
                    {"id": session_id},
                    {"$set": {"status": "scheduled"}},
                )
                session_status = "scheduled"

        elif action["action"] == "cancel":
            await db.sessions.update_one(
                {"id": session_id},
                {"$set": {"status": "cancelled"}},
            )
            session_status = "cancelled"

    return ChatResponse(
        reply=display_reply,
        session_status=session_status,
        scheduled_time=scheduled_time_str,
    )


# ─── GET /chat/{session_id}/greet — trigger AI opening message ───────────────

@router.get("/chat/{session_id}/greet", response_model=ChatResponse)
async def greet(session_id: str, db=Depends(get_db)):
    """
    Trigger the AI's opening greeting message.
    Call this once right after creating a session.
    """
    session = await db.sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Check if messages already exist
    count = await db.messages.count_documents({"session_id": session_id})
    if count > 0:
        raise HTTPException(status_code=400, detail="Session already has messages. Use /chat to continue.")

    candidate = await db.candidates.find_one({"id": session["candidate_id"]})
    candidate_name = candidate["name"]
    role = candidate["role"]

    # Seed history with a trigger prompt (not stored as user message)
    seed_history = [
        {"role": "user", "parts": [{"text": f"Hello, I'm {candidate_name}."}]}
    ]
    try:
        ai_reply_raw = await get_ai_response(candidate_name, role, seed_history)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    display_reply = clean_reply(ai_reply_raw)

    msg_id = await get_next_id("messages")
    await db.messages.insert_one({
        "id": msg_id,
        "session_id": session_id,
        "role": "assistant",
        "content": display_reply,
        "created_at": datetime.utcnow().isoformat(),
    })

    return ChatResponse(reply=display_reply, session_status="active")


# ─── GET /slots — all scheduled interviews ────────────────────────────────────

@router.get("/slots", response_model=list[SlotOut], tags=["Slots"])
async def list_slots(db=Depends(get_db)):
    """Get all interview slots with candidate details."""
    results = []
    async for slot in db.interview_slots.find().sort("scheduled_time", 1):
        candidate = await db.candidates.find_one({"id": slot["candidate_id"]})
        doc = clean_doc(slot)
        doc["candidate_name"] = candidate["name"] if candidate else ""
        doc["candidate_email"] = candidate["email"] if candidate else ""
        doc["role"] = candidate["role"] if candidate else ""
        results.append(doc)
    return results


# ─── PUT /slots/{slot_id}/cancel — cancel a slot ─────────────────────────────

@router.put("/slots/{slot_id}/cancel", tags=["Slots"])
async def cancel_slot(slot_id: int, db=Depends(get_db)):
    """Cancel a scheduled interview slot."""
    slot = await db.interview_slots.find_one({"id": slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found.")
    await db.interview_slots.update_one(
        {"id": slot_id},
        {"$set": {"status": "cancelled"}},
    )
    return {"message": f"Slot {slot_id} has been cancelled."}
