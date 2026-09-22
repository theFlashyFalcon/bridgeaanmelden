"""Weergave van opgeslagen tijdstippen in Nederlandse (lokale) tijd.

Tijdstippen die met server_default=func.now() zijn opgeslagen (bv.
Registration.aangemeld_op) komen op de productiedatabase (Postgres) als UTC
binnen, zonder tijdzone-info. Rechtstreeks tonen met strftime() geeft dan een
tijd die in de zomer (CEST, UTC+2) 2 uur achterloopt op de werkelijke lokale
tijd. Deze helper zet zo'n naive UTC-datetime om naar Europe/Amsterdam vóór
het formatteren.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def naar_lokale_tijd(dt: datetime | None) -> datetime | None:
    """Interpreteert een naive datetime als UTC en zet hem om naar Europe/Amsterdam."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(AMSTERDAM)
