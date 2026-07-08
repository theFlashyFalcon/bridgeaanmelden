import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from app.auth import SECRET_KEY  # noqa: E402 — must be after load_dotenv
from app.csrf import require_csrf  # noqa: E402
from app.routes import admin, auth, berichten, clubs, evenings, gdpr, members, registrations, rankings, uitslagen  # noqa: E402
from app.startup import run_startup_tasks  # noqa: E402
from app.templates_env import templates as _templates  # noqa: E402

_https_only = os.getenv("HTTPS_ONLY", "false").lower() == "true"


def _get_user_for_request(request: Request):
    try:
        from app.database import SessionLocal
        from app.models import Member
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        db = SessionLocal()
        try:
            return db.query(Member).filter(Member.id == user_id).first()
        finally:
            db.close()
    except Exception:
        return None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Schema-sync, seeds en opschoning draaien bij het starten van de server,
    # niet bij import — zie app/startup.py.
    run_startup_tasks()
    yield


app = FastAPI(
    title="Bridge Club Aanmeldingsapp",
    docs_url=None,
    redoc_url=None,
    dependencies=[Depends(require_csrf)],
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="strict",
    https_only=_https_only,
    max_age=7 * 24 * 3600,
)


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=302)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    current_user = _get_user_for_request(request)
    return _templates.TemplateResponse(
        request, "errors/403.html",
        {"current_user": current_user, "welkom": False},
        status_code=403,
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    current_user = _get_user_for_request(request)
    return _templates.TemplateResponse(
        request, "errors/404.html",
        {"current_user": current_user, "welkom": False},
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    import traceback
    logger.error("500 op %s:\n%s", request.url.path, traceback.format_exc())
    return _templates.TemplateResponse(
        request, "errors/500.html",
        {"current_user": _get_user_for_request(request), "welkom": False},
        status_code=500,
    )


class LogExceptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception:
            import traceback
            logger.error("Onverwerkte fout op %s:\n%s", request.url.path, traceback.format_exc())
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    # 'unsafe-inline' is nodig: de templates gebruiken inline <script> en style-attributen.
    # Google Fonts wordt geladen vanuit base.html.
    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", self._CSP)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if _https_only:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(LogExceptionsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(clubs.router)
app.include_router(evenings.router)
app.include_router(registrations.router)
app.include_router(members.router)
app.include_router(admin.router)
app.include_router(berichten.router)
app.include_router(rankings.router)
app.include_router(uitslagen.router)
app.include_router(gdpr.router)
