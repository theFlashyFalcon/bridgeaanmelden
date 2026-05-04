from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Bericht, Member

router = APIRouter(prefix="/berichten")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    return user


def _get_conversations(db: Session, user_id: int):
    """Haal alle root-berichten op waarbij de gebruiker betrokken is."""
    direct = (
        db.query(Bericht)
        .filter(
            Bericht.parent_id == None,  # noqa: E711
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

    result = []
    for root in direct + indirect:
        replies = (
            db.query(Bericht)
            .filter(Bericht.parent_id == root.id)
            .order_by(Bericht.aangemaakt_op)
            .all()
        )
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
    members = (
        db.query(Member)
        .filter(Member.verwijderd_op == None, Member.id != current_user.id)  # noqa: E711
        .order_by(Member.voornaam)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "berichten.html",
        {
            "current_user": current_user,
            "conversations": conversations,
            "members": members,
            "welkom": False,
        },
    )


# ── Nieuw bericht versturen — vóór /{bericht_id} ─────────────────────────────

@router.post("/verstuur")
async def bericht_verstuur(request: Request, db: Session = Depends(get_db)):
    current_user = _require_login(request, db)
    form = await request.form()
    ontvanger_id = int(form.get("ontvanger_id", 0))
    onderwerp = form.get("onderwerp", "").strip() or None
    tekst = form.get("tekst", "").strip()

    if not tekst or not ontvanger_id:
        return RedirectResponse(url="/berichten?fout=leeg", status_code=302)

    ontvanger = db.query(Member).filter(Member.id == ontvanger_id).first()
    if not ontvanger:
        return RedirectResponse(url="/berichten?fout=ontvanger", status_code=302)

    bericht = Bericht(
        afzender_id=current_user.id,
        ontvanger_id=ontvanger_id,
        onderwerp=onderwerp,
        tekst=tekst,
    )
    db.add(bericht)
    db.commit()
    db.refresh(bericht)
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
        raise HTTPException(status_code=404)

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
        .order_by(Member.voornaam)
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
    root = db.query(Bericht).filter(Bericht.id == bericht_id).first()
    if not root:
        raise HTTPException(status_code=404)

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
