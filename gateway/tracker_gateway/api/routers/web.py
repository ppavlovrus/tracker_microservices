"""Web UI router for Task Tracker."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ...config import YANDEX_OAUTH_ENABLED

router = APIRouter(tags=["Web UI"])

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    return templates.TemplateResponse(request, "index.html")


@router.get("/web/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(request, "login.html", {"yandex_oauth_enabled": YANDEX_OAUTH_ENABLED})


@router.get("/web/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    """Tasks page."""
    return templates.TemplateResponse(request, "tasks.html")
