"""
Authentication routes: signup, login, and current user profile.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from app.schemas import UserSignUp, UserLogin, UserOut, AuthResponse
from app.database import get_db, get_next_id, clean_doc, log_activity
from app.auth_utils import hash_password, verify_password, create_access_token, get_current_user
from pymongo.errors import DuplicateKeyError
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(payload: UserSignUp, db=Depends(get_db)):
    """Register a new user (candidate or recruiter)."""

    # Validate passwords match
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    if payload.role not in ("candidate", "recruiter"):
        raise HTTPException(status_code=400, detail="Role must be 'candidate' or 'recruiter'.")

    # Check if email already exists
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # Create user
    user_id = await get_next_id("users")
    now = datetime.utcnow().isoformat()
    user_doc = {
        "id": user_id,
        "name": payload.name,
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "role": payload.role,
        "created_at": now,
    }

    try:
        await db.users.insert_one(user_doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # If candidate, also create a candidate record
    candidate_id = None
    if payload.role == "candidate":
        candidate_id = await get_next_id("candidates")
        candidate_doc = {
            "id": candidate_id,
            "name": payload.name,
            "email": payload.email.lower(),
            "phone": None,
            "role": "General",
            "status": "applied",
            "notes": None,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await db.candidates.insert_one(candidate_doc)
        except DuplicateKeyError:
            # Link to existing candidate record
            existing_cand = await db.candidates.find_one({"email": payload.email.lower()})
            if existing_cand:
                candidate_id = existing_cand["id"]
                await db.candidates.update_one(
                    {"id": candidate_id}, {"$set": {"user_id": user_id}}
                )

    await log_activity(db, "signup", "user", user_id, f"New {payload.role}: {payload.name}")

    # Generate token
    token = create_access_token({
        "user_id": user_id,
        "email": payload.email.lower(),
        "role": payload.role,
        "name": payload.name,
        "candidate_id": candidate_id,
    })

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut(
            id=user_id,
            name=payload.name,
            email=payload.email.lower(),
            role=payload.role,
            candidate_id=candidate_id,
            created_at=now,
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: UserLogin, db=Depends(get_db)):
    """Authenticate a user with email and password."""
    user = await db.users.find_one({"email": payload.email.lower()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # If candidate, find their candidate_id
    candidate_id = None
    if user["role"] == "candidate":
        candidate = await db.candidates.find_one({"user_id": user["id"]})
        if candidate:
            candidate_id = candidate["id"]

    # Generate token
    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "candidate_id": candidate_id,
    })

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user["role"],
            candidate_id=candidate_id,
            created_at=user["created_at"],
        ),
    )


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Validate token and return current user profile."""
    user = await db.users.find_one({"id": current_user["user_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    candidate_id = None
    if user["role"] == "candidate":
        candidate = await db.candidates.find_one({"user_id": user["id"]})
        if candidate:
            candidate_id = candidate["id"]

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "candidate_id": candidate_id,
        "created_at": user["created_at"],
    }
