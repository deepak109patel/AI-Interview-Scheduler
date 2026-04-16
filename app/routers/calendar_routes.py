from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from app.schemas import RescheduleRequest
from app.database import get_db, log_activity, clean_doc
from app.services.scheduler import parse_datetime

router = APIRouter(prefix="/api/calendar", tags=["Calendar"])


@router.get("/events")
async def get_calendar_events(
    start: str = Query(None, description="Start date YYYY-MM-DD"),
    end: str = Query(None, description="End date YYYY-MM-DD"),
    status: str = Query(None, description="Filter by status"),
    db=Depends(get_db),
):
    """Get interview events for calendar view."""
    conditions = []

    if start:
        conditions.append({"scheduled_time": {"$gte": start}})
    if end:
        conditions.append({"scheduled_time": {"$lte": end + " 23:59:59"}})
    if status:
        conditions.append({"status": status})

    query = {"$and": conditions} if len(conditions) > 1 else (conditions[0] if conditions else {})

    results = []
    async for slot in db.interview_slots.find(query).sort("scheduled_time", 1):
        candidate = await db.candidates.find_one({"id": slot["candidate_id"]})
        results.append({
            "id": slot["id"],
            "candidate_name": candidate["name"] if candidate else "",
            "candidate_email": candidate["email"] if candidate else "",
            "role": candidate["role"] if candidate else "",
            "scheduled_time": slot["scheduled_time"],
            "duration_minutes": slot["duration_minutes"],
            "location": slot.get("location", ""),
            "status": slot["status"],
            "notes": slot.get("notes"),
        })
    return results


@router.put("/events/{slot_id}/reschedule")
async def reschedule_event(
    slot_id: int,
    payload: RescheduleRequest,
    db=Depends(get_db),
):
    """Reschedule an interview to a new datetime."""
    slot = await db.interview_slots.find_one({"id": slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found.")

    dt = parse_datetime(payload.new_datetime)
    if not dt:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use YYYY-MM-DD HH:MM.")

    candidate = await db.candidates.find_one({"id": slot["candidate_id"]})
    candidate_name = candidate["name"] if candidate else "Unknown"

    await db.interview_slots.update_one(
        {"id": slot_id},
        {"$set": {"scheduled_time": dt.isoformat(), "status": "confirmed"}},
    )
    await log_activity(db, "rescheduled", "interview", slot_id, f"Rescheduled {candidate_name} to {dt}")

    return {"message": f"Interview rescheduled to {dt.strftime('%A, %B %d %Y at %I:%M %p')}"}


@router.get("/events/{slot_id}")
async def get_event_detail(slot_id: int, db=Depends(get_db)):
    """Get detailed event info."""
    slot = await db.interview_slots.find_one({"id": slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail="Event not found.")

    candidate = await db.candidates.find_one({"id": slot["candidate_id"]})
    doc = clean_doc(slot)
    doc["candidate_name"] = candidate["name"] if candidate else ""
    doc["candidate_email"] = candidate["email"] if candidate else ""
    doc["candidate_phone"] = candidate.get("phone", "") if candidate else ""
    doc["role"] = candidate["role"] if candidate else ""
    return doc
