from contextlib import asynccontextmanager
from pathlib import Path
import logging
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.database.mongo import connect_db, close_db, ensure_indexes
from app.api.routes import health, auth, clients, products, conversations, instagram, test_api, search, admin, catalogue_options, knowledge, ai_analytics

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await ensure_indexes()
    from app.services.admin_bootstrap import ensure_admin
    await ensure_admin()
    yield
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version="3.1.0",
    description="Production-oriented Instagram DM automation for clothing businesses.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(products.router)
app.include_router(conversations.router)
app.include_router(instagram.router)
app.include_router(test_api.router)
app.include_router(search.router)
app.include_router(admin.router)
app.include_router(catalogue_options.router)
app.include_router(knowledge.router)
app.include_router(ai_analytics.router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/dashboard", StaticFiles(directory=frontend_dir / "client", html=True), name="dashboard")
app.mount("/admin", StaticFiles(directory=frontend_dir / "admin", html=True), name="admin")


@app.get("/", include_in_schema=False)
async def domain_home(request: Request):
    """Send each custom hostname to its matching UI; keep the API host as a health landing."""
    host = request.headers.get("host", "").split(":", 1)[0].lower().rstrip(".")
    if host == "ig-app.meridin.in":
        return RedirectResponse(url="/dashboard/", status_code=307)
    if host == "ig-admin.meridin.in":
        return RedirectResponse(url="/admin/", status_code=307)
    return {"status": "ok", "service": "meridin-instagram", "api": "/docs"}
