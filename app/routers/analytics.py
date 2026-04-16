from __future__ import annotations

from fastapi import APIRouter, Depends
from app.database import get_db
import aiosqlite

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def dashboard_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Get comprehensive dashboard statistics."""
    # Total candidates
    cur = await db.execute("SELECT COUNT(*) as cnt FROM candidates")
    total_candidates = (await cur.fetchone())["cnt"]

    # Candidates by status
    cur = await db.execute("SELECT status, COUNT(*) as count FROM candidates GROUP BY status")
    status_rows = await cur.fetchall()
    candidates_by_status = {r["status"]: r["count"] for r in status_rows}

    # Active sessions
    cur = await db.execute("SELECT COUNT(*) as cnt FROM sessions WHERE status = 'active'")
    active_sessions = (await cur.fetchone())["cnt"]

    # Interviews scheduled
    cur = await db.execute("SELECT COUNT(*) as cnt FROM interview_slots WHERE status = 'confirmed'")
    interviews_scheduled = (await cur.fetchone())["cnt"]

    # Interviews cancelled
    cur = await db.execute("SELECT COUNT(*) as cnt FROM interview_slots WHERE status = 'cancelled'")
    interviews_cancelled = (await cur.fetchone())["cnt"]

    # Total sessions for completion rate
    cur = await db.execute("SELECT COUNT(*) as cnt FROM sessions")
    total_sessions = (await cur.fetchone())["cnt"]

    cur = await db.execute("SELECT COUNT(*) as cnt FROM sessions WHERE status = 'scheduled'")
    completed_sessions = (await cur.fetchone())["cnt"]

    completion_rate = (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0

    # Sessions by status
    cur = await db.execute("SELECT status, COUNT(*) as count FROM sessions GROUP BY status")
    session_rows = await cur.fetchall()
    sessions_by_status = {r["status"]: r["count"] for r in session_rows}

    # Interviews this week
    cur = await db.execute(
        "SELECT COUNT(*) as cnt FROM interview_slots WHERE scheduled_time >= date('now') AND scheduled_time < date('now', '+7 days') AND status = 'confirmed'"
    )
    interviews_this_week = (await cur.fetchone())["cnt"]

    # Roles distribution
    cur = await db.execute("SELECT role, COUNT(*) as count FROM candidates GROUP BY role ORDER BY count DESC LIMIT 5")
    role_rows = await cur.fetchall()
    top_roles = {r["role"]: r["count"] for r in role_rows}

    return {
        "total_candidates": total_candidates,
        "active_sessions": active_sessions,
        "interviews_scheduled": interviews_scheduled,
        "interviews_cancelled": interviews_cancelled,
        "completion_rate": round(completion_rate, 1),
        "candidates_by_status": candidates_by_status,
        "sessions_by_status": sessions_by_status,
        "interviews_this_week": interviews_this_week,
        "top_roles": top_roles,
    }


@router.get("/timeline")
async def dashboard_timeline(days: int = 14, db: aiosqlite.Connection = Depends(get_db)):
    """Get upcoming interview timeline."""
    cur = await db.execute(
        """SELECT sl.id, c.name AS candidate_name, c.role, sl.scheduled_time,
                  sl.duration_minutes, sl.status, sl.location
           FROM interview_slots sl
           JOIN candidates c ON sl.candidate_id = c.id
           WHERE sl.scheduled_time >= date('now', '-1 day')
             AND sl.scheduled_time < date('now', '+' || ? || ' days')
           ORDER BY sl.scheduled_time ASC""",
        (days,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/activity")
async def dashboard_activity(limit: int = 20, db: aiosqlite.Connection = Depends(get_db)):
    """Get recent activity feed."""
    cur = await db.execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/chart/interviews-per-day")
async def interviews_per_day(days: int = 30, db: aiosqlite.Connection = Depends(get_db)):
    """Get interview counts per day for charting."""
    cur = await db.execute(
        """SELECT date(scheduled_time) as day, COUNT(*) as count
           FROM interview_slots
           WHERE scheduled_time >= date('now', '-' || ? || ' days')
           GROUP BY day
           ORDER BY day ASC""",
        (days,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/chart/candidates-per-week")
async def candidates_per_week(weeks: int = 8, db: aiosqlite.Connection = Depends(get_db)):
    """Get new candidates per week for charting."""
    cur = await db.execute(
        """SELECT strftime('%Y-W%W', created_at) as week, COUNT(*) as count
           FROM candidates
           WHERE created_at >= date('now', '-' || ? || ' days')
           GROUP BY week
           ORDER BY week ASC""",
        (weeks * 7,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]
