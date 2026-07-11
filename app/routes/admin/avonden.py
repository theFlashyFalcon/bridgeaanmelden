"""Beheer: avonden en seizoenen."""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    get_admin_club,
    is_member_of_club,
    require_admin,
    require_wedstrijdleider,
)
from app.database import get_db
from app.models import (
    Bericht,
    ClubEvening,
    ManualPair,
    Member,
    PartnerRequest,
    RecurringRegistration,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
    Uitslag,
)
from app.templates_env import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beheer")


def _seizoen_overlapt(
    db: Session, club_id: Optional[int], start: date, eind: date
) -> bool:
    """True als deze club al een seizoen heeft dat deze periode overlapt."""
    return (
        db.query(Season)
        .filter(
            Season.club_id == club_id,
            Season.start_datum <= eind,
            Season.eind_datum >= start,
        )
        .first()
        is not None
    )


EVENING_TYPES = [
    ("clubavond", "Clubavond"),
    ("jeugdtraining", "Jeugdtraining"),
    ("eten voor jeugdtraining", "Eten voor jeugdtraining"),
    ("speciaal", "Speciaal"),
]


# Legacy-synoniemen: "regulier" en "clubavond" (resp. "training" en "jeugdtraining")
# zijn hetzelfde type evenement onder een oude/nieuwe naam.
_TYPE_SYNONIEMEN: dict[str, list[str]] = {
    "clubavond": ["clubavond", "regulier"],
    "regulier": ["clubavond", "regulier"],
    "jeugdtraining": ["jeugdtraining", "training"],
    "training": ["jeugdtraining", "training"],
    "eten voor jeugdtraining": ["eten voor jeugdtraining"],
    "speciaal": ["speciaal"],
}

_TRAINING_DB_TYPES = {"jeugdtraining", "training"}


def _synoniemen(event_type: str) -> list[str]:
    return _TYPE_SYNONIEMEN.get(event_type, [event_type])


def _apply_recurring_registrations(db: Session, event: ClubEvening, sender_id: Optional[int] = None) -> None:
    recurring_regs = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.event_type.in_(_synoniemen(event.type)),
            RecurringRegistration.actief == True,  # noqa: E712
        )
        .all()
    )
    is_training = event.type in _TRAINING_DB_TYPES
    for rr in recurring_regs:
        member = rr.member
        if member is None or member.verwijderd_op is not None:
            continue
        if is_training and not member.training_eligible:
            continue
        if not is_member_of_club(member, event.club_id, db):
            continue
        if rr.herhaal_tot and rr.herhaal_tot < event.datum:
            continue
        if rr.interval > 1:
            count_q = (
                db.query(ClubEvening)
                .filter(
                    ClubEvening.type.in_(_synoniemen(event.type)),
                    ClubEvening.datum >= rr.referentie_datum,
                    ClubEvening.datum < event.datum,
                )
            )
            if event.club_id:
                count_q = count_q.filter(ClubEvening.club_id == event.club_id)
            count = count_q.count()
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
            deelnemers_type = event.deelnemers_type or "paren"
            if deelnemers_type == "individueel":
                reg_partner = None
                status = RegistrationStatus.aangemeld
            elif deelnemers_type == "paren" and rr.partner_naam:
                reg_partner = rr.partner_naam
                status = RegistrationStatus.aangemeld
            else:
                reg_partner = None
                status = RegistrationStatus.beschikbaar_solo
            db.add(Registration(
                evening_id=event.id,
                person1_id=rr.member_id,
                partner_naam=reg_partner,
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
                    is_systeem=True,
                ))


# ── Avonden (Wedstrijdleider + Admin) ─────────────────────────────────────────

@router.get("/avonden")
async def avonden_list(
    request: Request,
    pagina: int = 1,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = get_admin_club(current_user, db, request)
    PER_PAGINA = 30
    totaal = db.query(ClubEvening).filter(ClubEvening.club_id == club.id).count() if club else 0
    totaal_paginas = max(1, (totaal + PER_PAGINA - 1) // PER_PAGINA)
    pagina = max(1, min(pagina, totaal_paginas))
    seasons = (
        db.query(Season)
        .filter(Season.club_id == club.id)
        .order_by(Season.start_datum.desc())
        .all()
    ) if club else []
    evenings = (
        db.query(ClubEvening)
        .join(Season)
        .filter(ClubEvening.club_id == club.id)
        .order_by(ClubEvening.datum.desc())
        .offset((pagina - 1) * PER_PAGINA)
        .limit(PER_PAGINA)
        .all()
    ) if club else []
    from app.club_settings import LABEL_NAMEN, enabled_event_types, enabled_labels

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
            "beschikbare_types": enabled_event_types(club),
            "beschikbare_labels": [(k, LABEL_NAMEN[k]) for k in enabled_labels(club)],
        },
    )


