from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from app.schemas import SessionStart, SessionOut, MessageOut
from app.database import get_db
import aiosqlite
import uuid

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("/start", response_model=SessionOut, status_code=201)
async def start_session(payload: SessionStart, db: aiosqlite.Connection = Depends(get_db)):
    """
    Start a new interview scheduling session for a candidate.
    The AI greeting will be triggered on the first /chat call.
    """
    # Verify candidate exists
    cur = await db.execute("SELECT id FROM candidates WHERE id = ?", (payload.candidate_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Check for existing active session
    cur = await db.execute(
        "SELECT id FROM sessions WHERE candidate_id = ? AND status = 'active'",
        (payload.candidate_id,),
    )
    existing = await cur.fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"An active session already exists for this candidate: {existing['id']}",
        )

    session_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO sessions (id, candidate_id, status) VALUES (?, ?, 'active')",
        (session_id, payload.candidate_id),
    )
    await db.commit()

    cur = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cur.fetchone()
    return dict(row)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get session details."""
    cur = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")
    return dict(row)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get full conversation history for a session."""
    cur = await db.execute(
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.put("/{session_id}/complete")
async def complete_session(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Mark a session as completed so a new one can be started."""
    cur = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")
    if row["status"] in ("completed", "cancelled"):
        return {"message": "Session already ended."}

    await db.execute(
        "UPDATE sessions SET status = 'completed' WHERE id = ?", (session_id,)
    )
    await db.commit()
    return {"message": "Session completed."}

