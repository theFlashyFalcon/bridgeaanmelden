import logging
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import (
    get_algemene_club_id,
    get_current_user,
    get_member_club_ids,
    is_member_of_club,
    require_auth,
)
from app.database import get_db
from app.email import (
    send_afmelding_wedstrijdleider_email,
    send_bulk_afmelding_wedstrijdleider_email,
    smtp_geconfigureerd,
)
from app.models import (
    Bericht,
    Club,
    ClubEvening,
    EveningType,
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

# De inschrijftermijn wordt gerekend in Nederlandse tijd, ongeacht de servertijdzone
_TIJDZONE = ZoneInfo("Europe/Amsterdam")

# Legacy-synoniemen: oude en nieuwe naam voor hetzelfde type evenement
_TYPE_SYNONIEMEN: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "regulier": ["clubavond", "regulier"],
    "jeugdtraining": ["jeugdtraining", "training"],
    "training": ["jeugdtraining", "training"],
}


def _synoniemen(event_type: str) -> list[str]:
    return _TYPE_SYNONIEMEN.get(event_type, [event_type])


def _is_na_inschrijftermijn(evening: ClubEvening) -> bool:
    if not evening.inschrijftermijn_uren:
        return False
    middernacht = datetime.combine(evening.datum, datetime.min.time(), tzinfo=_TIJDZONE)
    deadline = middernacht - timedelta(hours=evening.inschrijftermijn_uren)
    return datetime.now(_TIJDZONE) > deadline


def _club_wedstrijdleiders(db: Session, club_id: Optional[int]) -> list[Member]:
    """Wedstrijdleiders die notificaties horen te krijgen voor een avond van deze club."""
    basis = db.query(Member).filter(
        Member.email.isnot(None),
        Member.verwijderd_op.is_(None),
    )
    if club_id:
        wl_ids = [
            mc.member_id
            for mc in db.query(MemberClub).filter(
                MemberClub.club_id == club_id,
                MemberClub.role.in_([MemberRole.wedstrijdleider.value, MemberRole.admin.value]),
            ).all()
        ]
        if wl_ids:
            return basis.filter(Member.id.in_(wl_ids)).all()
    # Legacy (avond zonder club, of club zonder per-club-WL's): globale WL-rol
    return basis.filter(Member.role == MemberRole.wedstrijdleider.value).all()


def _partner_lid(
    db: Session, current_user: Member, voornaam: str, achternaam: str
) -> Optional[Member]:
    """Zoek het clublid dat overeenkomt met de opgegeven partnernaam (voor de aanmeldnotificatie)."""
    if not voornaam or not achternaam:
        return None
    kandidaat = (
        db.query(Member)
        .filter(
            func.lower(Member.voornaam) == voornaam.lower(),
            func.lower(Member.achternaam) == achternaam.lower(),
            Member.verwijderd_op == None,  # noqa: E711
            Member.id != current_user.id,
        )
        .first()
    )
    if not kandidaat:
        return None
    mijn_clubs = set(get_member_club_ids(current_user, db))
    zijn_clubs = set(get_member_club_ids(kandidaat, db))
    if mijn_clubs and zijn_clubs and not (mijn_clubs & zijn_clubs):
        return None
    return kandidaat


def _stuur_aanmeld_notificatie(
    db: Session, current_user: Member, partner: Member, event_naam: str
) -> None:
    afzender_naam = f"{current_user.voornaam} {current_user.achternaam}"
    db.add(Bericht(
        afzender_id=current_user.id,
        ontvanger_id=partner.id,
        onderwerp=f"Aangemeld voor {event_naam}",
        tekst=f"{afzender_naam} heeft jullie opgegeven voor {event_naam}",
        is_systeem=True,
    ))
    db.commit()


