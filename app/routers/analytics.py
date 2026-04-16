from __future__ import annotations

from fastapi import APIRouter, Depends
from app.database import get_db, clean_doc
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def dashboard_stats(db=Depends(get_db)):
    """Get comprehensive dashboard statistics."""
    # Total candidates
    total_candidates = await db.candidates.count_documents({})

    # Candidates by status
    candidates_by_status = {}
    async for row in db.candidates.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]):
        candidates_by_status[row["_id"]] = row["count"]

    # Active sessions
    active_sessions = await db.sessions.count_documents({"status": "active"})

    # Interviews scheduled
    interviews_scheduled = await db.interview_slots.count_documents({"status": "confirmed"})

    # Interviews cancelled
    interviews_cancelled = await db.interview_slots.count_documents({"status": "cancelled"})

    # Completion rate
    total_sessions = await db.sessions.count_documents({})
    completed_sessions = await db.sessions.count_documents({"status": "scheduled"})
    completion_rate = (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0

    # Sessions by status
    sessions_by_status = {}
    async for row in db.sessions.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]):
        sessions_by_status[row["_id"]] = row["count"]

    # Interviews this week
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    week_later = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    interviews_this_week = await db.interview_slots.count_documents({
        "scheduled_time": {"$gte": today, "$lt": week_later},
        "status": "confirmed",
    })

    # Top roles
    top_roles = {}
    async for row in db.candidates.aggregate([
        {"$group": {"_id": "$role", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]):
        top_roles[row["_id"]] = row["count"]

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
async def dashboard_timeline(days: int = 14, db=Depends(get_db)):
    """Get upcoming interview timeline."""
    now = datetime.utcnow()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    future = (now + timedelta(days=days)).strftime("%Y-%m-%d")

    results = []
    async for slot in db.interview_slots.find({
        "scheduled_time": {"$gte": yesterday, "$lt": future},
    }).sort("scheduled_time", 1):
        candidate = await db.candidates.find_one({"id": slot["candidate_id"]})
        results.append({
            "id": slot["id"],
            "candidate_name": candidate["name"] if candidate else "Unknown",
            "role": candidate["role"] if candidate else "",
            "scheduled_time": slot["scheduled_time"],
            "duration_minutes": slot["duration_minutes"],
            "status": slot["status"],
            "location": slot.get("location", ""),
        })
    return results


@router.get("/activity")
async def dashboard_activity(limit: int = 20, db=Depends(get_db)):
    """Get recent activity feed."""
    results = []
    async for doc in db.activity_log.find().sort("created_at", -1).limit(limit):
        results.append(clean_doc(doc))
    return results


@router.get("/chart/interviews-per-day")
async def interviews_per_day(days: int = 30, db=Depends(get_db)):
    """Get interview counts per day for charting."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    results = []
    async for row in db.interview_slots.aggregate([
        {"$match": {"scheduled_time": {"$gte": cutoff}}},
        {"$addFields": {"day": {"$substr": ["$scheduled_time", 0, 10]}}},
        {"$group": {"_id": "$day", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]):
        results.append({"day": row["_id"], "count": row["count"]})
    return results


@router.get("/chart/candidates-per-week")
async def candidates_per_week(weeks: int = 8, db=Depends(get_db)):
    """Get new candidates per week for charting."""
    cutoff = (datetime.utcnow() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

    results = []
    async for row in db.candidates.aggregate([
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$addFields": {"week": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {"_id": "$week", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]):
        results.append({"week": row["_id"], "count": row["count"]})
    return results
