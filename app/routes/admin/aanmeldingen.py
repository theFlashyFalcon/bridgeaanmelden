"""Beheer: aanmeldingsoverzichten, af/aanmeldingen, partnerverzoeken en aanwezigheid."""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    can_manage_club,
    get_admin_club,
    is_member_of_club,
    require_auth,
    require_wedstrijdleider,
)
from app.database import get_db
from app.models import (
    ClubEvening,
    ManualPair,
    Member,
    MemberClub,
    MemberRole,
    PartnerRequest,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
)
from app.templates_env import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beheer")


# ── Aanmeldingenoverzicht (Wedstrijdleider + Admin) ───────────────────────────

@router.get("/aanmeldingen")
async def aanmeldingen_overview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = get_admin_club(current_user, db, request)
    q = db.query(ClubEvening).join(Season).filter(
        Season.actief == True, ClubEvening.datum >= date.today()  # noqa: E712
    )
    if club:
        q = q.filter(ClubEvening.club_id == club.id)
    evenings = q.order_by(ClubEvening.datum).all()
    return templates.TemplateResponse(
        request,
        "admin/aanmeldingen.html",
        {"current_user": current_user, "evenings": evenings},
    )


@router.get("/aanmeldingen/{event_id}")
async def aanmeldingen_detail(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")
    if not is_member_of_club(current_user, evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen lid van deze club")

    all_regs = (
        db.query(Registration)
        .filter(Registration.evening_id == event_id)
        .order_by(Registration.gewijzigd_op.desc())
        .all()
    )

    active = [r for r in all_regs if r.status != RegistrationStatus.afgemeld]
    recent_changes = all_regs[:10]
    dtype_detail = evening.deelnemers_type or "paren"

    if dtype_detail == "viertallen":
        volledig = [r for r in active if r.partner_naam and r.partner2_naam and r.partner3_naam]
        loslopers = [r for r in active if r not in volledig]
    elif dtype_detail == "individueel":
        volledig = list(active)
        loslopers = []
    else:
        volledig = [r for r in active if (r.person2_id or r.partner_naam) and r.status != RegistrationStatus.beschikbaar_solo]
        loslopers = [r for r in active if r not in volledig]

    return templates.TemplateResponse(
        request,
        "admin/event_detail.html",
        {
            "current_user": current_user,
            "evening": evening,
            "active": active,
            "volledig": volledig,
            "recent_changes": recent_changes,
            "loslopers": loslopers,
            "dtype": dtype_detail,
        },
    )


# ── Loslopers (Wedstrijdleider + Admin) ───────────────────────────────────────

@router.get("/loslopers")
async def loslopers(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = get_admin_club(current_user, db, request)
    q = db.query(Registration).join(ClubEvening, Registration.evening_id == ClubEvening.id).filter(
        Registration.status == RegistrationStatus.beschikbaar_solo
    )
    if club:
        q = q.filter(ClubEvening.club_id == club.id)
    solo = q.all()
    return templates.TemplateResponse(
        request,
        "admin/loslopers.html",
        {"current_user": current_user, "solo_registrations": solo},
    )


# ── Af/aanmeldingen beheren (Wedstrijdleider + Admin) ────────────────────────

_AF_TYPE_MAP: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "avondeten": ["eten voor jeugdtraining"],
    "training": ["jeugdtraining", "training"],
    "speciaal": ["speciaal"],
}


@router.get("/af-aanmeldingen")
async def af_aanmeldingen_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = get_admin_club(current_user, db, request)
    active_filter = request.query_params.get("type", "")
    query = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= date.today())  # noqa: E712
        .order_by(ClubEvening.datum)
    )
    if club:
        query = query.filter(ClubEvening.club_id == club.id)
    if active_filter and active_filter in _AF_TYPE_MAP:
        query = query.filter(ClubEvening.type.in_(_AF_TYPE_MAP[active_filter]))
    evenings = query.all()

    open_requests = {}
    for e in evenings:
        open_requests[e.id] = (
            db.query(PartnerRequest)
            .filter(PartnerRequest.evening_id == e.id, PartnerRequest.status == "wachtend")
            .count()
        )
    return templates.TemplateResponse(
        request,
        "admin/af_aanmeldingen.html",
        {
            "current_user": current_user,
            "evenings": evenings,
            "open_requests": open_requests,
            "active_filter": active_filter if active_filter in _AF_TYPE_MAP else "",
        },
    )


