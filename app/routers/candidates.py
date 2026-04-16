from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from app.schemas import CandidateCreate, CandidateOut, CandidateUpdate
from app.database import get_db, get_next_id, log_activity, clean_doc
from pymongo.errors import DuplicateKeyError
from datetime import datetime
import csv
import io

router = APIRouter(prefix="/candidates", tags=["Candidates"])

VALID_STATUSES = {"applied", "screening", "interview", "hired", "rejected"}


@router.post("/", response_model=CandidateOut, status_code=201)
async def add_candidate(payload: CandidateCreate, db=Depends(get_db)):
    """Add a new candidate to the system."""
    now = datetime.utcnow().isoformat()
    candidate_id = await get_next_id("candidates")
    doc = {
        "id": candidate_id,
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "role": payload.role,
        "status": "applied",
        "notes": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.candidates.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="A candidate with this email already exists.")

    await log_activity(db, "created", "candidate", candidate_id, f"Added candidate: {payload.name}")
    return clean_doc(doc)


@router.get("/", response_model=list[CandidateOut])
async def list_candidates(
    search: str = Query(None, description="Search by name, email, or role"),
    status: str = Query(None, description="Filter by status"),
    role: str = Query(None, description="Filter by role"),
    sort: str = Query("newest", description="Sort: newest, oldest, name"),
    db=Depends(get_db),
):
    """List all candidates with optional search and filters."""
    conditions = []

    if search:
        regex = {"$regex": search, "$options": "i"}
        conditions.append({"$or": [{"name": regex}, {"email": regex}, {"role": regex}]})

    if status:
        conditions.append({"status": status})

    if role:
        conditions.append({"role": {"$regex": role, "$options": "i"}})

    query = {"$and": conditions} if len(conditions) > 1 else (conditions[0] if conditions else {})

    sort_key = [("created_at", -1)]  # newest
    if sort == "oldest":
        sort_key = [("created_at", 1)]
    elif sort == "name":
        sort_key = [("name", 1)]

    results = []
    async for doc in db.candidates.find(query).sort(sort_key):
        results.append(clean_doc(doc))
    return results


@router.get("/stats")
async def candidate_stats(db=Depends(get_db)):
    """Get candidate pipeline statistics."""
    stats = {}
    async for row in db.candidates.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]):
        stats[row["_id"]] = row["count"]

    total = await db.candidates.count_documents({})

    return {
        "total": total,
        "by_status": stats,
    }


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: int, db=Depends(get_db)):
    """Get a single candidate by ID."""
    doc = await db.candidates.find_one({"id": candidate_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return clean_doc(doc)


@router.get("/{candidate_id}/detail")
async def get_candidate_detail(candidate_id: int, db=Depends(get_db)):
    """Get full candidate profile with sessions and interviews."""
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Get sessions
    sessions = []
    async for s in db.sessions.find({"candidate_id": candidate_id}).sort("created_at", -1):
        sessions.append(clean_doc(s))

    # Get interview slots
    interviews = []
    async for s in db.interview_slots.find({"candidate_id": candidate_id}).sort("scheduled_time", -1):
        slot = clean_doc(s)
        slot["candidate_name"] = candidate["name"]
        slot["candidate_email"] = candidate["email"]
        slot["role"] = candidate["role"]
        interviews.append(slot)

    result = clean_doc(candidate)
    result["sessions"] = sessions
    result["interviews"] = interviews
    return result


@router.put("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    db=Depends(get_db),
):
    """Update candidate details."""
    existing = await db.candidates.find_one({"id": candidate_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "status" in updates and updates["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    updates["updated_at"] = datetime.utcnow().isoformat()
    await db.candidates.update_one({"id": candidate_id}, {"$set": updates})

    updated = await db.candidates.find_one({"id": candidate_id})
    await log_activity(db, "updated", "candidate", candidate_id, f"Updated: {list(updates.keys())}")
    return clean_doc(updated)


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: int, db=Depends(get_db)):
    """Delete a candidate and all related data."""
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Get session IDs for this candidate
    session_ids = []
    async for s in db.sessions.find({"candidate_id": candidate_id}):
        session_ids.append(s["id"])

    # Delete related data
    if session_ids:
        await db.messages.delete_many({"session_id": {"$in": session_ids}})
    await db.sessions.delete_many({"candidate_id": candidate_id})
    await db.interview_slots.delete_many({"candidate_id": candidate_id})
    await db.notifications.delete_many({"candidate_id": candidate_id})
    await db.candidates.delete_one({"id": candidate_id})

    await log_activity(db, "deleted", "candidate", candidate_id, f"Deleted candidate: {candidate['name']}")


@router.post("/import", status_code=201)
async def import_candidates_csv(file: UploadFile = File(...), db=Depends(get_db)):
    """Bulk import candidates from CSV. Expected columns: name, email, phone, role."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0
    errors = []

    for i, row in enumerate(reader, 1):
        name = row.get("name", "").strip()
        email = row.get("email", "").strip()
        role = row.get("role", "").strip()
        phone = row.get("phone", "").strip()

        if not name or not email or not role:
            errors.append(f"Row {i}: missing required fields")
            skipped += 1
            continue

        try:
            candidate_id = await get_next_id("candidates")
            now = datetime.utcnow().isoformat()
            await db.candidates.insert_one({
                "id": candidate_id,
                "name": name,
                "email": email,
                "phone": phone or None,
                "role": role,
                "status": "applied",
                "notes": None,
                "created_at": now,
                "updated_at": now,
            })
            imported += 1
        except DuplicateKeyError:
            skipped += 1
            errors.append(f"Row {i}: duplicate email {email}")

    await log_activity(db, "imported", "candidate", None, f"CSV import: {imported} added, {skipped} skipped")

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10],  # Return first 10 errors
    }
