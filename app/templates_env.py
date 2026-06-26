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
