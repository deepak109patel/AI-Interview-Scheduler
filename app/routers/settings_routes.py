from __future__ import annotations

from fastapi import APIRouter, Depends
from app.schemas import SettingsUpdate, ApiKeyTest
from app.database import get_db
import aiosqlite

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("/")
async def get_settings(db: aiosqlite.Connection = Depends(get_db)):
    """Get all settings."""
    cur = await db.execute("SELECT key, value FROM settings")
    rows = await cur.fetchall()
    return {row["key"]: row["value"] for row in rows}


@router.put("/")
async def update_settings(payload: SettingsUpdate, db: aiosqlite.Connection = Depends(get_db)):
    """Update settings."""
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    for key, value in updates.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )
    await db.commit()
    return {"message": "Settings updated", "updated": list(updates.keys())}


@router.post("/test-key")
async def test_api_key(payload: ApiKeyTest):
    """Test if a Gemini API key is valid."""
    try:
        from google import genai
        client = genai.Client(api_key=payload.api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say 'API key is valid' in exactly those words.",
        )
        return {"valid": True, "message": response.text.strip()[:100]}
    except Exception as e:
        return {"valid": False, "message": str(e)[:200]}
