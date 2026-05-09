from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Bericht, Member, MemberRole

router = APIRouter(prefix="/berichten")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    return user


def _get_conversations(db: Session, user_id: int):
    """Haal alle root-berichten op waarbij de gebruiker betrokken is (geen nieuws)."""
    direct = (
        db.query(Bericht)
        .filter(
            Bericht.parent_id == None,  # noqa: E711
            Bericht.is_nieuws == False,  # noqa: E712
            or_(Bericht.afzender_id == user_id, Bericht.ontvanger_id == user_id),
        )
        .all()
    )
    direct_ids = {b.id for b in direct}

    reply_parent_ids = (
        db.query(Bericht.parent_id)
        .filter(
            Bericht.parent_id != None,  # noqa: E711
            or_(Bericht.afzender_id == user_id, Bericht.ontvanger_id == user_id),
        )
        .all()
    )
    extra_ids = {row[0] for row in reply_parent_ids} - direct_ids
    indirect = (
        db.query(Bericht).filter(Bericht.id.in_(extra_ids)).all() if extra_ids else []
    )

    root_messages = direct + indirect
    if not root_messages:
        return []

    # Bug 8 fix: load all replies in one query instead of one query per conversation
    all_root_ids = [r.id for r in root_messages]
    all_replies = (
        db.query(Bericht)
        .filter(Bericht.parent_id.in_(all_root_ids))
        .order_by(Bericht.aangemaakt_op)
        .all()
    )
    replies_by_parent: dict = {}
    for reply in all_replies:
        replies_by_parent.setdefault(reply.parent_id, []).append(reply)

    result = []
    for root in root_messages:
        replies = replies_by_parent.get(root.id, [])
        all_in_thread = [root] + replies
        latest = max(b.aangemaakt_op for b in all_in_thread)
        unread = sum(
            1 for b in all_in_thread
            if not b.gelezen and b.ontvanger_id == user_id
        )
        result.append({
            "root": root,
            "replies": replies,
            "latest": latest,
            "unread": unread,
            "count": len(replies),
        })

    result.sort(key=lambda x: x["latest"], reverse=True)
    return result


def _get_nieuws(db: Session, limit: int = 30):
    """Haal de meest recente nieuwsberichten op."""
    return (
        db.query(Bericht)
        .filter(Bericht.is_nieuws == True)  # noqa: E712
        .order_by(Bericht.aangemaakt_op.desc())
        .limit(limit)
        .all()
    )


# ── Ongelezen telling (voor badge in nav) — vóór /{bericht_id} ───────────────

@router.get("/telling")
async def berichten_telling(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"ongelezen": 0})
    count = (
        db.query(Bericht)
        .filter(Bericht.ontvanger_id == current_user.id, Bericht.gelezen == False)  # noqa: E712
        .count()
    )
    return JSONResponse({"ongelezen": count})


# ── Inbox ─────────────────────────────────────────────────────────────────────

@router.get("")
async def berichten_inbox(request: Request, db: Session = Depends(get_db)):
    current_user = _require_login(request, db)
    conversations = _get_conversations(db, current_user.id)
    nieuws_berichten = _get_nieuws(db)
    members = (
        db.query(Member)
        .filter(Member.verwijderd_op == None, Member.id != current_user.id)  # noqa: E711
        .order_by(Member.voornaam, Member.achternaam)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "berichten.html",
        {
            "current_user": current_user,
            "conversations": conversations,
            "nieuws_berichten": nieuws_berichten,
            "members": members,
            "welkom": False,
        },
    )


# ── Nieuw bericht versturen — vóór /{bericht_id} ─────────────────────────────