def _stuur_herhaal_notificatie(
    db: Session,
    current_user: Member,
    partner: Member,
    event_naam: str,
    tot: Optional[date],
) -> None:
    afzender_naam = f"{current_user.voornaam} {current_user.achternaam}"
    tekst = f"{afzender_naam} heeft jullie opgegeven voor een herhalende serie van {event_naam}"
    if tot:
        tekst += f" tot {tot.strftime('%d-%m-%Y')}"
    db.add(Bericht(
        afzender_id=current_user.id,
        ontvanger_id=partner.id,
        onderwerp=f"Herhaalaanmelding: {event_naam}",
        tekst=tekst,
        is_systeem=True,
    ))
    db.commit()


def _meld_niet_lid_wl(
    db: Session,
    request: Request,
    evening: ClubEvening,
    naam: str,
    afzender: Member,
    goedkeuring: bool,
) -> None:
    """Meldt WL's over een niet-lid-aanmelding: bericht altijd, e-mail alleen als
    SMTP geconfigureerd is. `goedkeuring=True` betekent dat de aanmelding nog
    goedgekeurd moet worden; anders is het puur informatief."""
    from app.email import send_niet_lid_goedkeuring_email, send_niet_lid_melding_email
    from app.routes.admin.helpers import _base_url

    event_naam = evening.naam or evening.type
    wedstrijdleiders = _club_wedstrijdleiders(db, evening.club_id)
    for wl in wedstrijdleiders:
        tekst = (
            f"{naam} (niet-lid) wil zich aanmelden voor {event_naam} en wacht op jouw goedkeuring."
            if goedkeuring
            else f"{naam} (niet-lid) is aangemeld voor {event_naam}. Ter informatie, geen actie nodig."
        )
        db.add(Bericht(
            afzender_id=afzender.id,
            ontvanger_id=wl.id,
            onderwerp=f"{'Goedkeuring nodig' if goedkeuring else 'Aanmelding niet-lid'}: {naam}",
            tekst=tekst,
            is_systeem=True,
        ))
    db.commit()

    if smtp_geconfigureerd():
        for wl in wedstrijdleiders:
            if not wl.email:
                continue
            try:
                if goedkeuring:
                    beheer_url = f"{_base_url(request)}/beheer/af-aanmeldingen/{evening.id}"
                    send_niet_lid_goedkeuring_email(
                        wl.email, wl.voornaam, naam, event_naam, evening.datum, beheer_url,
                    )
                else:
                    send_niet_lid_melding_email(wl.email, wl.voornaam, naam, event_naam, evening.datum)
            except Exception:
                logger.exception("E-mail niet-lid-melding versturen mislukt naar wedstrijdleider %s", wl.email)


def _niet_lid_redirect(
    db: Session,
    request: Request,
    evening: ClubEvening,
    current_user: Member,
    vereist: bool,
    beleid: Optional[str],
    gast_toegang: bool,
    normale_url: str,
) -> RedirectResponse:
    """Redirect na een aanmelding die (mogelijk) onder niet-ledenbeleid valt: stuurt
    een WL-melding wanneer nodig en geeft de bijpassende bevestigingspagina terug.
    `normale_url` is de redirect die zonder niet-ledenbeleid gebruikt zou worden."""
    naam = f"{current_user.voornaam} {current_user.achternaam}"
    if vereist and beleid == "goedkeuring":
        _meld_niet_lid_wl(db, request, evening, naam, current_user, goedkeuring=True)
        url = "/?gast=1&wacht_goedkeuring=1" if gast_toegang else "/?wacht_goedkeuring=1"
        return RedirectResponse(url=url, status_code=302)
    if vereist and beleid == "gemeld":
        _meld_niet_lid_wl(db, request, evening, naam, current_user, goedkeuring=False)
    url = normale_url
    if gast_toegang:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}gast=1"
    return RedirectResponse(url=url, status_code=302)


# Let op: deze route moet vóór /aanmelden/{event_id} staan, anders matcht
# "wijzigen" als event_id en geeft dat een 422.
@router.get("/aanmelden/wijzigen")
async def wijzigen_redirect(request: Request):
    return RedirectResponse(url="/", status_code=302)


