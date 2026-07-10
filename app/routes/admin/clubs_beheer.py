"""Beheer: clubs, club-ledenlijsten en weergave-instellingen."""
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin, require_wedstrijdleider
from app.database import get_db
from app.models import Club, Lid, Member, MemberClub, MemberRole
from app.templates_env import templates

router = APIRouter(prefix="/beheer")


# ── Actieve beheer-club instellen (Admin + Wedstrijdleider) ──────────────────

@router.get("/actieve-club/{club_id}")
async def actieve_club_instellen(
    club_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    """Slaat de actieve beheer-club op in de sessie en stuurt terug naar de vorige pagina."""
    if current_user.role != MemberRole.admin.value:
        mc = db.query(MemberClub).filter(
            MemberClub.member_id == current_user.id,
            MemberClub.club_id == club_id,
            MemberClub.role.in_([MemberRole.admin.value, MemberRole.wedstrijdleider.value]),
        ).first()
        if not mc:
            raise HTTPException(status_code=403, detail="Geen toegang tot deze club")
    else:
        club = db.query(Club).filter(Club.id == club_id).first()
        if not club:
            raise HTTPException(status_code=404, detail="Club niet gevonden")

    request.session["active_beheer_club_id"] = club_id

    terug = "/beheer/avonden"
    referer = request.headers.get("referer")
    if referer:
        # Referer is een volledige URL (incl. host) — alleen het pad (+query)
        # overnemen, nooit de host, om open redirects te voorkomen.
        onderdelen = urlsplit(referer)
        if onderdelen.path.startswith("/") and not onderdelen.path.startswith("//"):
            terug = onderdelen.path
            if onderdelen.query:
                terug += f"?{onderdelen.query}"

    return RedirectResponse(url=terug, status_code=302)


# ── Clubs (Admin only) ────────────────────────────────────────────────────────

@router.get("/clubs")
async def clubs_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    clubs = db.query(Club).order_by(Club.naam).all()
    lid_counts = {}
    for club in clubs:
        if club.is_algemeen:
            # Iedereen is automatisch lid van de algemene club
            lid_counts[club.id] = (
                db.query(Member).filter(Member.verwijderd_op.is_(None)).count()
            )
        else:
            lid_counts[club.id] = db.query(MemberClub).filter(MemberClub.club_id == club.id).count()
    ledenlijst_counts = {}
    for club in clubs:
        ledenlijst_counts[club.id] = db.query(Lid).filter(Lid.club_id == club.id).count()
    return templates.TemplateResponse(
        request,
        "admin/clubs.html",
        {
            "current_user": current_user,
            "clubs": clubs,
            "lid_counts": lid_counts,
            "ledenlijst_counts": ledenlijst_counts,
        },
    )


@router.post("/clubs")
async def club_toevoegen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    stad = form.get("stad", "").strip() or None
    kleur = form.get("kleur", "").strip() or None
    if naam:
        db.add(Club(naam=naam, stad=stad, kleur=kleur))
        db.commit()
    return RedirectResponse(url="/beheer/clubs?aangemaakt=1", status_code=302)


@router.post("/clubs/{club_id}/update")
async def club_update(
    club_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    stad = form.get("stad", "").strip() or None
    kleur = form.get("kleur", "").strip() or None
    club = db.query(Club).filter(Club.id == club_id).first()
    if club and naam:
        club.naam = naam
        club.stad = stad
        club.kleur = kleur
        db.commit()
    return RedirectResponse(url="/beheer/clubs?opgeslagen=1", status_code=302)


@router.post("/clubs/{club_id}/verwijder")
async def club_verwijder(
    club_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if club and club.is_algemeen:
        return RedirectResponse(url="/beheer/clubs?fout=algemeen", status_code=302)
    if club:
        db.delete(club)
        db.commit()
    return RedirectResponse(url="/beheer/clubs?verwijderd=1", status_code=302)


@router.post("/clubs/{club_id}/leden/importeer")
async def club_leden_importeer(
    club_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    import csv
    import io

    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="Club niet gevonden")

    form = await request.form()
    bestand = form.get("bestand")
    if not bestand or not bestand.filename:
        return RedirectResponse(url="/beheer/clubs?import_fout=1", status_code=302)

    inhoud = await bestand.read()
    try:
        tekst = inhoud.decode("utf-8-sig")
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
                Lid.club_id == club_id,
            )
            .first()
        )
        if not al_aanwezig:
            db.add(Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb, club_id=club_id))
            toegevoegd += 1
        else:
            overgeslagen += 1
    db.commit()
    return RedirectResponse(
        url=f"/beheer/clubs?import_ok={toegevoegd}&overgeslagen={overgeslagen}",
        status_code=302,
    )


# ── Club-ledenlijst beheren (Admin + wedstrijdleider van de club) ─────────────

def _vereis_clubbeheer(current_user: Member, club_id: int, db: Session) -> Club:
    """Geeft de club terug als current_user die mag beheren: globale admins
    altijd, anders is een wedstrijdleider/admin-rol bij deze club vereist."""
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="Club niet gevonden")
    if current_user.role == MemberRole.admin.value:
        return club
    mc = db.query(MemberClub).filter(
        MemberClub.member_id == current_user.id,
        MemberClub.club_id == club_id,
        MemberClub.role.in_([MemberRole.admin.value, MemberRole.wedstrijdleider.value]),
    ).first()
    if not mc:
        raise HTTPException(status_code=403, detail="Geen toegang tot deze club")
    return club


def _toewijsbare_rollen(current_user: Member) -> list[str]:
    """Rollen die deze beheerder mag toekennen: alleen admins de admin-rol."""
    if current_user.role == MemberRole.admin.value:
        return [r.value for r in MemberRole]
    return [MemberRole.lid.value, MemberRole.wedstrijdleider.value]


