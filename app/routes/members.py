from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Member

router = APIRouter(prefix="/leden")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def member_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    members = db.query(Member).order_by(Member.achternaam, Member.voornaam).all()
    return templates.TemplateResponse(
        request,
        "members/list.html",
        {"current_user": current_user, "members": members},
    )
