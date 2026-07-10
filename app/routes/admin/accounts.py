"""Beheer: uitnodigingen, accountaanvragen, rollen, ledenlijst en SMTP-test."""
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_admin_club, require_admin
from app.database import get_db
from app.models import (
    AccountRequest,
    AccountRequestStatus,
    AdminBericht,
    Club,
    EmailRoleAssignment,
    Invitation,
    Lid,
    Member,
    MemberClub,
    MemberRole,
)
from app.routes.admin.helpers import _base_url
from app.templates_env import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beheer")


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
    club = get_admin_club(current_user, db, request)
    invitations = (
        db.query(Invitation)
        .filter(Invitation.club_id == club.id)
        .order_by(Invitation.aangemaakt_op.desc())
        .all()
    ) if club else []
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

    club = get_admin_club(current_user, db, request)
    form = await request.form()
    email = form.get("email", "").strip().lower()
    role = form.get("role", MemberRole.lid.value)
    if role not in [r.value for r in MemberRole]:
        role = MemberRole.lid.value

    if not email:
        return RedirectResponse(url="/beheer/uitnodigingen?error=email_required", status_code=302)

    # Set role assignment
    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    if assignment:
        assignment.role = role
    else:
        db.add(EmailRoleAssignment(email=email, role=role))

    token = secrets.token_urlsafe(32)
    invitation = Invitation(token=token, email=email, club_id=club.id if club else None)
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
    club = get_admin_club(current_user, db, request)
    PER_PAGINA = 20
    base_q = db.query(AccountRequest)
    if club:
        base_q = base_q.filter(AccountRequest.club_id == club.id)
    totaal = base_q.count()
    totaal_paginas = max(1, (totaal + PER_PAGINA - 1) // PER_PAGINA)
    pagina = max(1, min(pagina, totaal_paginas))
    aanvragen = (
        base_q
        .order_by(AccountRequest.aangemaakt_op.desc())
        .offset((pagina - 1) * PER_PAGINA)
        .limit(PER_PAGINA)
        .all()
    )
    pending_count = (
        base_q
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
    role = form.get("role", MemberRole.lid.value)
    if role not in [r.value for r in MemberRole]:
        role = MemberRole.lid.value

    aanvraag = db.query(AccountRequest).filter(AccountRequest.id == aanvraag_id).first()
    if not aanvraag or aanvraag.status != AccountRequestStatus.wachtend:
        return RedirectResponse(url="/beheer/aanvragen", status_code=302)

    aanvraag.status = AccountRequestStatus.goedgekeurd
    aanvraag.beoordeeld_op = datetime.now(timezone.utc)

    if aanvraag.wachtwoord_hash:
        # User provided a password during registration — create member directly.
        # Lidnummer is de onderscheidende factor voor een account, niet e-mail.
        al_bestaat = (
            db.query(Member)
            .filter(Member.lidnummer == aanvraag.lidnummer)
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
            toestemming_op=aanvraag.toestemming_op,
        )
        db.add(member)
        db.flush()
        club_id = aanvraag.club_id or (db.query(Club).first() or Club()).id
        if club_id:
            db.add(MemberClub(member_id=member.id, club_id=club_id, role=role))
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
    club = get_admin_club(current_user, db, request)
    PER_PAGINA = 50
    base_q = db.query(Lid)
    if club:
        base_q = base_q.filter(Lid.club_id == club.id)
    totaal = base_q.count()
    totaal_paginas = max(1, (totaal + PER_PAGINA - 1) // PER_PAGINA)
    pagina = max(1, min(pagina, totaal_paginas))
    leden = (
        base_q
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
    club = get_admin_club(current_user, db, request)
    form = await request.form()
    voornaam = form.get("voornaam", "").strip()
    achternaam = form.get("achternaam", "").strip()
    nbb_nummer = form.get("nbb_nummer", "").strip() or None

    if voornaam and achternaam:
        db.add(Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb_nummer,
                   club_id=club.id if club else None))
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

    club = get_admin_club(current_user, db, request)
    club_id = club.id if club else None
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
    return RedirectResponse(url=f"/beheer/leden?import_ok={toegevoegd}&overgeslagen={overgeslagen}", status_code=302)