@router.get("/clubs/{club_id}/leden")
async def club_leden_beheer(
    club_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    club = _vereis_clubbeheer(current_user, club_id, db)

    mc_rows = db.query(MemberClub).filter(MemberClub.club_id == club_id).all()
    member_ids = [mc.member_id for mc in mc_rows]
    member_map: dict[int, Member] = {}
    if member_ids:
        member_map = {
            m.id: m for m in db.query(Member)
            .filter(Member.id.in_(member_ids), Member.verwijderd_op.is_(None))
            .all()
        }

    club_leden = sorted(
        [{"mc": mc, "member": member_map[mc.member_id]}
         for mc in mc_rows if mc.member_id in member_map],
        key=lambda x: (x["member"].achternaam or "", x["member"].voornaam or ""),
    )

    existing_ids = set(member_ids)
    if existing_ids:
        alle_members = (
            db.query(Member)
            .filter(Member.verwijderd_op.is_(None), Member.id.notin_(existing_ids))
            .order_by(Member.achternaam, Member.voornaam)
            .all()
        )
    else:
        alle_members = (
            db.query(Member)
            .filter(Member.verwijderd_op.is_(None))
            .order_by(Member.achternaam, Member.voornaam)
            .all()
        )

    return templates.TemplateResponse(
        request,
        "admin/club_leden.html",
        {
            "current_user": current_user,
            "club": club,
            "club_leden": club_leden,
            "alle_members": alle_members,
            "roles": _toewijsbare_rollen(current_user),
        },
    )


@router.post("/clubs/{club_id}/leden/toevoegen")
async def club_lid_toevoegen(
    club_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    _vereis_clubbeheer(current_user, club_id, db)

    form = await request.form()
    member_id_str = form.get("member_id", "").strip()
    role = form.get("role", MemberRole.lid.value).strip()

    if role not in _toewijsbare_rollen(current_user):
        role = MemberRole.lid.value

    try:
        member_id = int(member_id_str)
    except (ValueError, TypeError):
        return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?fout=lid", status_code=302)

    member = db.query(Member).filter(Member.id == member_id, Member.verwijderd_op.is_(None)).first()
    if not member:
        return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?fout=lid", status_code=302)

    existing = db.query(MemberClub).filter(
        MemberClub.club_id == club_id, MemberClub.member_id == member_id,
    ).first()
    if not existing:
        db.add(MemberClub(member_id=member_id, club_id=club_id, role=role))
        db.flush()  # autoflush staat uit; zonder flush ziet _sync_global_role de nieuwe rij niet
        _sync_global_role(member, db)
        db.commit()

    return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?toegevoegd=1", status_code=302)


@router.post("/clubs/{club_id}/leden/{member_id}/rol")
async def club_lid_rol_wijzigen(
    club_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    _vereis_clubbeheer(current_user, club_id, db)

    form = await request.form()
    role = form.get("role", "").strip()
    if role not in _toewijsbare_rollen(current_user):
        return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?fout=rol", status_code=302)

    mc = db.query(MemberClub).filter(
        MemberClub.club_id == club_id, MemberClub.member_id == member_id,
    ).first()
    if not mc:
        return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?fout=lid", status_code=302)

    # Wedstrijdleiders mogen de rol van een club-admin niet aanpassen
    is_admin = current_user.role == MemberRole.admin.value
    if mc.role == MemberRole.admin.value and not is_admin:
        return RedirectResponse(
            url=f"/beheer/clubs/{club_id}/leden?fout=rol", status_code=302
        )

    mc.role = role
    member = db.query(Member).filter(Member.id == member_id).first()
    if member:
        _sync_global_role(member, db)
    db.commit()
    return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?opgeslagen=1", status_code=302)


@router.post("/clubs/{club_id}/leden/{member_id}/verwijder")
async def club_lid_uit_club_verwijder(
    club_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    _vereis_clubbeheer(current_user, club_id, db)

    mc = db.query(MemberClub).filter(
        MemberClub.club_id == club_id, MemberClub.member_id == member_id,
    ).first()
    # Wedstrijdleiders mogen een club-admin niet uit de club verwijderen
    is_admin = current_user.role == MemberRole.admin.value
    if mc and mc.role == MemberRole.admin.value and not is_admin:
        return RedirectResponse(
            url=f"/beheer/clubs/{club_id}/leden?fout=rol", status_code=302
        )
    if mc:
        db.delete(mc)
        member = db.query(Member).filter(Member.id == member_id).first()
        if member:
            remaining = db.query(MemberClub).filter(
                MemberClub.member_id == member_id, MemberClub.club_id != club_id,
            ).all()
            if remaining:
                roles = [r.role for r in remaining]
                if MemberRole.admin.value in roles:
                    member.role = MemberRole.admin.value
                elif MemberRole.wedstrijdleider.value in roles:
                    member.role = MemberRole.wedstrijdleider.value
                else:
                    member.role = MemberRole.lid.value
        db.commit()
    return RedirectResponse(url=f"/beheer/clubs/{club_id}/leden?verwijderd=1", status_code=302)


def _sync_global_role(member: Member, db: Session) -> None:
    """Synchroniseert member.role met de hoogste rol in alle MemberClub rijen."""
    all_mc = db.query(MemberClub).filter(MemberClub.member_id == member.id).all()
    roles = [mc.role for mc in all_mc]
    if MemberRole.admin.value in roles:
        member.role = MemberRole.admin.value
    elif MemberRole.wedstrijdleider.value in roles:
        member.role = MemberRole.wedstrijdleider.value
    else:
        member.role = MemberRole.lid.value


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
