from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ─── Candidate Schemas ────────────────────────────────────────────────────────

class CandidateCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    role: str

class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class CandidateOut(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str]
    role: str
    status: str = "applied"
    notes: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

class CandidateDetail(CandidateOut):
    sessions: List[SessionOut] = []
    interviews: List[SlotOut] = []


# ─── Session Schemas ──────────────────────────────────────────────────────────

class SessionStart(BaseModel):
    candidate_id: int

class SessionOut(BaseModel):
    id: str
    candidate_id: int
    status: str
    created_at: str


# ─── Message / Chat Schemas ───────────────────────────────────────────────────

class ChatMessage(BaseModel):
    message: str

class MessageOut(BaseModel):
    role: str
    content: str
    created_at: str

class ChatResponse(BaseModel):
    reply: str
    session_status: str
    scheduled_time: Optional[str] = None


# ─── Interview Slot Schemas ───────────────────────────────────────────────────

class SlotOut(BaseModel):
    id: int
    session_id: str
    candidate_id: int
    candidate_name: str = ""
    candidate_email: str = ""
    role: str = ""
    scheduled_time: str
    duration_minutes: int
    location: str
    status: str
    notes: Optional[str]
    created_at: str


# ─── Dashboard / Analytics Schemas ────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_candidates: int
    active_sessions: int
    interviews_scheduled: int
    interviews_cancelled: int
    completion_rate: float
    candidates_by_status: dict

class TimelineEvent(BaseModel):
    id: int
    candidate_name: str
    role: str
    scheduled_time: str
    duration_minutes: int
    status: str

class ActivityItem(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: Optional[int]
    details: Optional[str]
    created_at: str


# ─── Calendar Schemas ─────────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    id: int
    candidate_name: str
    candidate_email: str
    role: str
    scheduled_time: str
    duration_minutes: int
    location: str
    status: str
    notes: Optional[str]

class RescheduleRequest(BaseModel):
    new_datetime: str


# ─── Notification Schemas ─────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    candidate_id: int
    candidate_name: str = ""
    type: str
    subject: str
    body: str
    status: str
    created_at: str

class NotificationCreate(BaseModel):
    candidate_id: int
    subject: str
    body: str
    type: str = "email"


# ─── Settings Schemas ─────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    company_name: str = "TechCorp"
    recruiter_name: str = "Alex"
    timezone: str = "Asia/Kolkata"
    interview_duration: str = "45"
    interview_location: str = "Google Meet link will be sent via email"
    buffer_minutes: str = "15"
    ai_tone: str = "friendly"

class SettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    recruiter_name: Optional[str] = None
    timezone: Optional[str] = None
    interview_duration: Optional[str] = None
    interview_location: Optional[str] = None
    buffer_minutes: Optional[str] = None
    ai_tone: Optional[str] = None

class ApiKeyTest(BaseModel):
    api_key: str


# ─── Export Schemas ───────────────────────────────────────────────────────────

class ExportFilter(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None


# ─── Authentication Schemas ───────────────────────────────────────────────────

class UserSignUp(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str
    role: str  # "candidate" or "recruiter"

class UserLogin(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    candidate_id: Optional[int] = None
    created_at: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# Fix forward references
CandidateDetail.model_rebuild()
