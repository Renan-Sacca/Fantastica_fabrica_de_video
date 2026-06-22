from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import TEMPLATES_DIR
from app.repositories import jobs as jobs_repo
from app.video_types import all_video_types

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    jobs = jobs_repo.get_all_jobs(user_id=user["id"])
    video_types = all_video_types()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "jobs": jobs, "video_types": video_types, "user": user},
    )
