import time
from collections import defaultdict

_failed: dict = defaultdict(list)
_WINDOW = 300   # seconden (5 minuten)
_MAX = 5        # maximaal aantal mislukte pogingen per venster


def is_limited(key: str) -> bool:
    """Geeft True als het maximale aantal pogingen voor de sleutel is bereikt."""
    now = time.monotonic()
    recent = [t for t in _failed[key] if now - t < _WINDOW]
    _failed[key] = recent
    return len(recent) >= _MAX


def record_failure(key: str) -> None:
    """Registreer een mislukte poging voor de gegeven sleutel."""
    _failed[key].append(time.monotonic())


def reset(key: str) -> None:
    """Verwijder alle pogingen (bijv. na succesvolle inlog)."""
    _failed.pop(key, None)
