from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from app.schemas import ChatMessage, ChatResponse, SlotOut
from app.database import get_db
from app.services.ai_service import get_ai_response, extract_action, clean_reply
from app.services.scheduler import parse_datetime, format_scheduled_time
import aiosqlite

router = APIRouter(tags=["Chat & Slots"])


# ─── Helper: load conversation history from DB ────────────────────────────────

async def load_history(session_id: str, db: aiosqlite.Connection) -> list[dict]:
    """Load conversation history in Gemini's expected format."""
    cur = await db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    rows = await cur.fetchall()
    history = []
    for row in rows:
        # Gemini uses "model" instead of "assistant"
        gemini_role = "model" if row["role"] == "assistant" else "user"
        history.append({"role": gemini_role, "parts": [{"text": row["content"]}]})
    return history


# ─── POST /chat/{session_id} — main conversation endpoint ────────────────────

@router.post("/chat/{session_id}", response_model=ChatResponse)
async def chat(
    session_id: str,
    payload: ChatMessage,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Send a message from the candidate and get an AI recruiter response.
    Automatically handles scheduling and cancellation based on the AI reply.
    """
    # 1. Validate session
    cur = await db.execute(
        "SELECT s.*, c.name AS cname, c.role AS crole "
        "FROM sessions s JOIN candidates c ON s.candidate_id = c.id "
        "WHERE s.id = ?",
        (session_id,),
    )
    session = await cur.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Session is already '{session['status']}'. Start a new session.",
        )

    candidate_name = session["cname"]
    role = session["crole"]
    candidate_id = session["candidate_id"]

    # 2. Save user message to DB
    await db.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
        (session_id, payload.message),
    )
    await db.commit()

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
    await db.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
        (session_id, display_reply),
    )
    await db.commit()

    # 7. Handle actions
    scheduled_time_str = None
    session_status = "active"

    if action:
        if action["action"] == "schedule":
            dt = parse_datetime(action.get("datetime", ""))
            if dt:
                scheduled_time_str = dt.isoformat()
                # Save slot
                await db.execute(
                    """INSERT INTO interview_slots
                       (session_id, candidate_id, scheduled_time)
                       VALUES (?, ?, ?)""",
                    (session_id, candidate_id, scheduled_time_str),
                )
                # Update session status
                await db.execute(
                    "UPDATE sessions SET status = 'scheduled' WHERE id = ?",
                    (session_id,),
                )
                await db.commit()
                session_status = "scheduled"

        elif action["action"] == "cancel":
            await db.execute(
                "UPDATE sessions SET status = 'cancelled' WHERE id = ?",
                (session_id,),
            )
            await db.commit()
            session_status = "cancelled"

    return ChatResponse(
        reply=display_reply,
        session_status=session_status,
        scheduled_time=scheduled_time_str,
    )


# ─── GET /chat/{session_id}/greet — trigger AI opening message ───────────────

@router.get("/chat/{session_id}/greet", response_model=ChatResponse)
async def greet(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """
    Trigger the AI's opening greeting message.
    Call this once right after creating a session.
    """
    cur = await db.execute(
        "SELECT s.*, c.name AS cname, c.role AS crole "
        "FROM sessions s JOIN candidates c ON s.candidate_id = c.id "
        "WHERE s.id = ?",
        (session_id,),
    )
    session = await cur.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Check if messages already exist
    cur = await db.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (session_id,)
    )
    row = await cur.fetchone()
    if row["cnt"] > 0:
        raise HTTPException(status_code=400, detail="Session already has messages. Use /chat to continue.")

    candidate_name = session["cname"]
    role = session["crole"]

    # Seed history with a trigger prompt (not stored as user message)
    seed_history = [
        {"role": "user", "parts": [{"text": f"Hello, I'm {candidate_name}."}]}
    ]
    try:
        ai_reply_raw = await get_ai_response(candidate_name, role, seed_history)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    display_reply = clean_reply(ai_reply_raw)

    await db.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
        (session_id, display_reply),
    )
    await db.commit()

    return ChatResponse(reply=display_reply, session_status="active")


# ─── GET /slots — all scheduled interviews ────────────────────────────────────

@router.get("/slots", response_model=list[SlotOut], tags=["Slots"])
async def list_slots(db: aiosqlite.Connection = Depends(get_db)):
    """Get all interview slots with candidate details."""
    cur = await db.execute(
        """SELECT
            sl.id, sl.session_id, sl.candidate_id,
            c.name  AS candidate_name,
            c.email AS candidate_email,
            c.role,
            sl.scheduled_time, sl.duration_minutes,
            sl.location, sl.status, sl.notes, sl.created_at
           FROM interview_slots sl
           JOIN candidates c ON sl.candidate_id = c.id
           ORDER BY sl.scheduled_time ASC""",
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ─── PUT /slots/{slot_id}/cancel — cancel a slot ─────────────────────────────

@router.put("/slots/{slot_id}/cancel", tags=["Slots"])
async def cancel_slot(slot_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Cancel a scheduled interview slot."""
    cur = await db.execute("SELECT id FROM interview_slots WHERE id = ?", (slot_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="Slot not found.")
    await db.execute(
        "UPDATE interview_slots SET status = 'cancelled' WHERE id = ?", (slot_id,)
    )
    await db.commit()
    return {"message": f"Slot {slot_id} has been cancelled."}
