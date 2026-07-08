# Bridge Club Aanmeldingsapp

Webapp waarmee leden van een bridgeclub zich aan- en afmelden voor clubavonden,
trainingen en speciale evenementen. Wedstrijdleiders beheren avonden, seizoenen,
paren en uitslagen; beheerders beheren accounts, rollen en clubs.

Gebouwd met FastAPI, SQLAlchemy en Jinja2-templates. Standaard draait de app op
een lokaal SQLite-bestand; voor productie wordt PostgreSQL aangeraden.

## Lokaal draaien

Vereist Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env          # en vul minimaal SECRET_KEY en ADMIN_EMAIL in

uvicorn app.main:app --reload
```

De app draait dan op http://127.0.0.1:8000. Bij de eerste start worden de
databasetabellen aangemaakt, de eerste club aangemaakt en (als `ADMIN_EMAIL` en
`ADMIN_PASSWORD` gezet zijn) een admin-account aangemaakt.

## Configuratie

Alle instellingen gaan via omgevingsvariabelen of `.env` — zie
[.env.example](.env.example) voor de volledige lijst met uitleg. De
belangrijkste:

| Variabele | Betekenis |
|---|---|
| `SECRET_KEY` | Sleutel voor sessie-ondertekening. **Verplicht in productie.** |
| `DATABASE_URL` | Database-URL. Standaard `sqlite:///./bridgeclub.db`; gebruik `postgresql://...` in productie. |
| `HTTPS_ONLY` | Zet op `true` in productie: Secure-cookies + HSTS, en de app weigert te starten zonder echte `SECRET_KEY`. |
| `TRUST_PROXY` | Zet op `true` achter een proxy (Render, Heroku, nginx) zodat rate limiting het echte client-IP gebruikt. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Eerste beheerdersaccount, aangemaakt bij het opstarten. |
| `SMTP_*` | Mailinstellingen voor uitnodigingen en notificaties. |

## Tests

```bash
python -m pytest
```

## Productie / hosting

Werkt op platforms als Render of Heroku:

- Stel `DATABASE_URL` in naar een PostgreSQL-database. **Gebruik geen SQLite op
  Render**: het bestandssysteem is daar niet persistent, dus de database gaat
  verloren bij elke deploy.
- Zet `HTTPS_ONLY=true`, `TRUST_PROXY=true`, een unieke `SECRET_KEY` en `BASE_URL`.
- Startcommando: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Draai bij voorkeur met één worker: de schema-sync en seeds draaien bij het
  opstarten van elke worker, en de login-rate-limiter is per proces.

## Architectuur in het kort

- `app/main.py` — FastAPI-app, middleware (sessies, CSRF, security headers) en
  foutafhandeling. Opstarttaken draaien in de lifespan-handler.
- `app/startup.py` — opstarttaken: schema-sync, seeds (admin, club, leden) en
  opschoning van verlopen data.
- `app/schema_sync.py` — vult ontbrekende tabellen/kolommen aan op basis van de
  modellen in `app/models.py` (de bron van waarheid voor het schema).
- `app/routes/` — routes per domein; beheer-routes staan in `app/routes/admin/`
  (avonden, aanmeldingen, accounts, clubs).
- `app/templates/` — Jinja2-templates (Nederlandstalige UI).
- `alembic/` — handmatige (data)migraties; het reguliere schema wordt door de
  schema-sync bijgehouden.
