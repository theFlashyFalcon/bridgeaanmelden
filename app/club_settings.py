"""
Clubinstellingen: welke evenementtypes een club gebruikt en welke
rankingweergaves beschikbaar zijn. Opgeslagen als komma-gescheiden
strings op Club.evenement_types en Club.ranking_weergaves;
NULL/leeg betekent: alles beschikbaar (standaard).
"""
from app.models import Club

# Canonieke filtersleutels zoals gebruikt in het hoofdscherm (index.html)
EVENT_TYPE_KEUZES: list[tuple[str, str]] = [
    ("clubavond", "Clubavonden"),
    ("avondeten", "Avondeten"),
    ("training", "Trainingen"),
    ("speciaal", "Speciale evenementen"),
]
EVENT_TYPE_KEYS = [k for k, _ in EVENT_TYPE_KEUZES]

# Weergave-sleutels zoals gebruikt op de rankingpagina (routes/rankings.py)
RANKING_KEUZES: list[tuple[str, str]] = [
    ("spanning", "Algemene ranking"),
    ("lijn_a", "Lijn A"),
    ("lijn_b", "Lijn B"),
    ("iedereen", "Iedereen"),
    ("imp_totaal", "IMP totaal"),
    ("consistentie", "Consistentie"),
    ("vaste_partners", "Vaste partners"),
    ("vorm", "Vorm"),
]
RANKING_KEYS = [k for k, _ in RANKING_KEUZES]

# Labels op evenementkaarten. De sleutel wordt afgeleid uit het evenement:
# Training/Avondeten uit het type, de rest uit de deelnemersvorm.
LABEL_KEUZES: list[tuple[str, str]] = [
    ("training", "Training"),
    ("avondeten", "Avondeten"),
    ("viertallen", "Viertallen"),
    ("paren", "Paren"),
    ("individuele_drive", "Individuele drive"),
]
LABEL_KEYS = [k for k, _ in LABEL_KEUZES]
LABEL_NAMEN = dict(LABEL_KEUZES)


def _parse(raw: str | None, geldige_keys: list[str]) -> list[str]:
    if not raw:
        return list(geldige_keys)
    gekozen = [t.strip() for t in raw.split(",") if t.strip()]
    resultaat = [k for k in geldige_keys if k in gekozen]
    return resultaat or list(geldige_keys)


def enabled_event_types(club: Club | None) -> list[str]:
    """Ingestelde evenementtypes van een club (volgorde van EVENT_TYPE_KEYS)."""
    return _parse(club.evenement_types if club else None, EVENT_TYPE_KEYS)


def enabled_rankings(club: Club | None) -> list[str]:
    """Ingestelde rankingweergaves van een club (volgorde van RANKING_KEYS)."""
    return _parse(club.ranking_weergaves if club else None, RANKING_KEYS)


def enabled_labels(club: Club | None) -> list[str]:
    """Ingestelde labels van een club (volgorde van LABEL_KEYS)."""
    return _parse(club.labels if club else None, LABEL_KEYS)


def evening_label_key(type_: str, deelnemers_type: str | None) -> str:
    """Leid de labelsleutel van een evenement af uit type + deelnemersvorm."""
    if type_ in ("jeugdtraining", "training"):
        return "training"
    if type_ == "eten voor jeugdtraining":
        return "avondeten"
    dt = deelnemers_type or "paren"
    if dt == "viertallen":
        return "viertallen"
    if dt == "individueel":
        return "individuele_drive"
    return "paren"


def evening_label(evening) -> dict | None:
    """
    Label voor een evenementkaart: {key, naam, css}, of None wanneer de club
    dit label niet gebruikt (zie /beheer/instellingen). Gebruikt als Jinja-global.
    """
    key = evening_label_key(evening.type, evening.deelnemers_type)
    if key not in enabled_labels(evening.club):
        return None
    return {"key": key, "naam": LABEL_NAMEN[key], "css": key.replace("_", "-")}


def merged_event_types(clubs: list[Club]) -> list[str]:
    """Vereniging van de evenementtypes van meerdere clubs (voor leden van meerdere clubs)."""
    if not clubs:
        return list(EVENT_TYPE_KEYS)
    samen: set[str] = set()
    for club in clubs:
        samen.update(enabled_event_types(club))
    return [k for k in EVENT_TYPE_KEYS if k in samen]


def merged_rankings(clubs: list[Club]) -> list[str]:
    """Vereniging van de rankingweergaves van meerdere clubs."""
    if not clubs:
        return list(RANKING_KEYS)
    samen: set[str] = set()
    for club in clubs:
        samen.update(enabled_rankings(club))
    return [k for k in RANKING_KEYS if k in samen]
