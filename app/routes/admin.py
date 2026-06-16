import logging
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _base_url(request: Request) -> str:
    configured = os.getenv("BASE_URL", "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")

from app.auth import get_current_user, require_admin, require_auth, require_wedstrijdleider
from app.database import get_db
from app.models import (
    AccountRequest,
    AccountRequestStatus,
    AdminBericht,
    Bericht,
    ClubEvening,
    EmailRoleAssignment,
    EveningType,
    Invitation,
    Lid,
    ManualPair,
    Member,
    MemberRole,
    PartnerRequest,
    RecurringRegistration,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
    Uitslag,
)

router = APIRouter(prefix="/beheer")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

EVENING_TYPES = [
    ("clubavond", "Clubavond"),
    ("jeugdtraining", "Jeugdtraining"),
    ("eten voor jeugdtraining", "Eten voor jeugdtraining"),
    ("speciaal", "Speciaal"),
]


def _apply_recurring_registrations(db: Session, event: ClubEvening, sender_id: Optional[int] = None) -> None:
    recurring_regs = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.event_type == event.type,
            RecurringRegistration.actief == True,  # noqa: E712
        )
        .all()
    )
    for rr in recurring_regs:
        if rr.herhaal_tot and rr.herhaal_tot < event.datum:
            continue
        if rr.interval > 1:
            count = (
                db.query(ClubEvening)
                .filter(
                    ClubEvening.type == event.type,
                    ClubEvening.datum >= rr.referentie_datum,
                    ClubEvening.datum < event.datum,
                )
                .count()
            )
            if count % rr.interval != 0:
                continue
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == event.id,
                Registration.person1_id == rr.member_id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )
        if not existing:
            status = RegistrationStatus.aangemeld if rr.partner_naam else RegistrationStatus.beschikbaar_solo
            db.add(Registration(
                evening_id=event.id,
                person1_id=rr.member_id,
                partner_naam=rr.partner_naam,
                type=RegistrationType.vast,
                status=status,
            ))
            if sender_id and sender_id != rr.member_id:
                datum_str = event.datum.strftime("%d-%m-%Y")
                event_naam = event.naam or event.type
                db.add(Bericht(
                    afzender_id=sender_id,
                    ontvanger_id=rr.member_id,
                    onderwerp=f"Automatisch aangemeld: {event_naam} op {datum_str}",
                    tekst=(
                        f"Je bent automatisch aangemeld voor {event_naam} op {datum_str}. "
                        "Dit is een gevolg van je definitieve aanmelding voor dit type evenement. "
                        "Je kunt je aanmelding aanpassen via de agenda."
                    ),
                ))


# ── Avonden (Wedstrijdleider + Admin) ─────────────────────────────────────────

