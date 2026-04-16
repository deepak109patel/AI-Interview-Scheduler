from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from app.database import get_db, clean_doc
import csv
import io
import json

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/interviews")
async def export_interviews(
    format: str = Query("csv", description="Export format: csv or json"),
    status: str = Query(None, description="Filter by status"),
    db=Depends(get_db),
):
    """Export interview slots as CSV or JSON."""
    query = {}
    if status:
        query["status"] = status

    data = []
    async for slot in db.interview_slots.find(query).sort("scheduled_time", 1):
        candidate = await db.candidates.find_one({"id": slot["candidate_id"]})
        data.append({
            "id": slot["id"],
            "candidate_name": candidate["name"] if candidate else "",
            "candidate_email": candidate["email"] if candidate else "",
            "role": candidate["role"] if candidate else "",
            "scheduled_time": slot["scheduled_time"],
            "duration_minutes": slot["duration_minutes"],
            "location": slot.get("location", ""),
            "status": slot["status"],
            "notes": slot.get("notes"),
            "created_at": slot["created_at"],
        })

    if format == "json":
        return StreamingResponse(
            io.BytesIO(json.dumps(data, indent=2).encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=interviews.json"},
        )

    # CSV
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    else:
        output.write("No interviews found")

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=interviews.csv"},
    )


@router.get("/candidates")
async def export_candidates(
    format: str = Query("csv"),
    db=Depends(get_db),
):
    """Export all candidates."""
    data = []
    async for doc in db.candidates.find().sort("name", 1):
        data.append({
            "id": doc["id"],
            "name": doc["name"],
            "email": doc["email"],
            "phone": doc.get("phone"),
            "role": doc["role"],
            "status": doc["status"],
            "created_at": doc["created_at"],
        })

    if format == "json":
        return StreamingResponse(
            io.BytesIO(json.dumps(data, indent=2).encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=candidates.json"},
        )

    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidates.csv"},
    )


@router.get("/report/{candidate_id}")
async def candidate_report(candidate_id: int, db=Depends(get_db)):
    """Generate a detailed report for a candidate."""
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        return {"error": "Candidate not found"}

    # Sessions
    sessions = []
    async for s in db.sessions.find({"candidate_id": candidate_id}).sort("created_at", -1):
        sessions.append({
            "id": s["id"],
            "status": s["status"],
            "created_at": s["created_at"],
        })

    # Interviews
    interviews = []
    async for s in db.interview_slots.find({"candidate_id": candidate_id}):
        interviews.append({
            "scheduled_time": s["scheduled_time"],
            "duration_minutes": s["duration_minutes"],
            "location": s.get("location", ""),
            "status": s["status"],
        })

    # Message count
    msg_count = 0
    for sess in sessions:
        count = await db.messages.count_documents({"session_id": sess["id"]})
        msg_count += count

    return {
        "candidate": clean_doc(candidate),
        "total_sessions": len(sessions),
        "total_messages": msg_count,
        "sessions": sessions,
        "interviews": interviews,
        "generated_at": "now",
    }
