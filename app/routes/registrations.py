import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_auth
from app.database import get_db
from app.email import (
    send_afmelding_wedstrijdleider_email,
    send_bulk_afmelding_wedstrijdleider_email,
    smtp_geconfigureerd,
)
from app.models import (
    Club,
    ClubEvening,
    EveningType,
    Lid,
    Member,
    MemberClub,
    MemberRole,
    PartnerRequest,
    RecurringRegistration,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
)

logger = logging.getLogger(__name__)

router = APIRouter()
from app.templates_env import templates


# ── Per-evenement aanmelden ───────────────────────────────────────────────────

_TRAINING_TYPES = {EveningType.jeugdtraining, EveningType.jeugdtraining.value,
                   EveningType.training, EveningType.training.value}


def _is_training(evening: ClubEvening) -> bool:
    return evening.type in _TRAINING_TYPES


def _is_na_inschrijftermijn(evening: ClubEvening) -> bool:
    if not evening.inschrijftermijn_uren:
        return False
    deadline = datetime.combine(evening.datum, datetime.min.time()) - timedelta(hours=evening.inschrijftermijn_uren)
    return datetime.now() > deadline


@router.get("/aanmelden/{event_id}")
async def registration_form(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    if evening.datum < date.today():
        return RedirectResponse(url="/", status_code=302)

    if _is_training(evening) and not current_user.training_eligible:
        return templates.TemplateResponse(
            request,
            "registrations/start.html",
            {
                "current_user": current_user,
                "evening": evening,
                "existing": None,
                "pending_request": None,
                "training_niet_toegestaan": True,
            },
        )

    existing = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.person1_id == current_user.id,
            Registration.status != RegistrationStatus.afgemeld,
        )
        .first()
    )

    pending_request = (
        db.query(PartnerRequest)
        .filter(
            PartnerRequest.evening_id == event_id,
            PartnerRequest.requester_id == current_user.id,
            PartnerRequest.status == "wachtend",
        )
        .first()
    )

    return templates.TemplateResponse(
        request,
        "registrations/start.html",
        {
            "current_user": current_user,
            "evening": evening,
            "existing": existing,
            "pending_request": pending_request,
        },
    )


