from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from app.schemas import SessionStart, SessionOut, MessageOut
from app.database import get_db, clean_doc
from datetime import datetime
import uuid

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("/start", response_model=SessionOut, status_code=201)
async def start_session(payload: SessionStart, db=Depends(get_db)):
    """
    Start a new interview scheduling session for a candidate.
    The AI greeting will be triggered on the first /chat call.
    """
    # Verify candidate exists
    candidate = await db.candidates.find_one({"id": payload.candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Check for existing active session
    existing = await db.sessions.find_one(
        {"candidate_id": payload.candidate_id, "status": "active"}
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"An active session already exists for this candidate: {existing['id']}",
        )

    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    doc = {
        "id": session_id,
        "candidate_id": payload.candidate_id,
        "status": "active",
        "created_at": now,
    }
    await db.sessions.insert_one(doc)
    return clean_doc(doc)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db=Depends(get_db)):
    """Get session details."""
    doc = await db.sessions.find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return clean_doc(doc)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(session_id: str, db=Depends(get_db)):
    """Get full conversation history for a session."""
    results = []
    async for doc in db.messages.find({"session_id": session_id}).sort("created_at", 1):
        results.append(clean_doc(doc))
    return results


@router.put("/{session_id}/complete")
async def complete_session(session_id: str, db=Depends(get_db)):
    """Mark a session as completed so a new one can be started."""
    session = await db.sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] in ("completed", "cancelled"):
        return {"message": "Session already ended."}

    await db.sessions.update_one(
        {"id": session_id}, {"$set": {"status": "completed"}}
    )
    return {"message": "Session completed."}
