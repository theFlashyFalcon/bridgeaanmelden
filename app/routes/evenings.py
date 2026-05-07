from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_auth
from app.database import get_db
from app.models import (
    ClubEvening,
    ManualPair,
    Member,
    Registration,
    RegistrationStatus,
    Season,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Mapping URL-type-sleutel → DB-waarden
_TYPE_MAP: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "avondeten": ["eten voor jeugdtraining"],
    "training": ["jeugdtraining", "training"],
    "speciaal": ["speciaal"],
}


@router.get("/")
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[Member] = Depends(get_current_user),
):
    today = date.today()
    active_filter = request.query_params.get("type", "")

    hidden_types: list[str] = []
    if current_user and current_user.verborgen_types:
        hidden_types = [t for t in current_user.verborgen_types.split(",") if t]

    query = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= today)  # noqa: E712
    )

    if active_filter and active_filter in _TYPE_MAP:
        query = query.filter(ClubEvening.type.in_(_TYPE_MAP[active_filter]))
    elif not active_filter and hidden_types:
        all_hidden_db: list[str] = []
        for key in hidden_types:
            all_hidden_db.extend(_TYPE_MAP.get(key, []))
        if all_hidden_db:
            query = query.filter(ClubEvening.type.notin_(all_hidden_db))

    evenings = query.order_by(ClubEvening.datum).limit(30).all()

    user_regs: dict[int, Registration] = {}
    if current_user:
        evening_ids = [e.id for e in evenings]
        regs1 = (
            db.query(Registration)
            .filter(
                Registration.person1_id == current_user.id,
                Registration.evening_id.in_(evening_ids),
                Registration.status != RegistrationStatus.afgemeld,
            )
            .all()
        )
        regs2 = (
            db.query(Registration)
            .filter(
                Registration.person2_id == current_user.id,
                Registration.evening_id.in_(evening_ids),
                Registration.status != RegistrationStatus.afgemeld,
            )
            .all()
        )
        for reg in regs1 + regs2:
            user_regs[reg.evening_id] = reg

    termijn_deadlines: dict[int, datetime] = {}
    for e in evenings:
        if e.inschrijftermijn_uren:
            deadline = datetime.combine(e.datum, datetime.min.time()) - timedelta(hours=e.inschrijftermijn_uren)
            termijn_deadlines[e.id] = deadline

    welkom = request.session.pop("welkom", False)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "current_user": current_user,
            "evenings": evenings,
            "user_regs": user_regs,
            "welkom": welkom,
            "active_filter": active_filter,
            "hidden_types": hidden_types,
            "termijn_deadlines": termijn_deadlines,
        },
    )


@router.get("/offline")
async def offline(request: Request):
    return templates.TemplateResponse(request, "offline.html", {})


@router.get("/deelnemers/{event_id}")
async def deelnemers(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    registrations = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.status != RegistrationStatus.afgemeld,
        )
        .all()
    )

    manual_pairs = (
        db.query(ManualPair)
        .filter(ManualPair.evening_id == event_id)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "deelnemers.html",
        {
            "current_user": current_user,
            "evening": evening,
            "registrations": registrations,
            "manual_pairs": manual_pairs,
        },
    )