@router.post("/aanmelden/{event_id}")
async def registration_submit(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    if evening.datum < date.today():
        return RedirectResponse(url="/", status_code=302)

    if _is_training(evening) and not current_user.training_eligible:
        raise HTTPException(status_code=403, detail="Geen toegang tot trainingsavonden")

    form = await request.form()
    action = form.get("action", "aanmelden")
    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()

    te_laat = _is_na_inschrijftermijn(evening)

    existing = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.person1_id == current_user.id,
            Registration.status != RegistrationStatus.afgemeld,
        )
        .first()
    )

    if action == "afmelden":
        if existing:
            existing.status = RegistrationStatus.afgemeld
            existing.partner_naam = None
            existing.partner2_naam = None
            existing.partner3_naam = None
            db.commit()
        # Also cancel pending partner request
        db.query(PartnerRequest).filter(
            PartnerRequest.evening_id == event_id,
            PartnerRequest.requester_id == current_user.id,
            PartnerRequest.status == "wachtend",
        ).delete()
        db.commit()
        if smtp_geconfigureerd():
            lid_naam = f"{current_user.voornaam} {current_user.achternaam}"
            event_naam = evening.naam or evening.type
            wedstrijdleiders = (
                db.query(Member)
                .filter(
                    Member.role == MemberRole.wedstrijdleider,
                    Member.email.isnot(None),
                    Member.verwijderd_op.is_(None),
                )
                .all()
            )
            for wl in wedstrijdleiders:
                try:
                    send_afmelding_wedstrijdleider_email(
                        wl.email,
                        wl.voornaam,
                        lid_naam,
                        event_naam,
                        evening.datum,
                    )
                except Exception:
                    logger.exception("E-mail afmelding versturen mislukt naar wedstrijdleider %s", wl.email)
        return RedirectResponse(url="/?afgemeld=1", status_code=302)

    deelnemers_type = evening.deelnemers_type or "paren"

    # Individueel: geen partner nodig
    if deelnemers_type == "individueel":
        if existing:
            existing.status = RegistrationStatus.aangemeld
            existing.partner_naam = None
            existing.partner2_naam = None
            existing.partner3_naam = None
            if te_laat:
                existing.te_laat = True
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                partner_naam=None,
                type=RegistrationType.los,
                status=RegistrationStatus.aangemeld,
                te_laat=te_laat,
            ))
        db.commit()
        return RedirectResponse(url="/?te_laat=1" if te_laat else "/?bevestigd=1", status_code=302)

    # Viertallen: teamnaam + tot 3 teamgenoten opgeven
    if deelnemers_type == "viertallen":
        team_naam_raw = form.get("team_naam", "").strip()
        team_naam = team_naam_raw if team_naam_raw else current_user.voornaam

        partner2_voornaam = form.get("partner2_voornaam", "").strip()
        partner2_achternaam = form.get("partner2_achternaam", "").strip()
        partner3_voornaam = form.get("partner3_voornaam", "").strip()
        partner3_achternaam = form.get("partner3_achternaam", "").strip()
        reserve1_voornaam = form.get("reserve1_voornaam", "").strip()
        reserve1_achternaam = form.get("reserve1_achternaam", "").strip()
        reserve2_voornaam = form.get("reserve2_voornaam", "").strip()
        reserve2_achternaam = form.get("reserve2_achternaam", "").strip()

        p1 = f"{partner_voornaam} {partner_achternaam}".strip() if partner_voornaam and partner_achternaam else None
        p2 = f"{partner2_voornaam} {partner2_achternaam}".strip() if partner2_voornaam and partner2_achternaam else None
        p3 = f"{partner3_voornaam} {partner3_achternaam}".strip() if partner3_voornaam and partner3_achternaam else None
        r1 = f"{reserve1_voornaam} {reserve1_achternaam}".strip() if reserve1_voornaam and reserve1_achternaam else None
        r2 = f"{reserve2_voornaam} {reserve2_achternaam}".strip() if reserve2_voornaam and reserve2_achternaam else None

        volledig = bool(p1 and p2 and p3)

        if existing:
            existing.status = RegistrationStatus.aangemeld
            existing.team_naam = team_naam
            existing.partner_naam = p1
            existing.partner2_naam = p2
            existing.partner3_naam = p3
            existing.reserve1_naam = r1
            existing.reserve2_naam = r2
            if te_laat:
                existing.te_laat = True
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                team_naam=team_naam,
                partner_naam=p1,
                partner2_naam=p2,
                partner3_naam=p3,
                reserve1_naam=r1,
                reserve2_naam=r2,
                type=RegistrationType.los,
                status=RegistrationStatus.aangemeld,
                te_laat=te_laat,
            ))
        db.commit()

        if volledig:
            return RedirectResponse(url="/?te_laat=1" if te_laat else "/?bevestigd=1", status_code=302)
        return RedirectResponse(url="/?aangemeld_onvolledig_team=1", status_code=302)

    # Paren (standaard): één partner opgeven
    if partner_voornaam and partner_achternaam:
        partner_naam = f"{partner_voornaam} {partner_achternaam}"

        lid = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == partner_voornaam.lower(),
                func.lower(Lid.achternaam) == partner_achternaam.lower(),
            )
            .first()
        )

        if lid:
            # Partner found in leden DB → direct registration
            if existing:
                existing.status = RegistrationStatus.aangemeld
                existing.partner_naam = partner_naam
                existing.partner2_naam = None
                existing.partner3_naam = None
                if te_laat:
                    existing.te_laat = True
            else:
                db.add(Registration(
                    evening_id=event_id,
                    person1_id=current_user.id,
                    partner_naam=partner_naam,
                    type=RegistrationType.los,
                    status=RegistrationStatus.aangemeld,
                    te_laat=te_laat,
                ))
            db.commit()
            return RedirectResponse(url="/?te_laat=1" if te_laat else "/?bevestigd=1", status_code=302)
        else:
            # Partner not in leden DB → create partner request
            # Remove existing pending request first
            db.query(PartnerRequest).filter(
                PartnerRequest.evening_id == event_id,
                PartnerRequest.requester_id == current_user.id,
                PartnerRequest.status == "wachtend",
            ).delete()
            db.add(PartnerRequest(
                evening_id=event_id,
                requester_id=current_user.id,
                partner_voornaam=partner_voornaam,
                partner_achternaam=partner_achternaam,
            ))
            db.commit()
            redirect_param = "te_laat=1" if te_laat else "verzoek_ingediend=1"
            return RedirectResponse(url=f"/?{redirect_param}", status_code=302)
    else:
        # Geen partner opgegeven bij paren
        if existing:
            existing.status = RegistrationStatus.beschikbaar_solo
            existing.partner_naam = None
            existing.partner2_naam = None
            existing.partner3_naam = None
            if te_laat:
                existing.te_laat = True
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                partner_naam=None,
                type=RegistrationType.los,
                status=RegistrationStatus.beschikbaar_solo,
                te_laat=te_laat,
            ))
        db.commit()
        return RedirectResponse(url="/?te_laat=1" if te_laat else "/?aangemeld_zonder_partner=1", status_code=302)