def _gast_check(request: Request, current_user: Optional[Member], evening: ClubEvening) -> bool:
    """Bepaalt of dit een geldige gast-toegang is (geen login, wel een gastlink-sessie
    voor exact deze club) en raist 401 voor elke andere niet-ingelogde bezoeker."""
    if current_user:
        return False
    if not evening.club_id or request.session.get("gast_club_id") != evening.club_id:
        raise HTTPException(status_code=401, detail="Niet ingelogd")
    return True


@router.get("/aanmelden/{event_id}")
async def registration_form(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[Member] = Depends(get_current_user),
):
    from app.niet_leden import niet_lid_beleid

    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    if current_user:
        if not is_member_of_club(current_user, evening.club_id, db):
            raise HTTPException(status_code=403, detail="Geen lid van deze club")
        gast_toegang = False
    else:
        gast_toegang = _gast_check(request, current_user, evening)

    if evening.datum < date.today():
        return RedirectResponse(url="/", status_code=302)

    niet_lid_geblokkeerd = gast_toegang and niet_lid_beleid(evening.club) == "geblokkeerd"

    existing = None
    if current_user:
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == event_id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
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
            "gast_toegang": gast_toegang,
            "niet_lid_geblokkeerd": niet_lid_geblokkeerd,
        },
    )


