from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import jobs_store
from app.config import TEMPLATES_DIR
from app.video_types import all_video_types

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal."""
    jobs = jobs_store.get_all_jobs()
    video_types = all_video_types()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "jobs": jobs, "video_types": video_types},
    )
