from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import (
    get_wedstrijdleider_clubs,
    require_admin,
    require_wedstrijdleider,
    sync_global_role,
)
from app.database import get_db
from app.models import Club, ClubEvening, Lid, Member, MemberClub, MemberRole, Registration

router = APIRouter(prefix="/leden")
from app.templates_env import templates


def _kan_lid_beheren(current_user: Member, member: Member, db: Session) -> bool:
    """WL's mogen alleen leden beheren waarmee ze een club delen; admins alles."""
    if current_user.role == MemberRole.admin.value:
        return True
    member_club_ids = {
        mc.club_id
        for mc in db.query(MemberClub).filter(MemberClub.member_id == member.id).all()
    }
    if not member_club_ids:
        return True  # legacy lid zonder clubkoppeling
    beheer_ids = {c.id for c in get_wedstrijdleider_clubs(current_user, db)}
    if not beheer_ids and current_user.role == MemberRole.wedstrijdleider.value:
        return True  # legacy globale WL zonder clubkoppelingen
    return bool(member_club_ids & beheer_ids)

_SORT_MAP = {
    "naam": (Member.achternaam, Member.voornaam),
    "nummer": (Member.lidnummer,),
    "mail": (Member.email,),
}


@router.get("")
async def member_list(
    request: Request,
    sort: str = "naam",
    club: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    sort_cols = _SORT_MAP.get(sort, _SORT_MAP["naam"])
    clubs = db.query(Club).order_by(Club.naam).all()

    active_club: Optional[Club] = None
    q = db.query(Member).filter(Member.verwijderd_op.is_(None))

    if club:
        active_club = db.query(Club).filter(Club.id == club).first()
        if active_club:
            member_ids = [
                mc.member_id
                for mc in db.query(MemberClub).filter(MemberClub.club_id == club).all()
            ]
            if member_ids:
                q = q.filter(Member.id.in_(member_ids))
            else:
                q = q.filter(Member.id.is_(None))

    members = q.order_by(*sort_cols).all()
    lid_nummers = {l.nbb_nummer for l in db.query(Lid.nbb_nummer).all() if l.nbb_nummer}

    return templates.TemplateResponse(
        request,
        "members/list.html",
        {
            "current_user": current_user,
            "members": members,
            "sort_by": sort,
            "lid_nummers": lid_nummers,
            "clubs": clubs,
            "active_club": active_club,
        },
    )


@router.get("/{member_id}")
async def member_detail(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404)
    if not _kan_lid_beheren(current_user, member, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot dit lid")

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

    club_memberships = (
        db.query(MemberClub)
        .filter(MemberClub.member_id == member_id)
        .all()
    )
    club_ids = [mc.club_id for mc in club_memberships]
    club_map = {
        c.id: c for c in db.query(Club).filter(Club.id.in_(club_ids)).all()
    } if club_ids else {}
    club_membership_map = {mc.club_id: mc for mc in club_memberships}

    # Clubs waarvan dit lid eventueel wedstrijdleider gemaakt kan worden; de
    # algemene club kan uitsluitend door globale admins beheerd worden en
    # wordt hier dus nooit als optie getoond.
    clubs = (
        db.query(Club)
        .filter(Club.is_algemeen == False)  # noqa: E712
        .order_by(Club.naam)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "members/detail.html",
        {
            "current_user": current_user,
            "member": member,
            "registrations": registrations,
            "lid_match": lid_match,
            "club_memberships": club_memberships,
            "club_map": club_map,
            "club_membership_map": club_membership_map,
            "clubs": clubs,
        },
    )


@router.post("/{member_id}/rol")
async def member_rol_wijzigen(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    """
    Zet de globale rol van een lid: lid of admin. Wedstrijdleiderschap is
    altijd per club en loopt via de club-ledenbeheerroutes (/beheer/clubs/...).
    """
    form = await request.form()
    role = form.get("role", "").strip()
    if role not in (MemberRole.lid.value, MemberRole.admin.value):
        return RedirectResponse(url=f"/leden/{member_id}?fout=rol", status_code=302)

    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404)

    if role == MemberRole.admin.value:
        member.role = MemberRole.admin.value
    else:
        # Niet blind op 'lid' zetten: als dit lid nog per-club wedstrijdleider
        # is, moet de globale rol dat blijven weerspiegelen.
        sync_global_role(member, db)
    db.commit()
    return RedirectResponse(url=f"/leden/{member_id}?opgeslagen=1", status_code=302)


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


@router.post("/{member_id}/training-toggle")
async def member_training_toggle(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404)
    if not _kan_lid_beheren(current_user, member, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot dit lid")
    member.training_eligible = not member.training_eligible
    db.commit()
    return RedirectResponse(url=f"/leden/{member_id}", status_code=302)
