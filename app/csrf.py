import secrets

from fastapi import HTTPException, Request
from markupsafe import Markup


def get_csrf_token(request: Request) -> str:
    """Geeft het sessie-CSRF-token terug; maakt er een aan als het nog niet bestaat."""
    if "_csrf" not in request.session:
        request.session["_csrf"] = secrets.token_hex(32)
    return request.session["_csrf"]


def csrf_input(request: Request) -> Markup:
    """Geeft een verborgen HTML-input terug met het CSRF-token."""
    token = get_csrf_token(request)
    return Markup(f'<input type="hidden" name="_csrf_token" value="{token}">')


async def require_csrf(request: Request) -> None:
    """FastAPI-dependency: valideert CSRF-token voor POST/PUT/DELETE-formulierverzoeken."""
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return
    content_type = request.headers.get("content-type", "")
    if (
        "application/x-www-form-urlencoded" not in content_type
        and "multipart/form-data" not in content_type
    ):
        return
    form = await request.form()
    submitted = form.get("_csrf_token", "")
    expected = request.session.get("_csrf", "")
    if not expected or not submitted or not secrets.compare_digest(submitted, expected):
        raise HTTPException(
            status_code=403,
            detail="Ongeldige aanvraag. Ververs de pagina en probeer opnieuw.",
        )
