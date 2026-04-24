# Implementatieplan — Bridge Club Aanmeldingsapp (PWA)

**Versie:** 1.0  
**Datum:** 22 april 2026  
**Status:** Concept

---

## Inhoudsopgave

1. [Samenvatting](#samenvatting)
2. [Werkwijze & Voorwaarden](#werkwijze--voorwaarden)
3. [Vereisten](#vereisten)
4. [Tech Stack](#tech-stack)
5. [Datamodel](#datamodel)
6. [Work Breakdown & Schattingen](#work-breakdown--schattingen)
7. [Openstaande vragen](#openstaande-vragen)

---

## Samenvatting

Een Progressive Web App (PWA) waarmee leden van de bridgeclub zich kunnen aanmelden voor clubavonden en trainingsavonden. De app is te installeren op Android en iPhone en werkt ook via de browser. Er is een publieke weergave van aanmeldingen en een beveiligde beheerdersrol voor de wedstrijdleider.

**Totaalschatting: 126 uur**

---

## Werkwijze & Voorwaarden

Dit project wordt uitgevoerd volgens een **Agile werkwijze** met de volgende afspraken:

### Iteraties & Demonstraties
- Het werk is opgedeeld in iteraties van **twee weken**.
- Aan het einde van elke iteratie vindt een **demonstratie** plaats van de opgeleverde functionaliteit.
- Yordi (opdrachtgever) beoordeelt de demo en geeft feedback voor de volgende iteratie.

### Koerscorrecties
- Na elke demonstratie is het mogelijk om **prioriteiten bij te stellen**, onderdelen toe te voegen, te wijzigen of te schrappen.
- Wijzigingen in de scope worden verwerkt in de planning van de volgende iteratie — er wordt geen werk weggegooid zonder overleg.
- Grote scopewijzigingen kunnen invloed hebben op de totale doorlooptijd; dit wordt tijdig gecommuniceerd.

### Schattingen
- Alle uurschattingen in dit document zijn **indicatief** en naar beste inzicht opgesteld.
- Schattingen zijn **niet-bindend**: de werkelijke bestede tijd kan afwijken door onvoorziene technische complexiteit of gewijzigde inzichten.
- Schattingen worden na elke iteratie herzien op basis van opgedane ervaring.

---

## Vereisten

### Functioneel

#### Publieke deelnemersweergave
- Lijst van aangemelde paren voor de eerstvolgende clubavond
- Gesorteerd: vaste paren alfabetisch (op voornaam van de eerste), dan losse paren alfabetisch
- Teller met aantal aangemelde paren
- Losse aanmeldingen (zonder partner) apart vermeld
- Loslopers **niet** publiek zichtbaar — alleen voor admins

#### Aanmelden
- Naam zoeken uit ledenlijst (of nieuwe naam + lidnummer toevoegen)
- Keuze: los aanmelden of partner selecteren (zelfde zoekmethode)
- Aanmeldingstype:
  - **Vast partnership** — aanmelden vanaf een bepaalde datum
  - **Alle trainingsavonden** — alleen voor trainingsgerechtigde leden
  - **Losse avonden** — meerdere datums selecteren
- Trainingsdatums alleen zichtbaar/selecteerbaar voor trainingsgerechtigde leden

#### Wijzigen
Stapsgewijs via datum → paar → type wijziging:
- Invaller opgeven
- Aanmelding annuleren
- Eén van de twee beschikbaar
- **Combipaar** opgeven:
  - Keuze uit alle vaste paren (ook al afgemeld) of aangemelde paren voor die datum
  - Beide partijen zien met wie ze spelen
  - Het andere paar wordt automatisch afgemeld
- Afmelden als vast partnership

#### Rollen & Rechten

| Functie | Lid | Wedstrijdleider | Admin |
|---|:---:|:---:|:---:|
| Eigen aanmeldingen beheren | ✓ | ✓ | ✓ |
| Publieke deelnemersweergave | ✓ | ✓ | ✓ |
| Loslopers inzien | | ✓ | ✓ |
| Aanmeldingen & afmeldingen inzien | | ✓ | ✓ |
| Clubavonden toevoegen / bewerken | | ✓ | ✓ |
| Seizoenen beheren | | | ✓ |
| Ledenlijst beheren & importeren | | | ✓ |
| Trainingsgerechtigde leden markeren | | | ✓ |
| Uitnodigingslinks genereren | | | ✓ |
| Rollen toewijzen | | | ✓ |

#### Beheerfuncties (Wedstrijdleider)
- Clubavonden toevoegen / bewerken / verwijderen (datum, type, seizoen)
- Alle aanmeldingen en afmeldingen per avond inzien incl. wijzigingshistorie
- Loslopers inzien

#### Beheerdersfuncties (Admin)
- Alles wat Wedstrijdleider kan
- Seizoenen beheren (aanmaken, actief zetten)
- Ledenlijst beheren (toevoegen, bewerken, verwijderen)
- Trainingsgerechtigde leden markeren
- Ledenlijst importeren via CSV/Excel
- Uitnodigingslinks genereren per potentieel lid (verstuurd per e-mail buiten de app)
- Rollen toewijzen aan leden (`Lid` → `Wedstrijdleider` → `Admin`)

### Niet-functioneel
- Installeerbaar als PWA op Android en iPhone
- GDPR-compliant
- Hosting via Firebase-gegenereerde URL (later eigen domein)
- Geen e-mailnotificaties vereist (buiten uitnodigingsmails en GDPR-melding)
- Toegang alleen via persoonlijke uitnodigingslink; accountaanmaak via sociale login (Google)
- Drie rollen: **Lid** (standaard na registratie), **Wedstrijdleider**, **Admin**

### Clubstructuur
- 1 clubavond per week
- 1 trainingsavond per 2 weken (vlak vóór de clubavond, beperkte toegang)
- Seizoen = academisch jaar

---

## Tech Stack

| Laag | Keuze | Toelichting |
|---|---|---|
| **Backend** | Python — FastAPI | Modern, snel, automatische API-documentatie |
| **Frontend** | HTML + CSS (Jinja2 templates) | Served vanuit FastAPI, geen JavaScript framework |
| **Database** | SQLite (later PostgreSQL) | Eenvoudig, geen aparte server, Python-native |
| **Auth** | Authlib + Google OAuth 2.0 | Sociale login via Google; sessie in server-side cookie |
| **PWA** | Service Worker (minimaal vanilla JS) | Vereist voor offline-cache en installeerbaar maken |
| **Hosting** | Render.com of Railway | Gratis tier, HTTPS inbegrepen, eenvoudige Python-deployment |

> **Noot over JavaScript:** Een PWA vereist technisch gezien een service worker in JavaScript. Dit is de enige JS in het project — alle overige logica zit in Python (backend) en HTML/CSS (frontend).

---

## Datamodel

### Tabel: `members`
| Kolom | Type | Omschrijving |
|---|---|---|
| id | INTEGER PK | |
| voornaam | TEXT | |
| achternaam | TEXT | |
| lidnummer | TEXT UNIQUE | |
| training_eligible | BOOLEAN | Mag trainingsdatums zien/selecteren |
| role | TEXT | `lid`, `wedstrijdleider`, `admin` |
| oauth_sub | TEXT UNIQUE | Unieke identifier van Google OAuth provider |

### Tabel: `invitations`
| Kolom | Type | Omschrijving |
|---|---|---|
| id | INTEGER PK | |
| token | TEXT UNIQUE | Unieke token in de uitnodigingslink |
| email | TEXT | E-mailadres van de uitgenodigde |
| aangemaakt_op | DATETIME | |
| gebruikt_op | DATETIME | Null = nog niet gebruikt |
| member_id | INTEGER FK | Null = account nog niet aangemaakt |

### Tabel: `seasons`
| Kolom | Type | Omschrijving |
|---|---|---|
| id | INTEGER PK | |
| naam | TEXT | Bijv. "2025–2026" |
| start_datum | DATE | |
| eind_datum | DATE | |
| actief | BOOLEAN | |

### Tabel: `club_evenings`
| Kolom | Type | Omschrijving |
|---|---|---|
| id | INTEGER PK | |
| datum | DATE | |
| type | TEXT | `regulier` of `training` |
| season_id | INTEGER FK | |

### Tabel: `fixed_partnerships`
| Kolom | Type | Omschrijving |
|---|---|---|
| id | INTEGER PK | |
| person1_id | INTEGER FK | |
| person2_id | INTEGER FK | |
| start_datum | DATE | |
| eind_datum | DATE | Null = nog actief |
| scope | TEXT | `all` of `training_only` |

### Tabel: `registrations`
| Kolom | Type | Omschrijving |
|---|---|---|
| id | INTEGER PK | |
| evening_id | INTEGER FK | |
| person1_id | INTEGER FK | |
| person2_id | INTEGER FK | Null = solo |
| type | TEXT | `vast`, `los`, `training` |
| status | TEXT | `aangemeld`, `afgemeld`, `beschikbaar_solo`, `invaller`, `combipaar` |
| substitute_name | TEXT | Naam invaller |
| available_person_id | INTEGER FK | Wie beschikbaar is bij 1-van-2 |
| combo_partner_reg_id | INTEGER FK | Koppeling naar het andere combipaar |
| aangemeld_op | DATETIME | |
| gewijzigd_op | DATETIME | |

---

## Work Breakdown & Schattingen

### 1. Project Setup & Architectuur — *8 uur*
- FastAPI-project opzetten met Jinja2 template-rendering
- SQLite database-configuratie met SQLAlchemy ORM
- PWA-configuratie: `manifest.json`, service worker, app-iconen
- Projectstructuur: routes, templates, static files, database migrations (Alembic)
- Deployment pipeline (Render.com / Railway)

### 2. Datamodel & Database — *8 uur*
- SQLAlchemy models voor alle tabellen
- Alembic migraties opzetten
- Seed-script voor testdata (seizoen, avonden, testleden)
- Database-helperlagen (CRUD-functies)

### 3. Authenticatie, Rollen & Uitnodigingssysteem — *16 uur*
- **Sociale login** via Google OAuth 2.0 (Authlib); koppeling `oauth_sub` → member record
- Sessie opslaan in server-side HTTP-cookie (veilig, HTTPS)
- **Uitnodigingsflow**:
  - Admin genereert een unieke, enkelvoudig-te-gebruiken uitnodigingslink per potentieel lid
  - Link wordt per e-mail verstuurd (buiten de app, door de admin)
  - Gebruiker klikt de link, logt in via Google, account wordt aangemaakt met rol `Lid`
  - Gebruikte en verlopen links worden gemarkeerd en niet hergebruikt
- **Rollenbeheer**:
  - Standaardrol bij accountaanmaak: `Lid`
  - Admin kan rol wijzigen naar `Wedstrijdleider` of `Admin`
- Routebewaking per rol: toegangscontrole op alle routes
- Trainingsavonden verbergen voor niet-trainingsgerechtigde leden

### 4. Publieke Deelnemersweergave — *10 uur*
- Overzichtspagina van de eerstvolgende clubavond
- Gesorteerde parenlijst (vaste paren → losse paren, alfabetisch op voornaam)
- Parenteller
- Losse soloaanmeldingen apart weergegeven
- Loslopers verborgen voor publiek, zichtbaar voor admins
- Combipaar-aanmeldingen weergeven als "A + B (combipaar)"
- Responsive layout voor mobiel (CSS grid/flexbox)

### 5. Aanmeldingsstroom — *16 uur*
Meerstappenformulier:
1. **Lidzoeken** — zoekbalk op voornaam/achternaam in ledenlijst
2. **Partnerselectie** — solo of partner zoeken (zelfde zoekmethode)
3. **Aanmeldingstype** — vast / alle trainingen / losse avonden (training alleen voor eligible leden)
4. **Datumselectie** — meervoudige keuze voor losse avonden; startdatum voor vast/training
- Validatie: paar al aangemeld? Datum in verleden? Niet training-eligible?
- Bevestigingsscherm na aanmelding

### 6. Wijzigingsstroom — *20 uur*
Meerstappenformulier:
1. **Datum selecteren** — dropdown van avonden waarvoor je aangemeld bent
2. **Paar selecteren** — gefilterd op jouw aanmeldingen voor die datum
3. **Wijzigingstype kiezen**:
   - Invaller: naam invaller invoeren
   - Annuleren: bevestiging tonen
   - Eén beschikbaar: welke persoon?
   - Combipaar: selectie uit vaste paren + aangemelde paren; automatisch afmelden ander paar; beide partijen zien nieuwe partner
   - Afmelden als vast partnership
- Alle wijzigingen opslaan met tijdstempel in `registrations`

### 7. Beheerfuncties — *16 uur*
- **Clubavonden**: overzicht, toevoegen, bewerken, verwijderen *(Wedstrijdleider + Admin)*
- **Seizoenen**: aanmaken, actief zetten *(Admin)*
- **Aanmeldingenoverzicht per avond**: alle paren, statussen, wijzigingshistorie *(Wedstrijdleider + Admin)*
- **Loslopers-dashboard**: overzicht van soloaanmeldingen *(Wedstrijdleider + Admin)*
- **Ledenbeheer**: toevoegen, bewerken, verwijderen, training_eligible instellen *(Admin)*
- **Rollenbeheer**: rol toewijzen per lid (Lid / Wedstrijdleider / Admin) *(Admin)*
- **Uitnodigingen**: overzicht van verstuurde links, status (gebruikt / verlopen / open) *(Admin)*
- Navigatiemenu gefilterd op rol (Lid ziet geen beheerfuncties)

### 8. Ledenimport (CSV / Excel) — *8 uur*
- Uploadscherm in beheerderspaneel
- Ondersteuning voor `.csv` en `.xlsx` (via `pandas` / `openpyxl`)
- Kolomkoppeling UI: wijs kolommen "Voornaam", "Achternaam", "Lidnummer" aan
- Preview van te importeren leden voor bevestiging
- Duplicaatdetectie op lidnummer (optie: overslaan of updaten)
- Importrapport (X nieuw, Y bijgewerkt, Z overgeslagen)

### 9. GDPR-compliance — *6 uur*
- Privacymelding bij eerste gebruik (toestemming opslaan in sessie/cookie)
- Privacybeleidspagina: welke data, doel, bewaartermijn, contactpersoon
- **Gegevensretentie**: admin kan seizoendata archiveren of verwijderen na X maanden
- **Recht op verwijdering**: admin kan lid verwijderen; historische aanmeldingen worden geanonimiseerd (naam vervangen door "Verwijderd lid")
- Geen externe analytics of tracking

### 10. Meldingen & UX-afwerking — *8 uur*
- Bevestigingsschermen na elke actie
- Foutmeldingen: paar al aangemeld, datum verstreken, niet trainingsgerechtigde
- Laadstatussen, lege-statusmeldingen, terugnavigatie
- "App installeren"-prompt (Android-banner + iOS-instructiescherm)
- Offlinemelding bij geen connectiviteit
- Consistente kleurstelling en typografie (huisstijl club)

### 11. Testen & Deployment — *10 uur*
- Handmatig testen op Android en iPhone (installatieflow, alle gebruikersstromen)
- Testen trainingswhitelist en adminbeveiliging
- CSV-import testen met echte ledenexport
- Deployment naar Render.com / Railway
- Overdrachtshandleiding voor Marieke:
  - Admin PIN instellen
  - Seizoen aanmaken
  - Leden importeren
  - Clubavond toevoegen

---

## Totaaloverzicht

| # | Onderdeel | Uren |
|---|---|---|
| 1 | Project Setup & Architectuur | 8 |
| 2 | Datamodel & Database | 8 |
| 3 | Authenticatie, Rollen & Uitnodigingssysteem | 16 |
| 4 | Publieke Deelnemersweergave | 10 |
| 5 | Aanmeldingsstroom | 16 |
| 6 | Wijzigingsstroom | 20 |
| 7 | Beheerfuncties | 16 |
| 8 | Ledenimport (CSV/Excel) | 8 |
| 9 | GDPR-compliance | 6 |
| 10 | Meldingen & UX-afwerking | 8 |
| 11 | Testen & Deployment | 10 |
| | **Totaal** | **126 uur** |

---

## Openstaande vragen

1. **Ledenlijst formaat** — In welk formaat staat de huidige ledenlijst (Excel, CSV, exporteren uit een systeem)? Wat zijn de kolomnamen?
2. **Huisstijl** — Zijn er kleuren, logo of lettertypes van de club die in de app gebruikt moeten worden?
3. **Loslopers anoniem mailen** — In de eisen staat "misschien een anoniem gemaakte mail naar alle leden" voor loslopers. Moet dit in de eerste versie worden meegenomen?
4. **Trainingsgerechtigden** — Wie bepaalt wie trainingsgerechtigde is? Alleen de admin, of is dit een vaste lijst?
5. **Sociale login provider** — Google is de standaardkeuze. Heeft de club leden die geen Google-account hebben of willen? Zo ja, moeten we ook Microsoft of Apple login ondersteunen?
6. **App Store distributie** — De huidige aanpak is een PWA: installeerbaar via de browser, zonder app store. Is dat voldoende, of moet de app ook beschikbaar zijn in de Google Play Store en/of Apple App Store? Distributie via app stores vereist een aparte build (bijv. met Capacitor of een TWA), developer accounts ($25 eenmalig voor Google, $99/jaar voor Apple), en extra review- en publicatietijd.
