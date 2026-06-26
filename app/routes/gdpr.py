import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.models import (
    Bericht,
    Member,
    PartnerRequest,
    RecurringRegistration,
    Registration,
)

router = APIRouter(prefix="/gdpr")
logger = logging.getLogger(__name__)

from app.templates_env import templates


@router.get("/download")
async def download_mijn_gegevens(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    registrations = (
        db.query(Registration)
        .filter(Registration.person1_id == current_user.id)
        .all()
    )
    berichten_verzonden = (
        db.query(Bericht)
        .filter(Bericht.afzender_id == current_user.id)
        .all()
    )
    berichten_ontvangen = (
        db.query(Bericht)
        .filter(Bericht.ontvanger_id == current_user.id)
        .all()
    )

    data = {
        "export_datum": datetime.now(timezone.utc).isoformat(),
        "account": {
            "voornaam": current_user.voornaam,
            "achternaam": current_user.achternaam,
            "lidnummer": current_user.lidnummer,
            "email": current_user.email,
            "rol": current_user.role,
            "training_eligible": current_user.training_eligible,
            "toestemming_op": current_user.toestemming_op.isoformat() if current_user.toestemming_op else None,
        },
        "aanmeldingen": [
            {
                "avond_datum": str(r.evening.datum) if r.evening else None,
                "avond_naam": r.evening.naam if r.evening else None,
                "type": r.type,
                "status": r.status,
                "partner_naam": r.partner_naam,
                "aangemeld_op": r.aangemeld_op.isoformat() if r.aangemeld_op else None,
            }
            for r in registrations
        ],
        "berichten_verzonden": [
            {
                "onderwerp": b.onderwerp,
                "tekst": b.tekst,
                "aangemaakt_op": b.aangemaakt_op.isoformat() if b.aangemaakt_op else None,
            }
            for b in berichten_verzonden
        ],
        "berichten_ontvangen": [
            {
                "onderwerp": b.onderwerp,
                "tekst": b.tekst,
                "aangemaakt_op": b.aangemaakt_op.isoformat() if b.aangemaakt_op else None,
            }
            for b in berichten_ontvangen
        ],
    }

    logger.info("GDPR data-export uitgevoerd voor member-id %d", current_user.id)

    content = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="mijn-gegevens-{current_user.lidnummer}.json"'
        },
    )


@router.post("/verwijder-account")
async def verwijder_eigen_account(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    member_id = current_user.id

    # Verwijder berichten
    db.query(Bericht).filter(
        (Bericht.afzender_id == member_id) | (Bericht.ontvanger_id == member_id)
    ).delete(synchronize_session=False)

    # Verwijder partnerverzoeken
    db.query(PartnerRequest).filter(
        PartnerRequest.requester_id == member_id
    ).delete(synchronize_session=False)

    # Verwijder herhalende aanmeldingen
    db.query(RecurringRegistration).filter(
        RecurringRegistration.member_id == member_id
    ).delete(synchronize_session=False)

    # Verwijder aanmeldingen waarbij dit lid hoofdpersoon is
    db.query(Registration).filter(
        Registration.person1_id == member_id
    ).delete(synchronize_session=False)

    # Ontkoppel aanmeldingen waarbij dit lid partner was
    db.query(Registration).filter(
        Registration.person2_id == member_id
    ).update(
        {Registration.person2_id: None},
        synchronize_session=False,
    )

    # Verwijder het account zelf (hard delete)
    db.delete(current_user)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Fout bij verwijderen account member-id %d", member_id)
        return templates.TemplateResponse(
            request,
            "profiel.html",
            {"current_user": current_user, "fout_verwijdering": True},
            status_code=500,
        )

    logger.info("Account member-id %d zelf verwijderd (GDPR art. 17)", member_id)

    request.session.clear()
    return RedirectResponse(url="/?account_verwijderd=1", status_code=302)
