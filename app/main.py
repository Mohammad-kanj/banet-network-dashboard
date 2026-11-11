"""
FastAPI Application Entry for Internet Statistics & Speed Tester.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import os

from .database import init_db
from .live_monitor import monitor
from .routes import router

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database and Start Live Monitor
    init_db()
    monitor.start()
    yield
    # Shutdown: Stop monitor
    monitor.stop()

app = FastAPI(
    title="Banet - Live Internet Statistics & Speed Tester",
    description="Real-time network telemetry, ping, jitter, packet loss, bandwidth monitor, and benchmarks.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount API routes
app.include_router(router)

# Mount static folder
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))