@router.get("/af-aanmeldingen/{event_id}")
async def af_aanmeldingen_detail(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")
    if not can_manage_club(current_user, evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")

    all_regs = (
        db.query(Registration)
        .filter(Registration.evening_id == event_id)
        .all()
    )

    dtype = evening.deelnemers_type or "paren"

    if dtype == "individueel":
        volledig_aangemeld = [r for r in all_regs if r.status == RegistrationStatus.aangemeld]
        loslopers = []
    elif dtype == "viertallen":
        volledig_aangemeld = [
            r for r in all_regs
            if r.status == RegistrationStatus.aangemeld and r.partner_naam and r.partner2_naam and r.partner3_naam
        ]
        loslopers = [
            r for r in all_regs
            if r.status in (RegistrationStatus.beschikbaar_solo, RegistrationStatus.aangemeld)
            and r not in volledig_aangemeld
            and r.status != RegistrationStatus.afgemeld
        ]
    else:  # paren
        volledig_aangemeld = [
            r for r in all_regs
            if r.status == RegistrationStatus.aangemeld and (r.partner_naam or r.person2_id)
        ]
        loslopers = [
            r for r in all_regs
            if r.status == RegistrationStatus.beschikbaar_solo
            or (r.status == RegistrationStatus.aangemeld and not r.partner_naam and not r.person2_id)
        ]

    afgemeld = [r for r in all_regs if r.status == RegistrationStatus.afgemeld]
    all_manual = (
        db.query(ManualPair)
        .filter(ManualPair.evening_id == event_id)
        .order_by(ManualPair.aangemaakt_op)
        .all()
    )

    if dtype == "individueel":
        manual_aangemeld = all_manual
        manual_loslopers = []
    elif dtype == "viertallen":
        manual_aangemeld = [p for p in all_manual if p.naam_4]
        manual_loslopers = [p for p in all_manual if not p.naam_4]
    else:
        manual_aangemeld = [p for p in all_manual if p.naam_2]
        manual_loslopers = [p for p in all_manual if not p.naam_2]

    verzoeken = (
        db.query(PartnerRequest)
        .filter(PartnerRequest.evening_id == event_id)
        .order_by(PartnerRequest.aangemaakt_op)
        .all()
    )

    te_laat_regs = [r for r in all_regs if r.te_laat and r.status != RegistrationStatus.afgemeld]

    return templates.TemplateResponse(
        request,
        "admin/af_aanmeldingen_detail.html",
        {
            "current_user": current_user,
            "evening": evening,
            "volledig_aangemeld": volledig_aangemeld,
            "afgemeld": afgemeld,
            "loslopers": loslopers,
            "manual_aangemeld": manual_aangemeld,
            "manual_loslopers": manual_loslopers,
            "verzoeken": verzoeken,
            "te_laat_regs": te_laat_regs,
            "dtype": dtype,
        },
    )


@router.get("/af-aanmeldingen/{event_id}/print")
async def af_aanmeldingen_print(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")
    if not can_manage_club(current_user, evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")

    all_regs = db.query(Registration).filter(Registration.evening_id == event_id).all()
    dtype_print = evening.deelnemers_type or "paren"
    if dtype_print == "viertallen":
        volledig_aangemeld = [r for r in all_regs if r.status == RegistrationStatus.aangemeld and r.partner_naam and r.partner2_naam and r.partner3_naam]
    elif dtype_print == "individueel":
        volledig_aangemeld = [r for r in all_regs if r.status == RegistrationStatus.aangemeld]
    else:
        volledig_aangemeld = [r for r in all_regs if r.status == RegistrationStatus.aangemeld and (r.partner_naam or r.person2_id)]
    all_manual = (
        db.query(ManualPair)
        .filter(ManualPair.evening_id == event_id)
        .order_by(ManualPair.aangemaakt_op)
        .all()
    )
    if dtype_print == "viertallen":
        manual_aangemeld_print = [p for p in all_manual if p.naam_4]
    elif dtype_print == "individueel":
        manual_aangemeld_print = all_manual
    else:
        manual_aangemeld_print = [p for p in all_manual if p.naam_2]

    return templates.TemplateResponse(
        request,
        "admin/print_paren.html",
        {
            "current_user": current_user,
            "evening": evening,
            "volledig_aangemeld": volledig_aangemeld,
            "manual_pairs": manual_aangemeld_print,
            "welkom": False,
        },
    )


@router.post("/af-aanmeldingen/{event_id}/toevoegen")
async def af_aanmeldingen_toevoegen(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")
    if not can_manage_club(current_user, evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")

    form = await request.form()
    dtype = evening.deelnemers_type or "paren"

    naam_1 = form.get("naam_1", "").strip()
    if not naam_1:
        return RedirectResponse(url=f"/beheer/af-aanmeldingen/{event_id}?fout=naam_verplicht", status_code=302)

    if dtype == "individueel":
        # Elke naam is een individuele deelnemer → direct naar aangemeld (geen losloper)
        db.add(ManualPair(evening_id=event_id, naam_1=naam_1))
    elif dtype == "viertallen":
        naam_2 = form.get("naam_2", "").strip() or None
        naam_3 = form.get("naam_3", "").strip() or None
        naam_4 = form.get("naam_4", "").strip() or None
        naam_5 = form.get("naam_5", "").strip() or None
        naam_6 = form.get("naam_6", "").strip() or None
        team_naam = form.get("team_naam", "").strip() or None
        # < 4 spelers → losloper-groep (naam_4 is None); alle 4 → aangemeld
        db.add(ManualPair(
            evening_id=event_id,
            naam_1=naam_1, naam_2=naam_2, naam_3=naam_3, naam_4=naam_4,
            naam_5=naam_5, naam_6=naam_6,
            team_naam=team_naam,
        ))
    else:  # paren
        naam_2 = form.get("naam_2", "").strip() or None
        db.add(ManualPair(evening_id=event_id, naam_1=naam_1, naam_2=naam_2))

    db.commit()
    return RedirectResponse(url=f"/beheer/af-aanmeldingen/{event_id}?toegevoegd=1", status_code=302)


@router.post("/af-aanmeldingen/{event_id}/manual/{pair_id}/verwijder")
async def manual_pair_verwijder(
    event_id: int,
    pair_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    pair = db.query(ManualPair).filter(ManualPair.id == pair_id).first()
    if pair:
        if pair.evening and not can_manage_club(current_user, pair.evening.club_id, db):
            raise HTTPException(status_code=403, detail="Geen toegang tot deze club")
        db.delete(pair)
        db.commit()
    return RedirectResponse(url=f"/beheer/af-aanmeldingen/{event_id}", status_code=302)


@router.post("/verzoeken/{request_id}/goedkeuren")
async def verzoek_goedkeuren(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    from app.email import send_partner_request_approved_email

    partner_request = db.query(PartnerRequest).filter(PartnerRequest.id == request_id).first()
    if not partner_request or partner_request.status != "wachtend":
        return RedirectResponse(url="/beheer/af-aanmeldingen", status_code=302)
    if partner_request.evening and not can_manage_club(current_user, partner_request.evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")

    partner_naam = f"{partner_request.partner_voornaam} {partner_request.partner_achternaam}"
    requester = partner_request.requester
    evening = partner_request.evening

    # Create registration
    existing = (
        db.query(Registration)
        .filter(
            Registration.evening_id == partner_request.evening_id,
            Registration.person1_id == partner_request.requester_id,
            Registration.status != RegistrationStatus.afgemeld,
        )
        .first()
    )
    if existing:
        existing.status = RegistrationStatus.aangemeld
        existing.partner_naam = partner_naam
    else:
        db.add(Registration(
            evening_id=partner_request.evening_id,
            person1_id=partner_request.requester_id,
            partner_naam=partner_naam,
            type=RegistrationType.los,
            status=RegistrationStatus.aangemeld,
        ))

    partner_request.status = "goedgekeurd"
    db.commit()

    if requester.email:
        try:
            send_partner_request_approved_email(
                requester.email,
                requester.voornaam,
                evening.naam or evening.type,
                partner_naam,
            )
        except Exception:
            logger.exception("E-mail versturen mislukt bij goedkeuren partnerverzoek voor %s", requester.email)

    return RedirectResponse(
        url=f"/beheer/af-aanmeldingen/{partner_request.evening_id}?goedgekeurd=1",
        status_code=302,
    )


@router.post("/verzoeken/{request_id}/afwijzen")
async def verzoek_afwijzen(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    partner_request = db.query(PartnerRequest).filter(PartnerRequest.id == request_id).first()
    if not partner_request:
        return RedirectResponse(url="/beheer/af-aanmeldingen", status_code=302)
    if partner_request.evening and not can_manage_club(current_user, partner_request.evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")
    if partner_request.status == "wachtend":
        partner_request.status = "afgewezen"
        db.commit()
    return RedirectResponse(
        url=f"/beheer/af-aanmeldingen/{partner_request.evening_id}?afgewezen=1",
        status_code=302,
    )


@router.post("/te-laat/{reg_id}/goedkeuren")
async def te_laat_goedkeuren(
    reg_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    reg = db.query(Registration).filter(Registration.id == reg_id).first()
    if not reg:
        return RedirectResponse(url="/beheer/af-aanmeldingen", status_code=302)
    if reg.evening and not can_manage_club(current_user, reg.evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")
    reg.te_laat_goedgekeurd = True
    db.commit()
    return RedirectResponse(
        url=f"/beheer/af-aanmeldingen/{reg.evening_id}?te_laat_goedgekeurd=1",
        status_code=302,
    )


@router.post("/te-laat/{reg_id}/verwijderen")
async def te_laat_verwijderen(
    reg_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    reg = db.query(Registration).filter(Registration.id == reg_id).first()
    if not reg:
        return RedirectResponse(url="/beheer/af-aanmeldingen", status_code=302)
    if reg.evening and not can_manage_club(current_user, reg.evening.club_id, db):
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")
    evening_id = reg.evening_id
    db.delete(reg)
    db.commit()
    return RedirectResponse(
        url=f"/beheer/af-aanmeldingen/{evening_id}?te_laat_verwijderd=1",
        status_code=302,
    )


_AANWEZIGHEID_TYPE_MAP: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "avondeten": ["eten voor jeugdtraining"],
    "training": ["jeugdtraining", "training"],
    "speciaal": ["speciaal"],
}


@router.get("/aanwezigheid")
async def aanwezigheid(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    club = get_admin_club(current_user, db, request)

    seasons_q = db.query(Season)
    if club:
        seasons_q = seasons_q.filter(Season.club_id == club.id)
    seasons = seasons_q.order_by(Season.start_datum.desc()).all()

    selected_season_id = request.query_params.get("seizoen")
    selected_season = None

    if selected_season_id:
        try:
            selected_season = db.query(Season).filter(Season.id == int(selected_season_id)).first()
        except ValueError:
            selected_season = None
    if not selected_season:
        selected_season = next((s for s in seasons if s.actief), None)
    if not selected_season and seasons:
        selected_season = seasons[0]

    # Event-type filter: "alle" (default) or one/more of the type keys
    raw_types = request.query_params.getlist("type")
    valid_keys = list(_AANWEZIGHEID_TYPE_MAP.keys())
    selected_types = [t for t in raw_types if t in valid_keys]
    # If nothing selected → treat as "alle"
    alle_actief = not selected_types

    # Determine which DB event-type strings count
    if alle_actief:
        db_types: Optional[list[str]] = None  # no filter = all
    else:
        db_types = []
        for key in selected_types:
            db_types.extend(_AANWEZIGHEID_TYPE_MAP[key])

    is_beheerder = current_user.role in (MemberRole.wedstrijdleider.value, MemberRole.admin.value)

    if is_beheerder and club:
        club_member_ids = [
            mc.member_id
            for mc in db.query(MemberClub).filter(MemberClub.club_id == club.id).all()
        ]
        members = (
            db.query(Member)
            .filter(Member.verwijderd_op.is_(None), Member.id.in_(club_member_ids))
            .order_by(Member.achternaam, Member.voornaam)
            .all()
        )
    elif is_beheerder:
        members = (
            db.query(Member)
            .filter(Member.verwijderd_op.is_(None))
            .order_by(Member.achternaam, Member.voornaam)
            .all()
        )
    else:
        members = [current_user]

    stats = []
    if selected_season:
        evening_q = db.query(ClubEvening).filter(ClubEvening.season_id == selected_season.id)
        if club:
            evening_q = evening_q.filter(ClubEvening.club_id == club.id)
        if db_types is not None:
            evening_q = evening_q.filter(ClubEvening.type.in_(db_types))
        evening_count = evening_q.count()

        for member in members:
            base_q = (
                db.query(Registration)
                .join(ClubEvening)
                .filter(
                    Registration.person1_id == member.id,
                    ClubEvening.season_id == selected_season.id,
                )
            )
            if db_types is not None:
                base_q = base_q.filter(ClubEvening.type.in_(db_types))

            aanwezig = base_q.filter(Registration.status != RegistrationStatus.afgemeld).count()
            afgemeld = base_q.filter(Registration.status == RegistrationStatus.afgemeld).count()
            stats.append({
                "member": member,
                "aanwezig": aanwezig,
                "afgemeld": afgemeld,
            })
        stats.sort(key=lambda x: x["aanwezig"], reverse=True)
    else:
        evening_count = 0

    return templates.TemplateResponse(
        request,
        "admin/aanwezigheid.html",
        {
            "current_user": current_user,
            "seasons": seasons,
            "selected_season": selected_season,
            "stats": stats,
            "evening_count": evening_count,
            "selected_types": selected_types,
            "alle_actief": alle_actief,
            "type_knoppen": list(_AANWEZIGHEID_TYPE_MAP.keys()),
            "type_labels": {"clubavond": "Clubavond", "avondeten": "Avondeten", "training": "Training", "speciaal": "Speciaal"},
            "is_beheerder": is_beheerder,
            "welkom": False,
        },
    )