@router.post("/aanmelden/{event_id}")
async def registration_submit(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[Member] = Depends(get_current_user),
):
    from app.niet_leden import is_bekend_lid, niet_lid_beleid, niet_lid_paar_beleid

    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    if current_user:
        if not is_member_of_club(current_user, evening.club_id, db):
            raise HTTPException(status_code=403, detail="Geen lid van deze club")
        gast_toegang = False
    else:
        gast_toegang = _gast_check(request, current_user, evening)

    if evening.datum < date.today():
        return RedirectResponse(url="/", status_code=302)

    form = await request.form()
    action = form.get("action", "aanmelden")

    if action == "afmelden":
        if gast_toegang:
            # Gasten hebben geen bestaande aanmelding om af te melden.
            return RedirectResponse(url="/?gast=1", status_code=302)

        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == event_id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )
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
        # Alleen mailen als er echt een aanmelding was om af te melden
        if existing and smtp_geconfigureerd():
            lid_naam = f"{current_user.voornaam} {current_user.achternaam}"
            event_naam = evening.naam or evening.type
            wedstrijdleiders = _club_wedstrijdleiders(db, evening.club_id)
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

    # Vanaf hier: aanmelden. Niet-leden (gasten) worden hier pas aangemaakt —
    # zo blijft een afmeld-verzoek (hierboven) volledig kosteloos.
    gast_niet_lid_beleid: Optional[str] = None
    if gast_toegang:
        gast_niet_lid_beleid = niet_lid_beleid(evening.club)
        if gast_niet_lid_beleid == "geblokkeerd":
            return RedirectResponse(url=f"/aanmelden/{event_id}?fout=niet_lid", status_code=302)

        eigen_voornaam = form.get("eigen_voornaam", "").strip()
        eigen_achternaam = form.get("eigen_achternaam", "").strip()
        if not eigen_voornaam or not eigen_achternaam:
            return RedirectResponse(url=f"/aanmelden/{event_id}?fout=eigen_naam", status_code=302)

        current_user = Member(
            voornaam=eigen_voornaam,
            achternaam=eigen_achternaam,
            lidnummer=f"GAST-{secrets.token_hex(6)}",
            role=MemberRole.lid.value,
        )
        db.add(current_user)
        db.commit()
        db.refresh(current_user)

    # "vereist" stuurt de bevestigingspagina/melding aan (goedkeuring én gemeld);
    # "db_goedkeuring" is het opgeslagen vlag dat de aanmelding uit de normale
    # lijsten houdt totdat de WL goedkeurt (alleen bij het beleid "goedkeuring").
    gast_niet_lid_vereist = gast_toegang and gast_niet_lid_beleid in ("goedkeuring", "gemeld")
    gast_db_goedkeuring = gast_toegang and gast_niet_lid_beleid == "goedkeuring"

    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()

    te_laat = _is_na_inschrijftermijn(evening)

    existing = None
    if not gast_toegang:
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == event_id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )

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
                # Nieuwe te-late wijziging: eerdere goedkeuring vervalt
                existing.te_laat_goedgekeurd = None
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                partner_naam=None,
                type=RegistrationType.los,
                status=RegistrationStatus.aangemeld,
                te_laat=te_laat,
                niet_lid_goedkeuring_vereist=gast_db_goedkeuring,
            ))
        db.commit()
        return _niet_lid_redirect(
            db, request, evening, current_user, gast_niet_lid_vereist, gast_niet_lid_beleid,
            gast_toegang, "/?te_laat=1" if te_laat else "/?bevestigd=1",
        )

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

        # Teamgenoten van wie de naam nieuw is of gewijzigd t.o.v. de vorige aanmelding
        teamgenoten_gewijzigd = [
            (vn, an)
            for vn, an, nieuw, oud in (
                (partner_voornaam, partner_achternaam, p1, existing.partner_naam if existing else None),
                (partner2_voornaam, partner2_achternaam, p2, existing.partner2_naam if existing else None),
                (partner3_voornaam, partner3_achternaam, p3, existing.partner3_naam if existing else None),
            )
            if nieuw and nieuw != oud
        ]

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
                # Nieuwe te-late wijziging: eerdere goedkeuring vervalt
                existing.te_laat_goedgekeurd = None
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
                niet_lid_goedkeuring_vereist=gast_db_goedkeuring,
            ))
        db.commit()

        for vn, an in teamgenoten_gewijzigd:
            teamgenoot_lid = _partner_lid(db, current_user, vn, an)
            if teamgenoot_lid:
                _stuur_aanmeld_notificatie(db, current_user, teamgenoot_lid, evening.naam or evening.type)

        normale_url = "/?aangemeld_onvolledig_team=1" if not volledig else ("/?te_laat=1" if te_laat else "/?bevestigd=1")
        return _niet_lid_redirect(
            db, request, evening, current_user, gast_niet_lid_vereist, gast_niet_lid_beleid,
            gast_toegang, normale_url,
        )

    # Paren (standaard): één partner opgeven
    if partner_voornaam and partner_achternaam:
        partner_naam = f"{partner_voornaam} {partner_achternaam}"
        partner_gewijzigd = not existing or existing.partner_naam != partner_naam

        paar_beleid = niet_lid_paar_beleid(evening.club) if not gast_toegang else "toegestaan"
        partner_onbekend = (
            not gast_toegang
            and paar_beleid != "toegestaan"
            and not is_bekend_lid(db, evening.club_id, partner_voornaam, partner_achternaam)
        )
        if partner_onbekend and paar_beleid == "verwijderd":
            return RedirectResponse(url=f"/aanmelden/{event_id}?fout=niet_lid_partner", status_code=302)
        partner_vereist = partner_onbekend and paar_beleid in ("goedkeuring", "gemeld")
        partner_db_goedkeuring = partner_onbekend and paar_beleid == "goedkeuring"
        niet_lid_vereist = gast_niet_lid_vereist or partner_vereist
        db_goedkeuring = gast_db_goedkeuring or partner_db_goedkeuring

        if existing:
            existing.status = RegistrationStatus.aangemeld
            existing.partner_naam = partner_naam
            existing.partner2_naam = None
            existing.partner3_naam = None
            if te_laat:
                existing.te_laat = True
                # Nieuwe te-late wijziging: eerdere goedkeuring vervalt
                existing.te_laat_goedgekeurd = None
            existing.niet_lid_goedkeuring_vereist = db_goedkeuring
            if db_goedkeuring:
                existing.niet_lid_goedgekeurd = None
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                partner_naam=partner_naam,
                type=RegistrationType.los,
                status=RegistrationStatus.aangemeld,
                te_laat=te_laat,
                niet_lid_goedkeuring_vereist=db_goedkeuring,
            ))
        db.commit()

        if partner_gewijzigd:
            partner_lid = _partner_lid(db, current_user, partner_voornaam, partner_achternaam)
            if partner_lid:
                _stuur_aanmeld_notificatie(db, current_user, partner_lid, evening.naam or evening.type)

        beleid_voor_melding = gast_niet_lid_beleid if gast_toegang else paar_beleid
        return _niet_lid_redirect(
            db, request, evening, current_user, niet_lid_vereist, beleid_voor_melding,
            gast_toegang, "/?te_laat=1" if te_laat else "/?bevestigd=1",
        )
    else:
        # Geen partner opgegeven bij paren
        if existing:
            existing.status = RegistrationStatus.beschikbaar_solo
            existing.partner_naam = None
            existing.partner2_naam = None
            existing.partner3_naam = None
            if te_laat:
                existing.te_laat = True
                # Nieuwe te-late wijziging: eerdere goedkeuring vervalt
                existing.te_laat_goedgekeurd = None
            existing.niet_lid_goedkeuring_vereist = gast_db_goedkeuring
            if gast_db_goedkeuring:
                existing.niet_lid_goedgekeurd = None
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                partner_naam=None,
                type=RegistrationType.los,
                status=RegistrationStatus.beschikbaar_solo,
                te_laat=te_laat,
                niet_lid_goedkeuring_vereist=gast_db_goedkeuring,
            ))
        db.commit()
        return _niet_lid_redirect(
            db, request, evening, current_user, gast_niet_lid_vereist, gast_niet_lid_beleid,
            gast_toegang, "/?te_laat=1" if te_laat else "/?aangemeld_zonder_partner=1",
        )


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

    user_club_ids = get_member_club_ids(current_user, db)
    if club_id and user_club_ids and club_id not in user_club_ids:
        raise HTTPException(status_code=403, detail="Geen lid van deze club")

    partner_naam = f"{partner_voornaam} {partner_achternaam}" if partner_voornaam and partner_achternaam else None

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
    elif user_club_ids:
        # Alleen avonden van eigen clubs (of legacy-avonden zonder club)
        q = q.filter(
            (ClubEvening.club_id.in_(user_club_ids)) | (ClubEvening.club_id.is_(None))
        )
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

    form = await request.form()
    alles = form.get("alles") == "on"
    alles_tot_str = form.get("alles_tot", "").strip()
    elke_str = form.get("elke", "").strip()
    herhaal_tot_str = form.get("herhaal_tot", "").strip()
    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()

    partner_naam = f"{partner_voornaam} {partner_achternaam}" if partner_voornaam and partner_achternaam else None

    today = date.today()
    user_club_ids = get_member_club_ids(current_user, db)

    def _events_query():
        query = (
            db.query(ClubEvening)
            .join(Season)
            .filter(
                ClubEvening.type.in_(_synoniemen(evening.type)),
                ClubEvening.datum >= today,
                Season.actief == True,  # noqa: E712
            )
        )
        if user_club_ids:
            query = query.filter(
                (ClubEvening.club_id.in_(user_club_ids)) | (ClubEvening.club_id.is_(None))
            )
        return query

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
        try:
            alles_tot = date.fromisoformat(alles_tot_str) if alles_tot_str else None
        except ValueError:
            return RedirectResponse(url=f"/aanmelden/{event_id}?fout=datum", status_code=302)

        query = _events_query()
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

        if count and partner_naam:
            partner_lid = _partner_lid(db, current_user, partner_voornaam, partner_achternaam)
            if partner_lid:
                _stuur_herhaal_notificatie(db, current_user, partner_lid, evening.type, alles_tot)

        return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)

    elif elke_str:
        try:
            elke = max(1, int(elke_str))
        except ValueError:
            elke = 1

        try:
            herhaal_tot = date.fromisoformat(herhaal_tot_str) if herhaal_tot_str else None
        except ValueError:
            return RedirectResponse(url=f"/aanmelden/{event_id}?fout=datum", status_code=302)

        query = _events_query()
        if herhaal_tot:
            query = query.filter(ClubEvening.datum <= herhaal_tot)

        future_events = query.order_by(ClubEvening.datum).all()
        selected = [evt for i, evt in enumerate(future_events) if i % elke == 0]
        count = _register_for_events(selected)

        db.commit()

        if count and partner_naam:
            partner_lid = _partner_lid(db, current_user, partner_voornaam, partner_achternaam)
            if partner_lid:
                _stuur_herhaal_notificatie(db, current_user, partner_lid, evening.type, herhaal_tot)

        return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)

    return RedirectResponse(url=f"/aanmelden/{event_id}", status_code=302)


