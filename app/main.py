import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.auth import create_session_token, SESSION_COOKIE
from app.routes import dashboard, constituents, sends, webhooks, api
from app.services.scheduler import schedule_daily_sends, execute_pending_sends, daily_summary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
scheduler = AsyncIOScheduler()


def run_migrations():
    """Run Alembic migrations on startup."""
    try:
        from alembic.config import Config
        from alembic import command
        import os

        alembic_cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations complete")
    except Exception:
        logger.exception("Failed to run migrations")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting lifespan...")

    # Run database migrations
    run_migrations()
    logger.info("Migrations done, setting up scheduler...")

    # Schedule daily sends at 8:55 AM ET
    # misfire_grace_time=3600 ensures the job still runs if the app was down at 8:55
    scheduler.add_job(
        schedule_daily_sends,
        CronTrigger(hour=8, minute=55, timezone="America/Toronto"),
        id="schedule_daily_sends",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Execute pending sends every 5 minutes
    scheduler.add_job(
        execute_pending_sends,
        "interval",
        minutes=5,
        id="execute_pending_sends",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Daily summary at 5 PM ET
    scheduler.add_job(
        daily_summary,
        CronTrigger(hour=17, minute=0, timezone="America/Toronto"),
        id="daily_summary",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("APScheduler started with 3 jobs")

    # Catch-up: run schedule_daily_sends on startup in case the 8:55 AM job was missed
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/Toronto"))
    if now_et.hour >= 9:
        logger.info("Running catch-up schedule_daily_sends (app started after 9 AM ET)...")
        try:
            schedule_daily_sends()
            logger.info("Catch-up scheduling complete")
        except Exception:
            logger.exception("Catch-up scheduling failed")

    logger.info("Lifespan startup complete")
    yield
    scheduler.shutdown()
    logger.info("APScheduler shut down")


app = FastAPI(title="ImpactOutreach Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(f"Internal Server Error: {exc}", status_code=500)

# Include routers
app.include_router(dashboard.router)
app.include_router(constituents.router)
app.include_router(sends.router)
app.include_router(webhooks.router)
app.include_router(api.router, prefix="/api")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        token = create_session_token(username)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=86400,
        )
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid username or password",
    })


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.api_route("/admin/trigger-scheduler", methods=["GET", "POST"])
def trigger_scheduler(request: Request, key: str = ""):
    """Manually trigger the send scheduling + executor for testing."""
    if key != settings.APP_SECRET_KEY:
        from app.auth import auth_redirect_if_needed
        redirect = auth_redirect_if_needed(request)
        if redirect:
            return {"error": "Not authenticated. Pass ?key=APP_SECRET_KEY"}

    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.database import SessionLocal
    from app.models import Send

    logger.info("Manually triggering scheduler...")
    schedule_daily_sends()

    # For testing: override all scheduled sends to fire NOW
    db = SessionLocal()
    try:
        now = datetime.now(ZoneInfo("America/Toronto"))
        pending = db.query(Send).filter(Send.status == "scheduled").all()
        for s in pending:
            s.scheduled_time = now
        db.commit()
        logger.info(f"Overrode {len(pending)} sends to fire now")
    finally:
        db.close()

    logger.info("Running executor...")
    execute_pending_sends()
    logger.info("Executor done.")
    return {"status": "ok", "message": f"Scheduler triggered, {len(pending)} sends queued and executor run"}