@router.get("/avonden")
async def avonden_list(
    request: Request,
    pagina: int = 1,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    PER_PAGINA = 30
    totaal = db.query(ClubEvening).count()
    totaal_paginas = max(1, (totaal + PER_PAGINA - 1) // PER_PAGINA)
    pagina = max(1, min(pagina, totaal_paginas))
    seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
    evenings = (
        db.query(ClubEvening)
        .join(Season)
        .order_by(ClubEvening.datum.desc())
        .offset((pagina - 1) * PER_PAGINA)
        .limit(PER_PAGINA)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/avonden.html",
        {
            "current_user": current_user,
            "evenings": evenings,
            "seasons": seasons,
            "pagina": pagina,
            "totaal_paginas": totaal_paginas,
            "totaal": totaal,
        },
    )


@router.post("/avonden/seizoen")
async def seizoen_add_from_beheren(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    start_str = form.get("start_datum", "")
    eind_str = form.get("eind_datum", "")

    errors = []
    if not naam:
        errors.append("Naam is verplicht.")
    if not start_str or not eind_str:
        errors.append("Start- en einddatum zijn verplicht.")

    if errors:
        return RedirectResponse(url="/beheer/avonden?fout=seizoen", status_code=302)

    try:
        start = date.fromisoformat(start_str)
        eind = date.fromisoformat(eind_str)
    except ValueError:
        return RedirectResponse(url="/beheer/avonden?fout=datum", status_code=302)
    if start >= eind:
        return RedirectResponse(url="/beheer/avonden?fout=datum", status_code=302)

    actief = form.get("actief") == "on"
    if actief:
        db.query(Season).update({"actief": False})
    db.add(Season(naam=naam, start_datum=start, eind_datum=eind, actief=actief))
    db.commit()
    return RedirectResponse(url="/beheer/avonden?seizoen_aangemaakt=1", status_code=302)


@router.post("/avonden")
async def avonden_add(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    datum_str = form.get("datum", "")
    type_ = form.get("type", "clubavond")
    deelnemers_type = form.get("deelnemers_type", "paren")

    errors = []
    if not naam:
        errors.append("Naam is verplicht.")
    if not datum_str:
        errors.append("Datum is verplicht.")

    datum = None
    if datum_str:
        try:
            datum = date.fromisoformat(datum_str)
        except ValueError:
            errors.append("Ongeldige datumformat (gebruik JJJJ-MM-DD).")

    season = None
    if datum:
        season = (
            db.query(Season)
            .filter(Season.start_datum <= datum, Season.eind_datum >= datum)
            .first()
        )
        if not season:
            errors.append(f"Geen seizoen gevonden voor {datum_str}. Maak eerst een seizoen aan dat deze datum omvat.")

    if errors:
        seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
        evenings = db.query(ClubEvening).join(Season).order_by(ClubEvening.datum).all()
        return templates.TemplateResponse(
            request,
            "admin/avonden.html",
            {
                "current_user": current_user,
                "evenings": evenings,
                "seasons": seasons,
                "errors": errors,
                "open_type": type_,
            },
            status_code=422,
        )

    termijn_waarde_str = form.get("inschrijftermijn_waarde", "").strip()
    termijn_eenheid = form.get("inschrijftermijn_eenheid", "uren")
    inschrijftermijn_uren = None
    if termijn_waarde_str:
        try:
            waarde = int(termijn_waarde_str)
            inschrijftermijn_uren = waarde * 24 if termijn_eenheid == "dagen" else waarde
        except ValueError:
            pass

    herhaal_elke_str = (form.get("herhaal_elke", "").strip() or "1")
    herhaal_eenheid = form.get("herhaal_eenheid", "weken")
    herhaal_tot_str = form.get("herhaal_tot", "").strip()

    new_events = []
    first_event = ClubEvening(naam=naam, datum=datum, type=type_, deelnemers_type=deelnemers_type,
                               inschrijftermijn_uren=inschrijftermijn_uren, season_id=season.id)
    db.add(first_event)
    db.flush()
    new_events.append(first_event)

    if herhaal_tot_str:
        try:
            herhaal_elke = int(herhaal_elke_str)
            herhaal_tot = date.fromisoformat(herhaal_tot_str)
            if herhaal_eenheid == "dagen":
                delta = timedelta(days=herhaal_elke)
            else:
                delta = timedelta(weeks=herhaal_elke)

            next_datum = datum + delta
            while next_datum <= herhaal_tot:
                next_season = (
                    db.query(Season)
                    .filter(Season.start_datum <= next_datum, Season.eind_datum >= next_datum)
                    .first()
                )
                if next_season:
                    evt = ClubEvening(naam=naam, datum=next_datum, type=type_, deelnemers_type=deelnemers_type,
                                      inschrijftermijn_uren=inschrijftermijn_uren, season_id=next_season.id)
                    db.add(evt)
                    db.flush()
                    new_events.append(evt)
                next_datum += delta
        except (ValueError, TypeError):
            pass

    db.commit()

    for evt in new_events:
        _apply_recurring_registrations(db, evt, sender_id=current_user.id)
    db.commit()

    aantal = len(new_events)
    return RedirectResponse(url=f"/beheer/avonden?aangemaakt={aantal}", status_code=302)


@router.post("/avonden/{event_id}/verwijder")
async def avonden_delete(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if evening:
        db.query(Registration).filter(Registration.evening_id == event_id).delete(synchronize_session=False)
        db.query(ManualPair).filter(ManualPair.evening_id == event_id).delete(synchronize_session=False)
        db.query(PartnerRequest).filter(PartnerRequest.evening_id == event_id).delete(synchronize_session=False)
        db.query(Uitslag).filter(Uitslag.evening_id == event_id).delete(synchronize_session=False)
        db.delete(evening)
        db.commit()
    return RedirectResponse(url="/beheer/avonden?verwijderd=1", status_code=302)


# ── Aanmeldingenoverzicht (Wedstrijdleider + Admin) ───────────────────────────

@router.get("/aanmeldingen")
async def aanmeldingen_overview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evenings = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= date.today())  # noqa: E712
        .order_by(ClubEvening.datum)
        .all()
    )
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
    solo = (
        db.query(Registration)
        .filter(Registration.status == RegistrationStatus.beschikbaar_solo)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/loslopers.html",
        {"current_user": current_user, "solo_registrations": solo},
    )


# ── Seizoenen (Admin only) ────────────────────────────────────────────────────

@router.get("/seizoenen")
async def seizoenen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
    return templates.TemplateResponse(
        request,
        "admin/seizoenen.html",
        {"current_user": current_user, "seasons": seasons},
    )


@router.post("/seizoenen")
async def seizoen_add(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    start = form.get("start_datum", "")
    eind = form.get("eind_datum", "")
    actief = form.get("actief") == "on"

    if naam and start and eind:
        if actief:
            db.query(Season).update({"actief": False})
        db.add(Season(
            naam=naam,
            start_datum=date.fromisoformat(start),
            eind_datum=date.fromisoformat(eind),
            actief=actief,
        ))
        db.commit()
    return RedirectResponse(url="/beheer/seizoenen?aangemaakt=1", status_code=302)


@router.post("/seizoenen/{season_id}/activeer")
async def seizoen_activeer(
    season_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    db.query(Season).update({"actief": False})
    season = db.query(Season).filter(Season.id == season_id).first()
    if season:
        season.actief = True
    db.commit()
    return RedirectResponse(url="/beheer/seizoenen", status_code=302)


# ── SMTP-test (Admin only) ────────────────────────────────────────────────────

@router.post("/smtp-test")
async def smtp_test(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from app.email import _send, smtp_geconfigureerd
    if not smtp_geconfigureerd():
        return RedirectResponse(url="/beheer/uitnodigingen?smtp_test=niet_geconfigureerd", status_code=302)
    to_email = current_user.email or ""
    if not to_email:
        return RedirectResponse(url="/beheer/uitnodigingen?smtp_test=geen_email", status_code=302)
    try:
        _send(
            to_email,
            "SMTP-test Bridge Club",
            "<p>Dit is een testbericht vanuit de Bridge Club Aanmeldingsapp.</p>",
            "Dit is een testbericht vanuit de Bridge Club Aanmeldingsapp.",
        )
        logger.info("SMTP-test geslaagd, bericht verstuurd naar %s", to_email)
        return RedirectResponse(url="/beheer/uitnodigingen?smtp_test=ok", status_code=302)
    except Exception:
        logger.exception("SMTP-test mislukt")
        return RedirectResponse(url="/beheer/uitnodigingen?smtp_test=fout", status_code=302)


# ── Uitnodigingen (Admin only) ────────────────────────────────────────────────

@router.get("/uitnodigingen")
async def uitnodigingen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from app.email import smtp_geconfigureerd
    invitations = db.query(Invitation).order_by(Invitation.aangemaakt_op.desc()).all()
    return templates.TemplateResponse(
        request,
        "admin/uitnodigingen.html",
        {
            "current_user": current_user,
            "invitations": invitations,
            "roles": [r.value for r in MemberRole],
            "smtp_ok": smtp_geconfigureerd(),
        },
    )


@router.post("/uitnodigingen")
async def create_invitation(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from app.email import send_invitation_email

    form = await request.form()
    email = form.get("email", "").strip().lower()
    role = form.get("role", MemberRole.lid)

    if not email:
        return RedirectResponse(url="/beheer/uitnodigingen?error=email_required", status_code=302)

    # Set role assignment
    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    if assignment:
        assignment.role = role
    else:
        db.add(EmailRoleAssignment(email=email, role=role))

    token = secrets.token_urlsafe(32)
    invitation = Invitation(token=token, email=email)
    db.add(invitation)
    db.commit()

    base = _base_url(request)
    invite_url = f"{base}/invite/{token}"
    try:
        send_invitation_email(email, invite_url)
        return RedirectResponse(url="/beheer/uitnodigingen?verstuurd=1", status_code=302)
    except Exception:
        logger.exception("E-mail versturen mislukt voor uitnodiging naar %s", email)
        return RedirectResponse(
            url="/beheer/uitnodigingen?aangemaakt=1&email_fout=1",
            status_code=302,
        )


@router.post("/uitnodigingen/verwijder-alle")
async def delete_all_invitations(
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    db.query(Invitation).delete()
    db.commit()
    return RedirectResponse(url="/beheer/uitnodigingen?verwijderd=1", status_code=302)


@router.post("/uitnodigingen/verwijder-afgehandeld")
async def delete_handled_invitations(
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    db.query(Invitation).filter(Invitation.gebruikt_op.isnot(None)).delete()
    db.commit()
    return RedirectResponse(url="/beheer/uitnodigingen?verwijderd=1", status_code=302)


@router.post("/uitnodigingen/{invitation_id}/verwijder")
async def delete_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if invitation:
        db.delete(invitation)
        db.commit()
    return RedirectResponse(url="/beheer/uitnodigingen?verwijderd=1", status_code=302)


# ── Accountaanvragen (Admin only) ────────────────────────────────────────────

@router.get("/aanvragen")
async def aanvragen_list(
    request: Request,
    pagina: int = 1,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    PER_PAGINA = 20
    totaal = db.query(AccountRequest).count()
    totaal_paginas = max(1, (totaal + PER_PAGINA - 1) // PER_PAGINA)
    pagina = max(1, min(pagina, totaal_paginas))
    aanvragen = (
        db.query(AccountRequest)
        .order_by(AccountRequest.aangemaakt_op.desc())
        .offset((pagina - 1) * PER_PAGINA)
        .limit(PER_PAGINA)
        .all()
    )
    pending_count = (
        db.query(AccountRequest)
        .filter(AccountRequest.status == AccountRequestStatus.wachtend)
        .count()
    )
    berichten = (
        db.query(AdminBericht)
        .order_by(AdminBericht.aangemaakt_op.desc())
        .all()
    )
    ongelezen_berichten = sum(1 for b in berichten if not b.gelezen)
    from app.email import smtp_geconfigureerd
    return templates.TemplateResponse(
        request,
        "admin/aanvragen.html",
        {
            "current_user": current_user,
            "aanvragen": aanvragen,
            "pending_count": pending_count,
            "roles": [r.value for r in MemberRole],
            "smtp_ok": smtp_geconfigureerd(),
            "berichten": berichten,
            "ongelezen_berichten": ongelezen_berichten,
            "pagina": pagina,
            "totaal_paginas": totaal_paginas,
            "totaal": totaal,
        },
    )


@router.get("/aanvragen/telling")
async def aanvragen_telling(
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from fastapi.responses import JSONResponse
    count = (
        db.query(AccountRequest)
        .filter(AccountRequest.status == AccountRequestStatus.wachtend)
        .count()
    )
    return JSONResponse({"pending": count})


@router.post("/aanvragen/{aanvraag_id}/goedkeuren")
async def aanvraag_goedkeuren(
    aanvraag_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from app.email import send_approval_email, send_invitation_email

    form = await request.form()
    role = form.get("role", MemberRole.lid)

    aanvraag = db.query(AccountRequest).filter(AccountRequest.id == aanvraag_id).first()
    if not aanvraag or aanvraag.status != AccountRequestStatus.wachtend:
        return RedirectResponse(url="/beheer/aanvragen", status_code=302)

    aanvraag.status = AccountRequestStatus.goedgekeurd
    aanvraag.beoordeeld_op = datetime.now(timezone.utc)

    if aanvraag.wachtwoord_hash:
        # User provided a password during registration — create member directly
        al_bestaat = (
            db.query(Member)
            .filter(
                (Member.email == aanvraag.email) | (Member.lidnummer == aanvraag.lidnummer)
            )
            .first()
        )
        if al_bestaat:
            db.commit()
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1", status_code=302)

        member = Member(
            voornaam=aanvraag.voornaam,
            achternaam=aanvraag.achternaam,
            lidnummer=aanvraag.lidnummer,
            email=aanvraag.email,
            wachtwoord_hash=aanvraag.wachtwoord_hash,
            role=role,
        )
        db.add(member)
        db.commit()
        try:
            send_approval_email(aanvraag.email, aanvraag.voornaam, f"{_base_url(request)}/login")
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1", status_code=302)
        except Exception:
            logger.exception("E-mail versturen mislukt bij goedkeuren aanvraag %s", aanvraag.email)
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1&email_fout=1", status_code=302)
    else:
        # Legacy: send invite link
        assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == aanvraag.email).first()
        if assignment:
            assignment.role = role
        else:
            db.add(EmailRoleAssignment(email=aanvraag.email, role=role))

        token = secrets.token_urlsafe(32)
        db.add(Invitation(token=token, email=aanvraag.email, account_request_id=aanvraag.id))
        db.commit()

        invite_url = f"{_base_url(request)}/invite/{token}"
        try:
            send_invitation_email(aanvraag.email, invite_url)
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1", status_code=302)
        except Exception:
            logger.exception("Uitnodigingsmail mislukt voor aanvraag %s", aanvraag.email)
            return RedirectResponse(
                url="/beheer/aanvragen?goedgekeurd=1&email_fout=1",
                status_code=302,
            )


@router.post("/aanvragen/{aanvraag_id}/afwijzen")
async def aanvraag_afwijzen(
    aanvraag_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    aanvraag = db.query(AccountRequest).filter(AccountRequest.id == aanvraag_id).first()
    if aanvraag and aanvraag.status == AccountRequestStatus.wachtend:
        aanvraag.status = AccountRequestStatus.afgewezen
        aanvraag.beoordeeld_op = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url="/beheer/aanvragen?afgewezen=1", status_code=302)


# ── Admin berichten (Admin only) ─────────────────────────────────────────────

@router.post("/berichten/{bericht_id}/gelezen")
async def bericht_gelezen(
    bericht_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    bericht = db.query(AdminBericht).filter(AdminBericht.id == bericht_id).first()
    if bericht:
        bericht.gelezen = True
        db.commit()
    return RedirectResponse(url="/beheer/aanvragen", status_code=302)


# ── Roltoewijzingen (Admin only) ──────────────────────────────────────────────

@router.get("/rollen")
async def rollen_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    assignments = db.query(EmailRoleAssignment).order_by(EmailRoleAssignment.email).all()
    return templates.TemplateResponse(
        request,
        "admin/rollen.html",
        {
            "current_user": current_user,
            "assignments": assignments,
            "roles": [r.value for r in MemberRole],
        },
    )


@router.post("/rollen")
async def upsert_role(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    email = form.get("email", "").strip().lower()
    role = form.get("role", "").strip()

    if not email or role not in [r.value for r in MemberRole]:
        return RedirectResponse(url="/beheer/rollen?error=1", status_code=302)

    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    if assignment:
        assignment.role = role
    else:
        db.add(EmailRoleAssignment(email=email, role=role))

    member = db.query(Member).filter(Member.email == email).first()
    if member:
        member.role = role

    db.commit()
    return RedirectResponse(url="/beheer/rollen?opgeslagen=1", status_code=302)


@router.post("/rollen/verwijder")
async def delete_role(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    assignment_id = form.get("id")
    if assignment_id:
        try:
            db.query(EmailRoleAssignment).filter(EmailRoleAssignment.id == int(assignment_id)).delete()
            db.commit()
        except ValueError:
            pass
    return RedirectResponse(url="/beheer/rollen", status_code=302)


# ── Ledenlijst beheren (Admin only) ──────────────────────────────────────────

@router.get("/leden")
async def leden_list(
    request: Request,
    pagina: int = 1,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    PER_PAGINA = 50
    totaal = db.query(Lid).count()
    totaal_paginas = max(1, (totaal + PER_PAGINA - 1) // PER_PAGINA)
    pagina = max(1, min(pagina, totaal_paginas))
    leden = (
        db.query(Lid)
        .order_by(Lid.achternaam, Lid.voornaam)
        .offset((pagina - 1) * PER_PAGINA)
        .limit(PER_PAGINA)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/leden.html",
        {
            "current_user": current_user,
            "leden": leden,
            "pagina": pagina,
            "totaal_paginas": totaal_paginas,
            "totaal": totaal,
        },
    )


@router.post("/leden")
async def lid_toevoegen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    voornaam = form.get("voornaam", "").strip()
    achternaam = form.get("achternaam", "").strip()
    nbb_nummer = form.get("nbb_nummer", "").strip() or None

    if voornaam and achternaam:
        db.add(Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb_nummer))
        db.commit()
    return RedirectResponse(url="/beheer/leden?toegevoegd=1", status_code=302)


@router.post("/leden/{lid_id}/verwijder")
async def lid_verwijder(
    lid_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    lid = db.query(Lid).filter(Lid.id == lid_id).first()
    if lid:
        db.delete(lid)
        db.commit()
    return RedirectResponse(url="/beheer/leden?verwijderd=1", status_code=302)


@router.post("/leden/importeer")
async def leden_importeer(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    import csv
    import io

    form = await request.form()
    bestand = form.get("bestand")
    if not bestand or not bestand.filename:
        return RedirectResponse(url="/beheer/leden?import_fout=1", status_code=302)

    inhoud = await bestand.read()
    try:
        tekst = inhoud.decode("utf-8-sig")  # utf-8-sig handles Excel BOM
    except UnicodeDecodeError:
        tekst = inhoud.decode("latin-1")

    reader = csv.DictReader(io.StringIO(tekst))
    toegevoegd = 0
    overgeslagen = 0
    for rij in reader:
        voornaam = (rij.get("voornaam") or rij.get("Voornaam") or "").strip()
        achternaam = (rij.get("achternaam") or rij.get("Achternaam") or "").strip()
        nbb = (rij.get("nbb_nummer") or rij.get("NBB") or rij.get("nbb") or "").strip() or None
        if not voornaam or not achternaam:
            overgeslagen += 1
            continue
        al_aanwezig = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == voornaam.lower(),
                func.lower(Lid.achternaam) == achternaam.lower(),
            )
            .first()
        )
        if not al_aanwezig:
            db.add(Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb))
            toegevoegd += 1
        else:
            overgeslagen += 1
    db.commit()
    return RedirectResponse(url=f"/beheer/leden?import_ok={toegevoegd}&overgeslagen={overgeslagen}", status_code=302)


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
    active_filter = request.query_params.get("type", "")
    query = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= date.today())  # noqa: E712
        .order_by(ClubEvening.datum)
    )
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
    seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
    selected_season_id = request.query_params.get("seizoen")
    selected_season = None

    if selected_season_id:
        try:
            selected_season = db.query(Season).filter(Season.id == int(selected_season_id)).first()
        except ValueError:
            selected_season = None
    if not selected_season:
        selected_season = db.query(Season).filter(Season.actief == True).first()  # noqa: E712
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

    if is_beheerder:
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


@router.get("/weergave/{rol}")
async def set_weergave(
    rol: str,
    request: Request,
    current_user: Member = Depends(require_admin),
):
    if rol == "reset":
        request.session.pop("view_as_role", None)
    elif rol in ("lid", "wedstrijdleider"):
        request.session["view_as_role"] = rol
    else:
        raise HTTPException(status_code=400, detail="Ongeldige rol")

    referer = request.headers.get("referer", "/")
    # Only follow relative paths — reject absolute URLs to prevent open redirect
    if not referer.startswith("/") or referer.startswith("//"):
        referer = "/"
    return RedirectResponse(url=referer, status_code=302)