# ── Instellingen / bulk aanmelden ─────────────────────────────────────────────

@router.get("/instellingen")
async def instellingen_form(
    request: Request,
    club: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    today = date.today()

    user_clubs = (
        db.query(Club)
        .join(MemberClub, MemberClub.club_id == Club.id)
        .filter(MemberClub.member_id == current_user.id)
        .order_by(Club.naam)
        .all()
    )

    active_club: Optional[Club] = None
    if club:
        active_club = next((c for c in user_clubs if c.id == club), None)

    q = (
        db.query(ClubEvening)
        .join(Season)
        .filter(
            ClubEvening.datum >= today,
            ClubEvening.type.in_([EveningType.clubavond, "regulier"]),
            Season.actief == True,  # noqa: E712
        )
    )
    if active_club:
        q = q.filter(ClubEvening.club_id == active_club.id)
    upcoming_clubavonden = q.order_by(ClubEvening.datum).all()

    herhalingen = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.member_id == current_user.id,
            RecurringRegistration.actief == True,  # noqa: E712
        )
        .order_by(RecurringRegistration.aangemaakt_op)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "registrations/instellingen.html",
        {
            "current_user": current_user,
            "upcoming_clubavonden": upcoming_clubavonden,
            "herhalingen": herhalingen,
            "user_clubs": user_clubs,
            "active_club": active_club,
        },
    )


@router.post("/instellingen/herhaal/{herhaal_id}/stop")
async def herhaal_stop(
    herhaal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    rr = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.id == herhaal_id,
            RecurringRegistration.member_id == current_user.id,
        )
        .first()
    )
    if rr:
        rr.actief = False
        db.commit()
    return RedirectResponse(url="/instellingen?herhaal_gestopt=1", status_code=302)


@router.post("/instellingen")
async def instellingen_submit(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()
    club_id_raw = form.get("club_id", "").strip()
    club_id = int(club_id_raw) if club_id_raw.isdigit() else None

    partner_naam = None
    if partner_voornaam and partner_achternaam:
        lid = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == partner_voornaam.lower(),
                func.lower(Lid.achternaam) == partner_achternaam.lower(),
            )
            .first()
        )
        if lid:
            partner_naam = f"{partner_voornaam} {partner_achternaam}"

    today = date.today()
    q = (
        db.query(ClubEvening)
        .join(Season)
        .filter(
            ClubEvening.datum >= today,
            ClubEvening.type.in_([EveningType.clubavond, "regulier"]),
            Season.actief == True,  # noqa: E712
        )
    )
    if club_id:
        q = q.filter(ClubEvening.club_id == club_id)
    upcoming_clubavonden = q.all()

    count = 0
    for evening in upcoming_clubavonden:
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == evening.id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )
        if not existing:
            status = RegistrationStatus.aangemeld if partner_naam else RegistrationStatus.beschikbaar_solo
            db.add(Registration(
                evening_id=evening.id,
                person1_id=current_user.id,
                partner_naam=partner_naam,
                type=RegistrationType.vast,
                status=status,
            ))
            count += 1

    db.commit()
    return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)


