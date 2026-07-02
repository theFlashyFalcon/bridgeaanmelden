from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.csrf import csrf_input, get_csrf_token
from app.config import ANDERE_CLUBS, CLUB_NAAM, CLUB_STAD

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["csrf_token"] = get_csrf_token
templates.env.globals["csrf_input"] = csrf_input
templates.env.globals["club_naam"] = CLUB_NAAM
templates.env.globals["club_stad"] = CLUB_STAD
templates.env.globals["andere_clubs"] = ANDERE_CLUBS


def _get_beheer_clubs(request):
    """
    Clubs die de ingelogde gebruiker kan beheren.
    Admins zien alle clubs; wedstrijdleiders zien alleen de clubs waarvoor ze WL-rol hebben.
    Alleen getoond wanneer er meer dan één club is (voor de club-switcher in de nav).
    """
    try:
        from app.database import SessionLocal
        from app.models import Club, Member, MemberClub, MemberRole
        user_id = request.session.get("user_id")
        if not user_id:
            return []
        db = SessionLocal()
        try:
            member = db.query(Member).filter(Member.id == user_id).first()
            if not member:
                return []
            if member.role == MemberRole.admin.value:
                return db.query(Club).order_by(Club.naam).all()
            mc_rows = db.query(MemberClub).filter(
                MemberClub.member_id == member.id,
                MemberClub.role.in_([MemberRole.admin.value, MemberRole.wedstrijdleider.value]),
            ).all()
            if not mc_rows:
                return []
            club_ids = [mc.club_id for mc in mc_rows]
            return db.query(Club).filter(Club.id.in_(club_ids)).order_by(Club.naam).all()
        finally:
            db.close()
    except Exception:
        return []


templates.env.globals["get_beheer_clubs"] = _get_beheer_clubs
