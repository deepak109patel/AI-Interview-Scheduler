from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from app.database import get_db
import aiosqlite
import csv
import io
import json

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/interviews")
async def export_interviews(
    format: str = Query("csv", description="Export format: csv or json"),
    status: str = Query(None, description="Filter by status"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Export interview slots as CSV or JSON."""
    query = """SELECT sl.id, c.name AS candidate_name, c.email AS candidate_email,
                      c.role, sl.scheduled_time, sl.duration_minutes,
                      sl.location, sl.status, sl.notes, sl.created_at
               FROM interview_slots sl
               JOIN candidates c ON sl.candidate_id = c.id"""
    params = []

    if status:
        query += " WHERE sl.status = ?"
        params.append(status)

    query += " ORDER BY sl.scheduled_time ASC"

    cur = await db.execute(query, params)
    rows = await cur.fetchall()
    data = [dict(r) for r in rows]

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
    db: aiosqlite.Connection = Depends(get_db),
):
    """Export all candidates."""
    cur = await db.execute("SELECT id, name, email, phone, role, status, created_at FROM candidates ORDER BY name")
    rows = await cur.fetchall()
    data = [dict(r) for r in rows]

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
async def candidate_report(candidate_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Generate a detailed report for a candidate."""
    # Candidate info
    cur = await db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    candidate = await cur.fetchone()
    if not candidate:
        return {"error": "Candidate not found"}

    # Sessions
    cur = await db.execute(
        "SELECT id, status, created_at FROM sessions WHERE candidate_id = ? ORDER BY created_at DESC",
        (candidate_id,),
    )
    sessions = [dict(s) for s in await cur.fetchall()]

    # Interviews
    cur = await db.execute(
        "SELECT scheduled_time, duration_minutes, location, status FROM interview_slots WHERE candidate_id = ?",
        (candidate_id,),
    )
    interviews = [dict(s) for s in await cur.fetchall()]

    # Message count
    session_ids = [s["id"] for s in sessions]
    msg_count = 0
    for sid in session_ids:
        cur = await db.execute("SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (sid,))
        msg_count += (await cur.fetchone())["cnt"]

    return {
        "candidate": dict(candidate),
        "total_sessions": len(sessions),
        "total_messages": msg_count,
        "sessions": sessions,
        "interviews": interviews,
        "generated_at": "now",
    }