# ── Herhaal-aanmelding ────────────────────────────────────────────────────────

@router.post("/aanmelden/{event_id}/herhaal")
async def registration_herhaal(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    if _is_training(evening) and not current_user.training_eligible:
        raise HTTPException(status_code=403, detail="Geen toegang tot trainingsavonden")

    form = await request.form()
    alles = form.get("alles") == "on"
    alles_tot_str = form.get("alles_tot", "").strip()
    elke_str = form.get("elke", "").strip()
    herhaal_tot_str = form.get("herhaal_tot", "").strip()
    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()

    partner_naam = None
    if partner_voornaam and partner_achternaam:
        lid = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == partner_voornaam.lower(),
                func.lower(Lid.achternaam) == partner_achternaam.lower(),
            )
            .first()
        )
        if lid:
            partner_naam = f"{partner_voornaam} {partner_achternaam}"

    today = date.today()

    def _register_for_events(events):
        count = 0
        for evt in events:
            existing = (
                db.query(Registration)
                .filter(
                    Registration.evening_id == evt.id,
                    Registration.person1_id == current_user.id,
                    Registration.status != RegistrationStatus.afgemeld,
                )
                .first()
            )
            if not existing:
                status = RegistrationStatus.aangemeld if partner_naam else RegistrationStatus.beschikbaar_solo
                db.add(Registration(
                    evening_id=evt.id,
                    person1_id=current_user.id,
                    partner_naam=partner_naam,
                    type=RegistrationType.vast,
                    status=status,
                ))
                count += 1
        return count

    if alles:
        alles_tot = date.fromisoformat(alles_tot_str) if alles_tot_str else None

        query = (
            db.query(ClubEvening)
            .join(Season)
            .filter(
                ClubEvening.type == evening.type,
                ClubEvening.datum >= today,
                Season.actief == True,  # noqa: E712
            )
        )
        if alles_tot:
            query = query.filter(ClubEvening.datum <= alles_tot)

        future_events = query.order_by(ClubEvening.datum).all()
        count = _register_for_events(future_events)

        # Without end date: store recurring registration for auto-apply on new events
        if not alles_tot:
            db.query(RecurringRegistration).filter(
                RecurringRegistration.member_id == current_user.id,
                RecurringRegistration.event_type == evening.type,
                RecurringRegistration.actief == True,  # noqa: E712
            ).update({"actief": False})
            db.add(RecurringRegistration(
                member_id=current_user.id,
                event_type=evening.type,
                partner_naam=partner_naam,
                interval=1,
                herhaal_tot=None,
                referentie_datum=today,
            ))

        db.commit()
        return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)

    elif elke_str:
        try:
            elke = max(1, int(elke_str))
        except ValueError:
            elke = 1

        herhaal_tot = date.fromisoformat(herhaal_tot_str) if herhaal_tot_str else None

        query = (
            db.query(ClubEvening)
            .join(Season)
            .filter(
                ClubEvening.type == evening.type,
                ClubEvening.datum >= today,
                Season.actief == True,  # noqa: E712
            )
        )
        if herhaal_tot:
            query = query.filter(ClubEvening.datum <= herhaal_tot)

        future_events = query.order_by(ClubEvening.datum).all()
        selected = [evt for i, evt in enumerate(future_events) if i % elke == 0]
        count = _register_for_events(selected)

        db.commit()
        return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)

    return RedirectResponse(url=f"/aanmelden/{event_id}", status_code=302)


# ── Definitief aanmelden voor alle evenementen van een type ───────────────────

_TYPE_MAP: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "avondeten": ["eten voor jeugdtraining"],
    "training": ["jeugdtraining", "training"],
    "speciaal": ["speciaal"],
}

_TRAINING_KEYS = {"training"}


