from contextlib import asynccontextmanager
from pathlib import Path
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.database.mongo import connect_db, close_db, ensure_indexes
from app.api.routes import health, auth, clients, products, conversations, instagram, test_api, search, admin, catalogue_options

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
    version="3.0.0",
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

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/dashboard", StaticFiles(directory=frontend_dir / "client", html=True), name="dashboard")
app.mount("/admin", StaticFiles(directory=frontend_dir / "admin", html=True), name="admin")
