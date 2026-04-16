from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from app.schemas import CandidateCreate, CandidateOut, CandidateUpdate
from app.database import get_db, log_activity
import aiosqlite
import csv
import io

router = APIRouter(prefix="/candidates", tags=["Candidates"])

VALID_STATUSES = {"applied", "screening", "interview", "hired", "rejected"}


@router.post("/", response_model=CandidateOut, status_code=201)
async def add_candidate(payload: CandidateCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Add a new candidate to the system."""
    try:
        cursor = await db.execute(
            "INSERT INTO candidates (name, email, phone, role) VALUES (?, ?, ?, ?)",
            (payload.name, payload.email, payload.phone, payload.role),
        )
        await db.commit()
        row = await db.execute(
            "SELECT * FROM candidates WHERE id = ?", (cursor.lastrowid,)
        )
        candidate = await row.fetchone()
        await log_activity(db, "created", "candidate", cursor.lastrowid, f"Added candidate: {payload.name}")
        return dict(candidate)
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail="A candidate with this email already exists.")


@router.get("/", response_model=list[CandidateOut])
async def list_candidates(
    search: str = Query(None, description="Search by name, email, or role"),
    status: str = Query(None, description="Filter by status"),
    role: str = Query(None, description="Filter by role"),
    sort: str = Query("newest", description="Sort: newest, oldest, name"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all candidates with optional search and filters."""
    query = "SELECT * FROM candidates WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE ? OR email LIKE ? OR role LIKE ?)"
        params.extend([f"%{search}%"] * 3)

    if status:
        query += " AND status = ?"
        params.append(status)

    if role:
        query += " AND role LIKE ?"
        params.append(f"%{role}%")

    if sort == "oldest":
        query += " ORDER BY created_at ASC"
    elif sort == "name":
        query += " ORDER BY name ASC"
    else:
        query += " ORDER BY created_at DESC"

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/stats")
async def candidate_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Get candidate pipeline statistics."""
    cursor = await db.execute(
        "SELECT status, COUNT(*) as count FROM candidates GROUP BY status"
    )
    rows = await cursor.fetchall()
    stats = {row["status"]: row["count"] for row in rows}

    total = await db.execute("SELECT COUNT(*) as cnt FROM candidates")
    total_row = await total.fetchone()

    return {
        "total": total_row["cnt"],
        "by_status": stats,
    }


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single candidate by ID."""
    cursor = await db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return dict(row)


@router.get("/{candidate_id}/detail")
async def get_candidate_detail(candidate_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get full candidate profile with sessions and interviews."""
    cursor = await db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    candidate = await cursor.fetchone()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Get sessions
    sess_cur = await db.execute(
        "SELECT * FROM sessions WHERE candidate_id = ? ORDER BY created_at DESC",
        (candidate_id,),
    )
    sessions = [dict(s) for s in await sess_cur.fetchall()]

    # Get interview slots
    slot_cur = await db.execute(
        """SELECT sl.*, c.name AS candidate_name, c.email AS candidate_email, c.role
           FROM interview_slots sl JOIN candidates c ON sl.candidate_id = c.id
           WHERE sl.candidate_id = ? ORDER BY sl.scheduled_time DESC""",
        (candidate_id,),
    )
    interviews = [dict(s) for s in await slot_cur.fetchall()]

    return {
        **dict(candidate),
        "sessions": sessions,
        "interviews": interviews,
    }


@router.put("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update candidate details."""
    cursor = await db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Candidate not found.")

    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "status" in updates and updates["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [candidate_id]

    await db.execute(
        f"UPDATE candidates SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values,
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    row = await cursor.fetchone()
    await log_activity(db, "updated", "candidate", candidate_id, f"Updated: {list(updates.keys())}")
    return dict(row)


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a candidate and all related data."""
    cursor = await db.execute("SELECT name FROM candidates WHERE id = ?", (candidate_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    await db.execute("DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE candidate_id = ?)", (candidate_id,))
    await db.execute("DELETE FROM sessions WHERE candidate_id = ?", (candidate_id,))
    await db.execute("DELETE FROM interview_slots WHERE candidate_id = ?", (candidate_id,))
    await db.execute("DELETE FROM notifications WHERE candidate_id = ?", (candidate_id,))
    await db.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
    await db.commit()
    await log_activity(db, "deleted", "candidate", candidate_id, f"Deleted candidate: {row['name']}")


@router.post("/import", status_code=201)
async def import_candidates_csv(file: UploadFile = File(...), db: aiosqlite.Connection = Depends(get_db)):
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
            await db.execute(
                "INSERT INTO candidates (name, email, phone, role) VALUES (?, ?, ?, ?)",
                (name, email, phone or None, role),
            )
            imported += 1
        except aiosqlite.IntegrityError:
            skipped += 1
            errors.append(f"Row {i}: duplicate email {email}")

    await db.commit()
    await log_activity(db, "imported", "candidate", None, f"CSV import: {imported} added, {skipped} skipped")

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10],  # Return first 10 errors
    }
