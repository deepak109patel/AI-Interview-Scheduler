"""
Vercel Serverless Function entry point.
Exports the FastAPI app instance for Vercel's Python runtime.
"""
from app.main import app

# Vercel expects the ASGI app to be named `app` or `handler`
# FastAPI is ASGI-compatible, so this just works.
