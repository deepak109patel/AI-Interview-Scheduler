from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "interview_scheduler")

client = AsyncIOMotorClient(MONGODB_URL)
database = client[DB_NAME]

DEFAULT_SETTINGS = {
    "company_name": "TechCorp",
    "recruiter_name": "Alex",
    "timezone": "Asia/Kolkata",
    "interview_duration": "45",
    "interview_location": "Google Meet link will be sent via email",
    "buffer_minutes": "15",
    "ai_tone": "friendly",
}


def clean_doc(doc):
    """Remove MongoDB's _id field from a document for JSON serialization."""
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


async def get_db():
    """Dependency that yields the MongoDB database instance."""
    yield database


async def get_next_id(collection_name: str) -> int:
    """Auto-increment integer ID using a counters collection."""
    result = await database.counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return result["seq"]


async def init_db():
    """Create indexes and seed default settings."""
    # Candidate indexes
    await database.candidates.create_index("id", unique=True)
    await database.candidates.create_index("email", unique=True)
    await database.candidates.create_index("status")

    # Session indexes
    await database.sessions.create_index("id", unique=True)
    await database.sessions.create_index("candidate_id")

    # Message indexes
    await database.messages.create_index("id", unique=True)
    await database.messages.create_index("session_id")

    # Interview slot indexes
    await database.interview_slots.create_index("id", unique=True)
    await database.interview_slots.create_index("candidate_id")
    await database.interview_slots.create_index("scheduled_time")

    # Notification indexes
    await database.notifications.create_index("id", unique=True)
    await database.notifications.create_index("candidate_id")

    # Activity log indexes
    await database.activity_log.create_index("id", unique=True)
    await database.activity_log.create_index("created_at")

    # User indexes (authentication)
    await database.users.create_index("id", unique=True)
    await database.users.create_index("email", unique=True)

    # Settings indexes
    await database.settings.create_index("key", unique=True)

    # Seed default settings if empty
    count = await database.settings.count_documents({})
    if count == 0:
        now = datetime.utcnow().isoformat()
        for key, value in DEFAULT_SETTINGS.items():
            await database.settings.update_one(
                {"key": key},
                {"$setOnInsert": {"key": key, "value": value, "updated_at": now}},
                upsert=True,
            )


async def log_activity(db, action: str, entity_type: str, entity_id: int = None, details: str = None):
    """Log an activity event."""
    activity_id = await get_next_id("activity_log")
    await db.activity_log.insert_one({
        "id": activity_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "created_at": datetime.utcnow().isoformat(),
    })