@router.post("/definitief-aanmelden/{event_type}")
async def definitief_aanmelden(
    event_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    if event_type not in _TYPE_MAP:
        raise HTTPException(status_code=400, detail="Onbekend type")

    if event_type in _TRAINING_KEYS and not current_user.training_eligible:
        raise HTTPException(status_code=403, detail="Geen toegang tot trainingsavonden")

    form = await request.form()
    partner_naam = None
    if form.get("met_partner") == "1":
        partner_voornaam = form.get("partner_voornaam", "").strip()
        partner_achternaam = form.get("partner_achternaam", "").strip()
        if partner_voornaam and partner_achternaam:
            lid = (
                db.query(Lid)
                .filter(
                    func.lower(Lid.voornaam) == partner_voornaam.lower(),
                    func.lower(Lid.achternaam) == partner_achternaam.lower(),
                )
                .first()
            )
            if lid:
                partner_naam = f"{partner_voornaam} {partner_achternaam}"

    club_id_raw = form.get("club_id", "").strip()
    club_id = int(club_id_raw) if club_id_raw.isdigit() else None

    db_types = _TYPE_MAP[event_type]
    today = date.today()

    q = (
        db.query(ClubEvening)
        .join(Season)
        .filter(
            ClubEvening.type.in_(db_types),
            ClubEvening.datum >= today,
            Season.actief == True,  # noqa: E712
        )
    )
    if club_id:
        q = q.filter(ClubEvening.club_id == club_id)
    future_events = q.order_by(ClubEvening.datum).all()

    count = 0
    for evt in future_events:
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == evt.id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )
        if not existing:
            deelnemers_type = evt.deelnemers_type or "paren"
            if deelnemers_type == "individueel":
                reg_partner = None
                reg_status = RegistrationStatus.aangemeld
            elif deelnemers_type == "paren" and partner_naam:
                reg_partner = partner_naam
                reg_status = RegistrationStatus.aangemeld
            else:
                reg_partner = None
                reg_status = RegistrationStatus.beschikbaar_solo
            db.add(Registration(
                evening_id=evt.id,
                person1_id=current_user.id,
                partner_naam=reg_partner,
                type=RegistrationType.vast,
                status=reg_status,
            ))
            count += 1

    # Sla op als herhaalaanmelding (zonder einddatum) zodat nieuwe avonden automatisch worden toegevoegd
    primary_type = db_types[0]
    db.query(RecurringRegistration).filter(
        RecurringRegistration.member_id == current_user.id,
        RecurringRegistration.event_type == primary_type,
        RecurringRegistration.actief == True,  # noqa: E712
    ).update({"actief": False})
    db.add(RecurringRegistration(
        member_id=current_user.id,
        event_type=primary_type,
        partner_naam=partner_naam,
        interval=1,
        herhaal_tot=None,
        referentie_datum=today,
    ))

    db.commit()
    return RedirectResponse(url=f"/?type={event_type}&bulk_ok={count}", status_code=302)


# ── Weergave-voorkeuren opslaan ───────────────────────────────────────────────

@router.post("/instellingen/verborgen-types")
async def verborgen_types_submit(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    all_keys = ["clubavond", "avondeten", "training", "speciaal"]
    hidden = [k for k in all_keys if not form.get(f"toon_{k}")]
    current_user.verborgen_types = ",".join(hidden)
    db.commit()
    return RedirectResponse(url="/?voorkeuren_opgeslagen=1", status_code=302)


# ── Wijzigen (redirect) ───────────────────────────────────────────────────────

@router.get("/aanmelden/wijzigen")
async def wijzigen_redirect(request: Request):
    return RedirectResponse(url="/", status_code=302)


# ── Profielpagina ─────────────────────────────────────────────────────────────

@router.get("/profiel")
async def mijn_profiel(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    registrations = (
        db.query(Registration)
        .filter(
            or_(
                Registration.person1_id == current_user.id,
                Registration.person2_id == current_user.id,
            )
        )
        .join(ClubEvening)
        .order_by(ClubEvening.datum.desc())
        .limit(50)
        .all()
    )

    herhalingen = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.member_id == current_user.id,
            RecurringRegistration.actief == True,  # noqa: E712
        )
        .order_by(RecurringRegistration.aangemaakt_op)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "profiel.html",
        {
            "current_user": current_user,
            "registrations": registrations,
            "herhalingen": herhalingen,
            "welkom": False,
        },
    )


# ── Bulk voor alles aanmelden / afmelden ─────────────────────────────────────

