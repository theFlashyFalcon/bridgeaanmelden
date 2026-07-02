from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_member_club_ids, require_auth
from app.database import get_db
from app.models import (
    Club,
    ClubEvening,
    ManualPair,
    Member,
    Registration,
    RegistrationStatus,
    Season,
)

router = APIRouter()
from app.templates_env import templates

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

    # ── Club-filtering ────────────────────────────────────────────────────────
    user_club_ids: list[int] = []
    user_clubs: list[Club] = []
    active_club_filter: int | None = None

    if current_user:
        user_club_ids = get_member_club_ids(current_user, db)
        if user_club_ids:
            user_clubs = db.query(Club).filter(Club.id.in_(user_club_ids)).order_by(Club.naam).all()
        try:
            raw_club = request.query_params.get("club", "")
            if raw_club:
                cid = int(raw_club)
                if cid in user_club_ids:
                    active_club_filter = cid
        except ValueError:
            pass

    query = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= today)  # noqa: E712
    )

    if current_user and user_club_ids:
        if active_club_filter:
            query = query.filter(ClubEvening.club_id == active_club_filter)
        else:
            query = query.filter(
                (ClubEvening.club_id.in_(user_club_ids)) | (ClubEvening.club_id.is_(None))
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

    # Club-opzoektabel voor gebruik in de template (club_id → Club)
    club_map: dict[int, Club] = {c.id: c for c in user_clubs}

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
            "user_clubs": user_clubs,
            "club_map": club_map,
            "active_club_filter": active_club_filter,
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