# ── Definitief aanmelden voor alle evenementen van een type ───────────────────

_TYPE_MAP: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "avondeten": ["eten voor jeugdtraining"],
    "training": ["jeugdtraining", "training"],
    "speciaal": ["speciaal"],
}

@router.post("/definitief-aanmelden/{event_type}")
async def definitief_aanmelden(
    event_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    if event_type not in _TYPE_MAP:
        raise HTTPException(status_code=400, detail="Onbekend type")

    form = await request.form()
    partner_naam = None
    if form.get("met_partner") == "1":
        partner_voornaam = form.get("partner_voornaam", "").strip()
        partner_achternaam = form.get("partner_achternaam", "").strip()
        if partner_voornaam and partner_achternaam:
            partner_naam = f"{partner_voornaam} {partner_achternaam}"

    club_id_raw = form.get("club_id", "").strip()
    club_id = int(club_id_raw) if club_id_raw.isdigit() else None

    user_club_ids = get_member_club_ids(current_user, db)
    if club_id and user_club_ids and club_id not in user_club_ids:
        raise HTTPException(status_code=403, detail="Geen lid van deze club")

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
    elif user_club_ids:
        q = q.filter(
            (ClubEvening.club_id.in_(user_club_ids)) | (ClubEvening.club_id.is_(None))
        )
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
    from app.club_settings import merged_event_types

    form = await request.form()
    # Alleen de types die de club(s) van dit lid gebruiken; types die de club
    # niet gebruikt worden nooit als verborgen opgeslagen (clubinstellingen).
    club_ids = get_member_club_ids(current_user, db)
    user_clubs = db.query(Club).filter(Club.id.in_(club_ids)).all() if club_ids else []
    beschikbaar = merged_event_types(user_clubs)
    hidden = [k for k in beschikbaar if not form.get(f"toon_{k}")]
    current_user.verborgen_types = ",".join(hidden)
    db.commit()
    return RedirectResponse(url="/?voorkeuren_opgeslagen=1", status_code=302)


# ── Profielpagina ─────────────────────────────────────────────────────────────

@router.get("/profiel")
async def mijn_profiel(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    today = date.today()

    agenda = (
        db.query(Registration)
        .filter(
            or_(
                Registration.person1_id == current_user.id,
                Registration.person2_id == current_user.id,
            ),
            Registration.status != RegistrationStatus.afgemeld,
        )
        .join(ClubEvening)
        .filter(ClubEvening.datum >= today)
        .order_by(ClubEvening.datum.asc())
        .all()
    )

    registrations = (
        db.query(Registration)
        .filter(
            or_(
                Registration.person1_id == current_user.id,
                Registration.person2_id == current_user.id,
            )
        )
        .join(ClubEvening)
        .filter(ClubEvening.datum < today)
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

    club_ids = {
        mc.club_id
        for mc in db.query(MemberClub)
        .filter(MemberClub.member_id == current_user.id)
        .all()
    }
    algemeen_id = get_algemene_club_id(db)
    if algemeen_id is not None:
        club_ids.add(algemeen_id)
    mijn_clubs = (
        db.query(Club).filter(Club.id.in_(club_ids)).order_by(Club.naam).all()
        if club_ids
        else []
    )

    return templates.TemplateResponse(
        request,
        "profiel.html",
        {
            "current_user": current_user,
            "agenda": agenda,
            "registrations": registrations,
            "herhalingen": herhalingen,
            "mijn_clubs": mijn_clubs,
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
            partner_naam = f"{partner_voornaam} {partner_achternaam}"

    club_id_raw = form.get("club_id", "").strip()
    club_id = int(club_id_raw) if club_id_raw.isdigit() else None

    user_club_ids = get_member_club_ids(current_user, db)
    if club_id and user_club_ids and club_id not in user_club_ids:
        raise HTTPException(status_code=403, detail="Geen lid van deze club")

    today = date.today()
    all_db_types = ["clubavond", "regulier", "eten voor jeugdtraining", "speciaal", "jeugdtraining", "training"]

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
    elif user_club_ids:
        q = q.filter(
            (ClubEvening.club_id.in_(user_club_ids)) | (ClubEvening.club_id.is_(None))
        )
    future_events = q.order_by(ClubEvening.datum).all()

    count = 0
    nieuw_aangemeld = []
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
            nieuw_aangemeld.append(evt)
            count += 1

    db.commit()

    if nieuw_aangemeld:
        regels = "\n".join(
            f"- {e.naam or e.type} ({e.datum.strftime('%d-%m-%Y')})"
            for e in nieuw_aangemeld
        )
        n = len(nieuw_aangemeld)
        db.add(Bericht(
            afzender_id=current_user.id,
            ontvanger_id=current_user.id,
            onderwerp=f"Aangemeld voor {n} evenement{'en' if n != 1 else ''}",
            tekst=f"Je bent aangemeld voor de volgende {n} evenement{'en' if n != 1 else ''}:\n\n{regels}",
            is_systeem=True,
        ))
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

    # Annuleer ook openstaande partnerverzoeken (net als bij per-avond afmelden)
    pr_q = db.query(PartnerRequest).filter(
        PartnerRequest.requester_id == current_user.id,
        PartnerRequest.status == "wachtend",
        PartnerRequest.evening_id.in_(
            db.query(ClubEvening.id).filter(ClubEvening.datum >= today)
        ),
    )
    if partner_naam:
        vn, an = form.get("partner_voornaam", "").strip(), form.get("partner_achternaam", "").strip()
        pr_q = pr_q.filter(
            func.lower(PartnerRequest.partner_voornaam) == vn.lower(),
            func.lower(PartnerRequest.partner_achternaam) == an.lower(),
        )
    pr_q.delete(synchronize_session=False)

    db.commit()

    if upcoming_regs:
        regels = "\n".join(
            f"- {reg.evening.naam or reg.evening.type} ({reg.evening.datum.strftime('%d-%m-%Y')})"
            for reg in upcoming_regs
        )
        db.add(Bericht(
            afzender_id=current_user.id,
            ontvanger_id=current_user.id,
            onderwerp=f"Afgemeld voor {count} evenement{'en' if count != 1 else ''}",
            tekst=f"Je bent afgemeld voor de volgende {count} evenement{'en' if count != 1 else ''}:\n\n{regels}",
            is_systeem=True,
        ))
        db.commit()

    if smtp_geconfigureerd() and upcoming_regs:
        lid_naam = f"{current_user.voornaam} {current_user.achternaam}"
        # Per club de eigen wedstrijdleiders mailen, alleen over avonden van die club
        per_club: dict = {}
        for reg in upcoming_regs:
            club_key = reg.evening.club_id if reg.evening else None
            per_club.setdefault(club_key, []).append(
                (reg.evening.naam or reg.evening.type, reg.evening.datum)
            )
        for club_key, events in per_club.items():
            for wl in _club_wedstrijdleiders(db, club_key):
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
