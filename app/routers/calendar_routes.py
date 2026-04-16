from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from app.schemas import RescheduleRequest
from app.database import get_db, log_activity
from app.services.scheduler import parse_datetime
import aiosqlite

router = APIRouter(prefix="/api/calendar", tags=["Calendar"])


@router.get("/events")
async def get_calendar_events(
    start: str = Query(None, description="Start date YYYY-MM-DD"),
    end: str = Query(None, description="End date YYYY-MM-DD"),
    status: str = Query(None, description="Filter by status"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get interview events for calendar view."""
    query = """SELECT sl.id, c.name AS candidate_name, c.email AS candidate_email,
                      c.role, sl.scheduled_time, sl.duration_minutes,
                      sl.location, sl.status, sl.notes
               FROM interview_slots sl
               JOIN candidates c ON sl.candidate_id = c.id
               WHERE 1=1"""
    params = []

    if start:
        query += " AND sl.scheduled_time >= ?"
        params.append(start)
    if end:
        query += " AND sl.scheduled_time <= ?"
        params.append(end + " 23:59:59")
    if status:
        query += " AND sl.status = ?"
        params.append(status)

    query += " ORDER BY sl.scheduled_time ASC"

    cur = await db.execute(query, params)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.put("/events/{slot_id}/reschedule")
async def reschedule_event(
    slot_id: int,
    payload: RescheduleRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Reschedule an interview to a new datetime."""
    cur = await db.execute(
        "SELECT sl.*, c.name FROM interview_slots sl JOIN candidates c ON sl.candidate_id = c.id WHERE sl.id = ?",
        (slot_id,),
    )
    slot = await cur.fetchone()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found.")

    dt = parse_datetime(payload.new_datetime)
    if not dt:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use YYYY-MM-DD HH:MM.")

    await db.execute(
        "UPDATE interview_slots SET scheduled_time = ?, status = 'confirmed' WHERE id = ?",
        (dt.isoformat(), slot_id),
    )
    await db.commit()
    await log_activity(db, "rescheduled", "interview", slot_id, f"Rescheduled {slot['name']} to {dt}")

    return {"message": f"Interview rescheduled to {dt.strftime('%A, %B %d %Y at %I:%M %p')}"}


@router.get("/events/{slot_id}")
async def get_event_detail(slot_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get detailed event info."""
    cur = await db.execute(
        """SELECT sl.*, c.name AS candidate_name, c.email AS candidate_email,
                  c.phone AS candidate_phone, c.role
           FROM interview_slots sl
           JOIN candidates c ON sl.candidate_id = c.id
           WHERE sl.id = ?""",
        (slot_id,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")
    return dict(row)
