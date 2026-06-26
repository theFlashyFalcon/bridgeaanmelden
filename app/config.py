import os

CLUB_NAAM: str = os.getenv("CLUB_NAAM", "Crash")
CLUB_STAD: str = os.getenv("CLUB_STAD", "")
CLUB_LEDENLIJST_CSV: str = os.getenv("CLUB_LEDENLIJST_CSV", "data/ledenlijst_nbbr_9040.csv")

INTER_CLUB_SECRET: str = os.getenv("INTER_CLUB_SECRET", "")


def _parse_andere_clubs() -> list[dict]:
    """Parseer ANDERE_CLUBS env var: 'Naam Club|https://url.nl;Naam Club 2|https://url2.nl'"""
    raw = os.getenv("ANDERE_CLUBS", "").strip()
    if not raw:
        return []
    clubs = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if "|" not in entry:
            continue
        naam, url = entry.split("|", 1)
        naam, url = naam.strip(), url.strip().rstrip("/")
        if naam and url:
            clubs.append({"naam": naam, "url": url})
    return clubs


ANDERE_CLUBS: list[dict] = _parse_andere_clubs()