@router.post("/verstuur")
async def bericht_verstuur(request: Request, db: Session = Depends(get_db)):
    current_user = _require_login(request, db)
    form = await request.form()
    ontvanger_id_raw  = form.get("ontvanger_id", "").strip()
    ontvanger_vnaam   = form.get("ontvanger_voornaam", "").strip()
    ontvanger_anaam   = form.get("ontvanger_achternaam", "").strip()
    is_nieuws         = form.get("is_nieuws", "") == "1"
    onderwerp         = form.get("onderwerp", "").strip() or None
    tekst             = form.get("tekst", "").strip()
    terug             = form.get("terug", "").strip()
    if terug and not terug.startswith("/beheer/af-aanmeldingen/"):
        terug = ""

    def _redirect_fout(code: str) -> RedirectResponse:
        base = terug if terug else "/berichten"
        return RedirectResponse(url=f"{base}?fout={code}", status_code=302)

    # ── Nieuwsbericht (admin / wedstrijdleider) ───────────────────────────
    if is_nieuws:
        if current_user.role not in (MemberRole.admin, MemberRole.wedstrijdleider):
            raise HTTPException(status_code=403)
        if not onderwerp:
            return _redirect_fout("leeg")
        db.add(Bericht(
            afzender_id=current_user.id,
            ontvanger_id=None,
            onderwerp=onderwerp,
            tekst=tekst,
            is_nieuws=True,
        ))
        db.commit()
        return RedirectResponse(url=terug or "/berichten", status_code=302)

    # ── Persoonlijk bericht via ontvanger_id (losloper-modal) ─────────────
    if ontvanger_id_raw:
        try:
            ontvanger_id = int(ontvanger_id_raw)
        except ValueError:
            return _redirect_fout("ontvanger")
        if ontvanger_id == current_user.id:  # Bug 5 fix: no self-messaging
            return _redirect_fout("ontvanger")
        if not tekst:  # Bug 4 fix: require non-empty message body
            return _redirect_fout("leeg")
        ontvanger = db.query(Member).filter(Member.id == ontvanger_id).first()
        if not ontvanger:
            return _redirect_fout("ontvanger")
        bericht = Bericht(
            afzender_id=current_user.id,
            ontvanger_id=ontvanger_id,
            onderwerp=onderwerp,
            tekst=tekst,
        )
        db.add(bericht)
        db.commit()
        db.refresh(bericht)
        if terug:
            return RedirectResponse(url=f"{terug}?bericht_verstuurd=1", status_code=302)
        return RedirectResponse(url=f"/berichten/{bericht.id}", status_code=302)

    # ── Persoonlijk bericht via naam-zoekopdracht ─────────────────────────
    if not onderwerp:
        return _redirect_fout("leeg")
    if not ontvanger_vnaam or not ontvanger_anaam:
        return _redirect_fout("ontvanger")

    ontvanger = (
        db.query(Member)
        .filter(
            func.lower(Member.voornaam) == ontvanger_vnaam.lower(),
            func.lower(Member.achternaam) == ontvanger_anaam.lower(),
            Member.verwijderd_op == None,  # noqa: E711
        )
        .first()
    )
    if not ontvanger:
        return _redirect_fout("ontvanger")

    bericht = Bericht(
        afzender_id=current_user.id,
        ontvanger_id=ontvanger.id,
        onderwerp=onderwerp,
        tekst=tekst,
    )
    db.add(bericht)
    db.commit()
    db.refresh(bericht)
    if terug:
        return RedirectResponse(url=f"{terug}?bericht_verstuurd=1", status_code=302)
    return RedirectResponse(url=f"/berichten/{bericht.id}", status_code=302)


# ── Gespreksdetail ────────────────────────────────────────────────────────────

@router.get("/{bericht_id}")
async def bericht_detail(
    bericht_id: int, request: Request, db: Session = Depends(get_db)
):
    current_user = _require_login(request, db)
    root = (
        db.query(Bericht)
        .filter(Bericht.id == bericht_id, Bericht.parent_id == None)  # noqa: E711
        .first()
    )
    if not root:
        raise HTTPException(status_code=404, detail="Bericht niet gevonden")

    involved = (
        root.afzender_id == current_user.id or root.ontvanger_id == current_user.id
    )
    if not involved:
        reply_check = (
            db.query(Bericht)
            .filter(
                Bericht.parent_id == bericht_id,
                or_(
                    Bericht.afzender_id == current_user.id,
                    Bericht.ontvanger_id == current_user.id,
                ),
            )
            .first()
        )
        if not reply_check:
            raise HTTPException(status_code=403)

    replies = (
        db.query(Bericht)
        .filter(Bericht.parent_id == bericht_id)
        .order_by(Bericht.aangemaakt_op)
        .all()
    )

    for b in [root] + replies:
        if not b.gelezen and b.ontvanger_id == current_user.id:
            b.gelezen = True
    db.commit()

    members = (
        db.query(Member)
        .filter(Member.verwijderd_op == None, Member.id != current_user.id)  # noqa: E711
        .order_by(Member.voornaam, Member.achternaam)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "berichten_detail.html",
        {
            "current_user": current_user,
            "root": root,
            "replies": replies,
            "members": members,
            "welkom": False,
        },
    )


# ── Antwoord sturen ───────────────────────────────────────────────────────────

@router.post("/{bericht_id}/antwoord")
async def bericht_antwoord(
    bericht_id: int, request: Request, db: Session = Depends(get_db)
):
    current_user = _require_login(request, db)
    # Bug 2 fix: only allow replying to root messages, not to replies themselves
    root = (
        db.query(Bericht)
        .filter(Bericht.id == bericht_id, Bericht.parent_id == None)  # noqa: E711
        .first()
    )
    if not root:
        raise HTTPException(status_code=404, detail="Bericht niet gevonden")

    # Bug 3 fix: news items have no addressed recipient, so replies are not possible
    if root.is_nieuws:
        raise HTTPException(status_code=403, detail="Nieuwsberichten kunnen niet beantwoord worden")

    # Bug 1 fix: check that the current user is a participant in this conversation
    involved = (
        root.afzender_id == current_user.id or root.ontvanger_id == current_user.id
    )
    if not involved:
        reply_check = (
            db.query(Bericht)
            .filter(
                Bericht.parent_id == bericht_id,
                or_(
                    Bericht.afzender_id == current_user.id,
                    Bericht.ontvanger_id == current_user.id,
                ),
            )
            .first()
        )
        if not reply_check:
            raise HTTPException(status_code=403)

    form = await request.form()
    tekst = form.get("tekst", "").strip()
    if not tekst:
        return RedirectResponse(url=f"/berichten/{bericht_id}?fout=leeg", status_code=302)

    ontvanger_id = root.ontvanger_id if root.afzender_id == current_user.id else root.afzender_id

    antwoord = Bericht(
        afzender_id=current_user.id,
        ontvanger_id=ontvanger_id,
        tekst=tekst,
        parent_id=bericht_id,
    )
    db.add(antwoord)
    db.commit()
    return RedirectResponse(url=f"/berichten/{bericht_id}", status_code=302)
