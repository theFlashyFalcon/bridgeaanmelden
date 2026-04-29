from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import ClubEvening, Lid, Member, Registration

router = APIRouter(prefix="/leden")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_SORT_MAP = {
    "naam": (Member.achternaam, Member.voornaam),
    "nummer": (Member.lidnummer,),
    "mail": (Member.email,),
}


@router.get("")
async def member_list(
    request: Request,
    sort: str = "naam",
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    sort_cols = _SORT_MAP.get(sort, _SORT_MAP["naam"])
    members = (
        db.query(Member)
        .filter(Member.verwijderd_op.is_(None))
        .order_by(*sort_cols)
        .all()
    )
    lid_nummers = {l.nbb_nummer for l in db.query(Lid.nbb_nummer).all() if l.nbb_nummer}
    return templates.TemplateResponse(
        request,
        "members/list.html",
        {
            "current_user": current_user,
            "members": members,
            "sort_by": sort,
            "lid_nummers": lid_nummers,
        },
    )


@router.get("/{member_id}")
async def member_detail(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404)

    registrations = (
        db.query(Registration)
        .filter(
            or_(
                Registration.person1_id == member_id,
                Registration.person2_id == member_id,
            )
        )
        .join(ClubEvening)
        .order_by(ClubEvening.datum.desc())
        .all()
    )

    lid_match = (
        db.query(Lid)
        .filter(Lid.nbb_nummer == member.lidnummer)
        .first()
    )

    return templates.TemplateResponse(
        request,
        "members/detail.html",
        {
            "current_user": current_user,
            "member": member,
            "registrations": registrations,
            "lid_match": lid_match,
        },
    )


@router.post("/{member_id}/verwijder")
async def member_verwijder(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if member and member.id != current_user.id:
        member.verwijderd_op = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url="/leden?verwijderd=1", status_code=302)
