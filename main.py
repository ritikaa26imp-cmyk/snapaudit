"""
SnapAudit FastAPI entrypoint.

Run locally::

    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from snapaudit.api.routes import router
from snapaudit.audit.log import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ensure the SQLite schema exists before serving traffic."""
    await init_db()
    yield


app = FastAPI(
    title="SnapAudit",
    description="AI-assisted product swap detection for e-commerce",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