@router.post("/avonden/seizoen")
async def seizoen_add_from_beheren(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = get_admin_club(current_user, db, request)
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

    club_id = club.id if club else None
    if _seizoen_overlapt(db, club_id, start, eind):
        return RedirectResponse(url="/beheer/avonden?fout=overlap", status_code=302)

    actief = form.get("actief") == "on"
    if actief and club:
        db.query(Season).filter(Season.club_id == club.id).update({"actief": False})
    db.add(Season(naam=naam, start_datum=start, eind_datum=eind, actief=actief, club_id=club_id))
    db.commit()
    return RedirectResponse(url="/beheer/avonden?seizoen_aangemaakt=1", status_code=302)


@router.post("/avonden")
async def avonden_add(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = get_admin_club(current_user, db, request)
    form = await request.form()
    from app.club_settings import LABEL_KEYS

    naam = form.get("naam", "").strip()
    datum_str = form.get("datum", "")
    type_ = form.get("type", "clubavond")
    deelnemers_type = form.get("deelnemers_type", "paren")
    label_raw = form.get("label", "").strip()
    label = label_raw if label_raw in LABEL_KEYS else None

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
        season_q = db.query(Season).filter(Season.start_datum <= datum, Season.eind_datum >= datum)
        if club:
            season_q = season_q.filter(Season.club_id == club.id)
        season = season_q.first()
        if not season:
            errors.append(f"Geen seizoen gevonden voor {datum_str}. Maak eerst een seizoen aan dat deze datum omvat.")

    if errors:
        seasons = (
            db.query(Season)
            .filter(Season.club_id == club.id)
            .order_by(Season.start_datum.desc())
            .all()
        ) if club else []
        evenings = (
            db.query(ClubEvening)
            .join(Season)
            .filter(ClubEvening.club_id == club.id)
            .order_by(ClubEvening.datum)
            .all()
        ) if club else []
        from app.club_settings import LABEL_NAMEN, enabled_event_types, enabled_labels

        return templates.TemplateResponse(
            request,
            "admin/avonden.html",
            {
                "current_user": current_user,
                "evenings": evenings,
                "seasons": seasons,
                "errors": errors,
                "open_type": type_,
                "beschikbare_types": enabled_event_types(club),
                "beschikbare_labels": [(k, LABEL_NAMEN[k]) for k in enabled_labels(club)],
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

    club_id = club.id if club else None
    new_events = []
    first_event = ClubEvening(naam=naam, datum=datum, type=type_, deelnemers_type=deelnemers_type,
                               inschrijftermijn_uren=inschrijftermijn_uren, season_id=season.id,
                               club_id=club_id, label=label)
    db.add(first_event)
    db.flush()
    new_events.append(first_event)

    if herhaal_tot_str:
        try:
            # max(1, ...): 0 of negatief zou delta ≤ 0 geven en de while-lus oneindig maken
            herhaal_elke = max(1, int(herhaal_elke_str))
            herhaal_tot = date.fromisoformat(herhaal_tot_str)
            if herhaal_eenheid == "dagen":
                delta = timedelta(days=herhaal_elke)
            else:
                delta = timedelta(weeks=herhaal_elke)

            next_datum = datum + delta
            while next_datum <= herhaal_tot and len(new_events) < 200:
                next_season = (
                    db.query(Season)
                    .filter(Season.start_datum <= next_datum, Season.eind_datum >= next_datum,
                            Season.club_id == club_id)
                    .first()
                )
                if next_season:
                    evt = ClubEvening(naam=naam, datum=next_datum, type=type_, deelnemers_type=deelnemers_type,
                                      inschrijftermijn_uren=inschrijftermijn_uren, season_id=next_season.id,
                                      club_id=club_id, label=label)
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


# ── Seizoenen (Admin only) ────────────────────────────────────────────────────

@router.get("/seizoenen")
async def seizoenen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    club = get_admin_club(current_user, db, request)
    seasons = (
        db.query(Season)
        .filter(Season.club_id == club.id)
        .order_by(Season.start_datum.desc())
        .all()
    ) if club else []
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
    club = get_admin_club(current_user, db, request)
    form = await request.form()
    naam = form.get("naam", "").strip()
    start = form.get("start_datum", "")
    eind = form.get("eind_datum", "")
    actief = form.get("actief") == "on"

    if naam and start and eind:
        try:
            start_datum = date.fromisoformat(start)
            eind_datum = date.fromisoformat(eind)
        except ValueError:
            return RedirectResponse(url="/beheer/seizoenen?fout=datum", status_code=302)
        if start_datum >= eind_datum:
            return RedirectResponse(url="/beheer/seizoenen?fout=datum", status_code=302)
        club_id = club.id if club else None
        if _seizoen_overlapt(db, club_id, start_datum, eind_datum):
            return RedirectResponse(url="/beheer/seizoenen?fout=overlap", status_code=302)
        if actief and club:
            db.query(Season).filter(Season.club_id == club.id).update({"actief": False})
        db.add(Season(
            naam=naam,
            start_datum=start_datum,
            eind_datum=eind_datum,
            actief=actief,
            club_id=club_id,
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
    club = get_admin_club(current_user, db, request)
    if club:
        db.query(Season).filter(Season.club_id == club.id).update({"actief": False})
    season = db.query(Season).filter(Season.id == season_id).first()
    if season and (not club or season.club_id == club.id):
        season.actief = True
    db.commit()
    return RedirectResponse(url="/beheer/seizoenen", status_code=302)


# ── Clubinstellingen (Wedstrijdleider + Admin) ────────────────────────────────

@router.get("/instellingen")
async def instellingen_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    from app.club_settings import (
        EVENT_TYPE_KEUZES,
        LABEL_KEUZES,
        RANKING_KEUZES,
        enabled_event_types,
        enabled_labels,
        enabled_rankings,
    )
    from app.niet_leden import (
        NIET_LID_BELEID_KEUZES,
        NIET_LID_PAAR_BELEID_KEUZES,
        maak_gast_token,
        niet_lid_beleid,
        niet_lid_paar_beleid,
    )
    from app.routes.admin.helpers import _base_url

    club = get_admin_club(current_user, db, request)

    gast_link = None
    if club is not None:
        if not club.gast_token:
            club.gast_token = maak_gast_token()
            db.commit()
            db.refresh(club)
        gast_link = f"{_base_url(request)}/gast/{club.gast_token}"

    return templates.TemplateResponse(
        request,
        "admin/instellingen.html",
        {
            "current_user": current_user,
            "club": club,
            "event_type_keuzes": EVENT_TYPE_KEUZES,
            "ranking_keuzes": RANKING_KEUZES,
            "label_keuzes": LABEL_KEUZES,
            "actieve_types": enabled_event_types(club),
            "actieve_rankings": enabled_rankings(club),
            "actieve_labels": enabled_labels(club),
            "niet_lid_beleid_keuzes": NIET_LID_BELEID_KEUZES,
            "niet_lid_paar_beleid_keuzes": NIET_LID_PAAR_BELEID_KEUZES,
            "actief_niet_lid_beleid": niet_lid_beleid(club),
            "actief_niet_lid_paar_beleid": niet_lid_paar_beleid(club),
            "gast_link": gast_link,
        },
    )


@router.post("/instellingen")
async def instellingen_save(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    from app.club_settings import EVENT_TYPE_KEYS, LABEL_KEYS, RANKING_KEYS
    from app.niet_leden import NIET_LID_BELEID_KEYS, NIET_LID_PAAR_BELEID_KEYS

    club = get_admin_club(current_user, db, request)
    if not club:
        return RedirectResponse(url="/beheer/instellingen?fout=geen_club", status_code=302)

    form = await request.form()
    gekozen_types = [k for k in EVENT_TYPE_KEYS if form.get(f"type_{k}")]
    gekozen_rankings = [k for k in RANKING_KEYS if form.get(f"ranking_{k}")]
    gekozen_labels = [k for k in LABEL_KEYS if form.get(f"label_{k}")]

    if not gekozen_types:
        return RedirectResponse(url="/beheer/instellingen?fout=geen_types", status_code=302)
    if not gekozen_rankings:
        return RedirectResponse(url="/beheer/instellingen?fout=geen_rankings", status_code=302)
    if not gekozen_labels:
        return RedirectResponse(url="/beheer/instellingen?fout=geen_labels", status_code=302)

    club.evenement_types = ",".join(gekozen_types)
    club.ranking_weergaves = ",".join(gekozen_rankings)
    club.labels = ",".join(gekozen_labels)

    niet_lid_beleid = form.get("niet_lid_beleid", "")
    if niet_lid_beleid in NIET_LID_BELEID_KEYS:
        club.niet_lid_beleid = niet_lid_beleid
    niet_lid_paar_beleid = form.get("niet_lid_paar_beleid", "")
    if niet_lid_paar_beleid in NIET_LID_PAAR_BELEID_KEYS:
        club.niet_lid_paar_beleid = niet_lid_paar_beleid

    db.commit()
    return RedirectResponse(url="/beheer/instellingen?opgeslagen=1", status_code=302)


@router.post("/instellingen/gastlink-mail")
async def instellingen_gastlink_mail(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    from app.email import send_gastlink_email, smtp_geconfigureerd
    from app.niet_leden import maak_gast_token
    from app.routes.admin.helpers import _base_url

    club = get_admin_club(current_user, db, request)
    if not club:
        return RedirectResponse(url="/beheer/instellingen?fout=geen_club", status_code=302)

    form = await request.form()
    email = form.get("email", "").strip()
    if not email:
        return RedirectResponse(url="/beheer/instellingen?mail_fout=1", status_code=302)

    if not club.gast_token:
        club.gast_token = maak_gast_token()
        db.commit()

    if not smtp_geconfigureerd():
        return RedirectResponse(url="/beheer/instellingen?mail_fout=1", status_code=302)

    link = f"{_base_url(request)}/gast/{club.gast_token}"
    try:
        send_gastlink_email(email, club.naam, link)
    except Exception:
        logger.exception("Gastlink-mail versturen mislukt naar %s", email)
        return RedirectResponse(url="/beheer/instellingen?mail_fout=1", status_code=302)

    return RedirectResponse(url="/beheer/instellingen?mail_verstuurd=1", status_code=302)


