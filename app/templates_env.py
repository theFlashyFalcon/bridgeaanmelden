from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.csrf import csrf_input, get_csrf_token

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["csrf_token"] = get_csrf_token
templates.env.globals["csrf_input"] = csrf_input