_ALL_TYPES_MAP: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "avondeten": ["eten voor jeugdtraining"],
    "training": ["jeugdtraining", "training"],
    "speciaal": ["speciaal"],
}


@router.post("/voor-alles-aanmelden")
async def voor_alles_aanmelden(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    partner_naam = None
    if form.get("met_partner") == "1":
        partner_voornaam = form.get("partner_voornaam", "").strip()
        partner_achternaam = form.get("partner_achternaam", "").strip()
        if partner_voornaam and partner_achternaam:
            lid = (
                db.query(Lid)
                .filter(
                    func.lower(Lid.voornaam) == partner_voornaam.lower(),
                    func.lower(Lid.achternaam) == partner_achternaam.lower(),
                )
                .first()
            )
            if lid:
                partner_naam = f"{partner_voornaam} {partner_achternaam}"

    club_id_raw = form.get("club_id", "").strip()
    club_id = int(club_id_raw) if club_id_raw.isdigit() else None

    today = date.today()
    all_db_types = ["clubavond", "regulier", "eten voor jeugdtraining", "speciaal"]
    if current_user.training_eligible:
        all_db_types += ["jeugdtraining", "training"]

    q = (
        db.query(ClubEvening)
        .join(Season)
        .filter(
            ClubEvening.datum >= today,
            ClubEvening.type.in_(all_db_types),
            Season.actief == True,  # noqa: E712
        )
    )
    if club_id:
        q = q.filter(ClubEvening.club_id == club_id)
    future_events = q.order_by(ClubEvening.datum).all()

    count = 0
    for evt in future_events:
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == evt.id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )
        if not existing:
            deelnemers_type = evt.deelnemers_type or "paren"
            if deelnemers_type == "individueel":
                reg_partner = None
                reg_status = RegistrationStatus.aangemeld
            elif deelnemers_type == "paren" and partner_naam:
                reg_partner = partner_naam
                reg_status = RegistrationStatus.aangemeld
            else:
                reg_partner = None
                reg_status = RegistrationStatus.beschikbaar_solo
            db.add(Registration(
                evening_id=evt.id,
                person1_id=current_user.id,
                partner_naam=reg_partner,
                type=RegistrationType.los,
                status=reg_status,
            ))
            count += 1

    db.commit()
    return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)


@router.post("/voor-alles-afmelden")
async def voor_alles_afmelden(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    partner_naam = None
    if form.get("met_partner") == "1":
        vn = form.get("partner_voornaam", "").strip()
        an = form.get("partner_achternaam", "").strip()
        if vn and an:
            partner_naam = f"{vn} {an}"

    today = date.today()

    query = (
        db.query(Registration)
        .join(ClubEvening)
        .filter(
            Registration.person1_id == current_user.id,
            Registration.status != RegistrationStatus.afgemeld,
            ClubEvening.datum >= today,
        )
    )
    if partner_naam:
        query = query.filter(
            func.lower(Registration.partner_naam) == partner_naam.lower()
        )
    upcoming_regs = query.all()

    count = len(upcoming_regs)
    for reg in upcoming_regs:
        reg.status = RegistrationStatus.afgemeld
        reg.partner_naam = None
        reg.partner2_naam = None
        reg.partner3_naam = None

    db.commit()
    if smtp_geconfigureerd() and upcoming_regs:
        lid_naam = f"{current_user.voornaam} {current_user.achternaam}"
        events = [(reg.evening.naam or reg.evening.type, reg.evening.datum) for reg in upcoming_regs]
        wedstrijdleiders = (
            db.query(Member)
            .filter(
                Member.role == MemberRole.wedstrijdleider,
                Member.email.isnot(None),
                Member.verwijderd_op.is_(None),
            )
            .all()
        )
        for wl in wedstrijdleiders:
            try:
                send_bulk_afmelding_wedstrijdleider_email(
                    wl.email,
                    wl.voornaam,
                    lid_naam,
                    events,
                )
            except Exception:
                logger.exception("E-mail bulk afmelding versturen mislukt naar wedstrijdleider %s", wl.email)
    return RedirectResponse(url=f"/?afgemeld_alles={count}", status_code=302)
