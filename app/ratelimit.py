import os
import time
from collections import defaultdict

_failed: dict = defaultdict(list)
_WINDOW = 300   # seconden (5 minuten)
_MAX = 5        # maximaal aantal mislukte pogingen per venster

# X-Forwarded-For is door de client zelf te zetten en dus alleen betrouwbaar
# achter een proxy die hem overschrijft (Render, Heroku, nginx). Zet
# TRUST_PROXY=true bij zulke deployments; anders geldt het verbindings-IP.
_TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"


def client_key(request) -> str:
    """Client-IP voor rate limiting; achter een vertrouwde proxy telt X-Forwarded-For."""
    if _TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "onbekend"


def is_limited(key: str, max_attempts: int = _MAX) -> bool:
    """Geeft True als het maximale aantal pogingen voor de sleutel is bereikt."""
    now = time.monotonic()
    recent = [t for t in _failed[key] if now - t < _WINDOW]
    if recent:
        _failed[key] = recent
    else:
        # Lege sleutels opruimen zodat het geheugen niet onbegrensd groeit
        _failed.pop(key, None)
    return len(recent) >= max_attempts


def record_failure(key: str) -> None:
    """Registreer een mislukte poging voor de gegeven sleutel."""
    _failed[key].append(time.monotonic())


def reset(key: str) -> None:
    """Verwijder alle pogingen (bijv. na succesvolle inlog)."""
    _failed.pop(key, None)
