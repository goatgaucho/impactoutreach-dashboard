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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schedule daily sends at 8:55 AM ET
    scheduler.add_job(
        schedule_daily_sends,
        CronTrigger(hour=8, minute=55, timezone="America/Toronto"),
        id="schedule_daily_sends",
        replace_existing=True,
    )

    # Execute pending sends every 5 minutes
    scheduler.add_job(
        execute_pending_sends,
        "interval",
        minutes=5,
        id="execute_pending_sends",
        replace_existing=True,
    )

    # Daily summary at 5 PM ET
    scheduler.add_job(
        daily_summary,
        CronTrigger(hour=17, minute=0, timezone="America/Toronto"),
        id="daily_summary",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started with 3 jobs")
    yield
    scheduler.shutdown()
    logger.info("APScheduler shut down")


app = FastAPI(title="ImpactOutreach Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

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
