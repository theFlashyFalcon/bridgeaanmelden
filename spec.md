# User Stories — Bridge Club Aanmeldingsapp

**Versie:** 1.0  
**Datum:** 22 april 2026  
**Gerelateerd aan:** [implementatieplan.md](implementatieplan.md)

---

## Inhoudsopgave

1. [Authenticatie & Uitnodigingssysteem](#1-authenticatie--uitnodigingssysteem)
2. [Rollenbeheer](#2-rollenbeheer)
3. [Publieke Deelnemersweergave](#3-publieke-deelnemersweergave)
4. [Aanmelden](#4-aanmelden)
5. [Wijzigen](#5-wijzigen)
6. [Beheerfuncties — Wedstrijdleider](#6-beheerfuncties--wedstrijdleider)
7. [Beheerfuncties — Admin](#7-beheerfuncties--admin)
8. [Ledenimport](#8-ledenimport)
9. [GDPR & Privacy](#9-gdpr--privacy)
10. [PWA & Installatie](#10-pwa--installatie)

---

## Rollen

| Code | Rol | Omschrijving |
|---|---|---|
| **G** | Gast / niet-ingelogd | Kan alleen de publieke weergave zien |
| **L** | Lid | Standaardrol na registratie via uitnodigingslink |
| **W** | Wedstrijdleider | Kan avonden beheren en aanmeldingen inzien |
| **A** | Admin | Volledige toegang |

---

## 1. Authenticatie & Uitnodigingssysteem

---

### US-01 — Uitnodigingslink genereren

**Als** Admin  
**wil ik** voor een potentieel lid een persoonlijke, enkelvoudig-te-gebruiken uitnodigingslink genereren  
**zodat** alleen door mij uitgenodigde mensen toegang krijgen tot de app.

**Acceptatiecriteria:**
- De admin kan in het beheerpaneel een e-mailadres invoeren en een uitnodigingslink genereren.
- De gegenereerde link is uniek per uitnodiging en kan slechts één keer worden gebruikt.
- De link bevat een cryptografisch willekeurige token (minimaal 32 tekens).
- De link en het bijbehorende e-mailadres zijn zichtbaar in het uitnodigingoverzicht met status `open`.
- De admin kopieert de link zelf en verstuurt deze buiten de app per e-mail.

---

### US-02 — Account aanmaken via uitnodigingslink

**Als** uitgenodigde gebruiker  
**wil ik** via mijn persoonlijke uitnodigingslink een account aanmaken met mijn Google-account  
**zodat** ik toegang krijg tot de app.

**Acceptatiecriteria:**
- De uitnodigingslink opent een welkomstpagina met uitleg en een "Inloggen met Google"-knop.
- Na succesvolle Google-login wordt een account aangemaakt met rol `Lid`.
- De uitnodigingslink wordt gemarkeerd als `gebruikt` en kan niet opnieuw worden gebruikt.
- Als de link al gebruikt is, ziet de gebruiker een duidelijke foutmelding.
- Als de link niet bestaat of verlopen is, ziet de gebruiker een duidelijke foutmelding.
- Gebruikers zonder uitnodigingslink kunnen geen account aanmaken.

---

### US-03 — Inloggen

**Als** Lid / Wedstrijdleider / Admin  
**wil ik** inloggen via mijn Google-account  
**zodat** ik toegang krijg tot mijn persoonlijke aanmeldingen en de functies die bij mijn rol horen.

**Acceptatiecriteria:**
- De startpagina toont een "Inloggen met Google"-knop voor niet-ingelogde gebruikers.
- Na inloggen wordt de gebruiker doorgestuurd naar de hoofdpagina.
- De sessie blijft actief totdat de gebruiker uitlogt of de sessie verloopt.
- Als het Google-account niet gekoppeld is aan een uitgenodigde gebruiker, wordt toegang geweigerd met een duidelijke melding.

---

### US-04 — Uitloggen

**Als** ingelogd gebruiker  
**wil ik** kunnen uitloggen  
**zodat** mijn account beveiligd is op een gedeeld apparaat.

**Acceptatiecriteria:**
- Er is een zichtbare uitlogknop beschikbaar vanuit het menu.
- Na uitloggen wordt de sessiecookie ongeldig gemaakt.
- De gebruiker wordt teruggestuurd naar de publieke weergave.

---

### US-05 — Uitnodigingoverzicht

**Als** Admin  
**wil ik** een overzicht zien van alle gegenereerde uitnodigingslinks met hun status  
**zodat** ik weet wie al een account heeft aangemaakt en wie de link nog niet heeft gebruikt.

**Acceptatiecriteria:**
- Het overzicht toont per uitnodiging: e-mailadres, aanmaakdatum, status (`open` / `gebruikt` / `verlopen`).
- De admin kan een ongebruikte uitnodiging intrekken (status wordt `verlopen`).
- Ingetrokken links geven bij gebruik een foutmelding aan de uitgenodigde.

---

## 2. Rollenbeheer

---

### US-06 — Rol toewijzen aan een lid

**Als** Admin  
**wil ik** de rol van een lid kunnen wijzigen naar `Wedstrijdleider` of `Admin`  
**zodat** specifieke mensen uitgebreide beheerfuncties krijgen.

**Acceptatiecriteria:**
- In het ledenbeheer is per lid een dropdown beschikbaar met de opties `Lid`, `Wedstrijdleider`, `Admin`.
- Na opslaan heeft het lid direct toegang tot de functies die bij de nieuwe rol horen.
- Een Admin kan zijn eigen rol niet verlagen (ter voorkoming van lock-out).
- De wijziging is zichtbaar in het ledenoverzicht.

---

### US-07 — Rolgebaseerde navigatie

**Als** ingelogd gebruiker  
**wil ik** dat het navigatiemenu alleen de functies toont die voor mijn rol beschikbaar zijn  
**zodat** de interface overzichtelijk blijft en ik niet op vergrendelde pagina's terecht kom.

**Acceptatiecriteria:**
- Leden zien alleen: Deelnemersoverzicht, Aanmelden, Mijn aanmeldingen / Wijzigen.
- Wedstrijdleiders zien aanvullend: Avondenbeheer, Aanmeldingenoverzicht, Loslopers.
- Admins zien aanvullend: Ledenbeheer, Seizoenenbeheer, Uitnodigingen, Rollenbeheer, Import.
- Directe URL-toegang tot een niet-toegestane pagina geeft een 403-melding.

---

## 3. Publieke Deelnemersweergave

---

### US-08 — Aangemelde paren bekijken

**Als** bezoeker (ook niet-ingelogd)  
**wil ik** de aangemelde paren voor de eerstvolgende clubavond zien  
**zodat** ik weet wie er die avond speelt.

**Acceptatiecriteria:**
- De pagina is zichtbaar zonder inloggen.
- De datum en het type van de eerstvolgende avond worden getoond.
- Vaste paren worden bovenaan getoond, alfabetisch op voornaam van de eerste persoon van het paar.
- Losse paren worden daaronder getoond, ook alfabetisch op voornaam van de eerste persoon.
- Een teller bovenaan toont het totaal aantal aangemelde paren.
- Combipaar-aanmeldingen worden weergegeven als "Voornaam A + Voornaam B (combipaar)".
- Losse soloaanmeldingen (zonder partner) worden in een aparte sectie weergegeven.

---

### US-09 — Loslopers inzien

**Als** Wedstrijdleider of Admin  
**wil ik** een apart overzicht zien van loslopers (leden die aangegeven hebben beschikbaar te zijn zonder partner)  
**zodat** ik hen eventueel kan koppelen.

**Acceptatiecriteria:**
- Het loslopersoverzicht is niet zichtbaar voor gewone leden of niet-ingelogde bezoekers.
- Het overzicht toont per losloper: naam en voor welke datum zij beschikbaar zijn.
- Het overzicht is benaderbaar vanuit het navigatiemenu voor de juiste rollen.

---

## 4. Aanmelden

---

### US-10 — Naam zoeken in ledenlijst

**Als** Lid  
**wil ik** mijn naam zoeken in de ledenlijst  
**zodat** ik me snel en correct kan aanmelden zonder mijn gegevens opnieuw in te voeren.

**Acceptatiecriteria:**
- Er is een zoekveld beschikbaar waar ik kan typen op voornaam of achternaam.
- Zoekresultaten worden gefilterd terwijl ik typ (minimaal 2 tekens).
- Ik kan mijn naam selecteren uit de zoekresultaten.

---

### US-11 — Partner selecteren of solo aanmelden

**Als** Lid  
**wil ik** na het selecteren van mijn eigen naam kiezen of ik solo aanmeld of een partner selecteer  
**zodat** ik me zowel als individu als als paar kan aanmelden.

**Acceptatiecriteria:**
- Na mijn eigen naam te hebben geselecteerd, krijg ik de keuze: "Solo aanmelden" of "Partner selecteren".
- Bij "Partner selecteren" gebruik ik dezelfde zoekfunctie als bij stap 1.
- Ik kan niet mezelf als partner selecteren.
- Ik kan een lid niet als partner selecteren als diegene al aangemeld is als vast partnership voor die periode.

---

### US-12 — Aanmelden als vast partnership

**Als** Lid  
**wil ik** me samen met een partner aanmelden als vast partnership vanaf een bepaalde datum  
**zodat** we voor alle clubavonden vanaf die datum automatisch als paar aangemeld staan.

**Acceptatiecriteria:**
- Het aanmeldingstype "Vast partnership" is selecteerbaar nadat ik een partner heb gekozen.
- Ik kan een startdatum kiezen uit de beschikbare avonden in het huidige seizoen.
- Na bevestiging zijn we aangemeld voor alle reguliere clubavonden vanaf de gekozen datum.
- Een bevestigingsscherm toont een samenvatting van de aanmelding.

---

### US-13 — Aanmelden voor alle trainingsavonden

**Als** trainingsgerechtigde Lid  
**wil ik** me aanmelden voor alle trainingsavonden van het seizoen  
**zodat** ik niet elke keer apart hoef aan te melden.

**Acceptatiecriteria:**
- Het aanmeldingstype "Alle trainingsavonden" is alleen zichtbaar voor trainingsgerechtigde leden.
- Na selectie kan ik een startdatum kiezen.
- Na bevestiging ben ik aangemeld voor alle trainingsavonden vanaf de gekozen datum.
- Niet-trainingsgerechtigde leden zien dit aanmeldingstype niet.

---

### US-14 — Aanmelden voor losse avonden

**Als** Lid  
**wil ik** me aanmelden voor één of meerdere specifieke avonden  
**zodat** ik flexibel per avond kan kiezen wanneer ik meedoe.

**Acceptatiecriteria:**
- Het aanmeldingstype "Losse avonden" toont een overzicht van alle komende avonden in het seizoen.
- Ik kan meerdere datums tegelijk selecteren.
- Trainingsdatums zijn alleen selecteerbaar voor trainingsgerechtigde leden.
- Datums in het verleden zijn niet selecteerbaar.
- Avonden waarvoor ik al aangemeld ben, zijn gemarkeerd en niet opnieuw selecteerbaar.
- Na bevestiging verschijnt een bevestigingsscherm met een overzicht van de geselecteerde avonden.

---

### US-15 — Bevestigingsscherm na aanmelding

**Als** Lid  
**wil ik** na elke aanmelding een bevestigingsscherm zien  
**zodat** ik zeker weet dat mijn aanmelding is verwerkt.

**Acceptatiecriteria:**
- Het bevestigingsscherm toont: namen van de aangemelde perso(o)n(en), aanmeldingstype en de geselecteerde datum(s).
- Er is een knop om terug te gaan naar de hoofdpagina.
- Er is een knop om nog een aanmelding te doen.

---

## 5. Wijzigen

---

### US-16 — Datum selecteren voor wijziging

**Als** Lid  
**wil ik** eerst een datum kiezen waarvoor ik een wijziging wil doorgeven  
**zodat** ik gericht de juiste aanmelding kan aanpassen.

**Acceptatiecriteria:**
- De datumkeuze toont alleen avonden waarvoor ik aangemeld ben.
- Verstreken datums worden getoond maar zijn duidelijk gemarkeerd als "verstreken".
- Wijzigingen voor verstreken datums zijn niet mogelijk.

---

### US-17 — Paar selecteren voor wijziging

**Als** Lid  
**wil ik** na het kiezen van een datum mijn aangemeld paar kunnen selecteren  
**zodat** ik de juiste aanmelding aanpas als ik voor meerdere combinaties aangemeld ben.

**Acceptatiecriteria:**
- De dropdown toont alleen de paren waarvoor ik aangemeld ben op de gekozen datum.
- Als er slechts één aanmelding is, wordt dit paar automatisch geselecteerd.

---

### US-18 — Invaller opgeven

**Als** Lid  
**wil ik** een invaller opgeven voor mijn aanmelding  
**zodat** er iemand anders voor mij kan spelen als ik zelf niet kan.

**Acceptatiecriteria:**
- Ik kan de naam van de invaller invoeren als vrij tekstveld.
- Na opslaan toont de deelnemersweergave de invallernaam naast mijn naam.
- De aanmeldingsstatus wordt bijgewerkt naar `invaller`.

---

### US-19 — Aanmelding annuleren

**Als** Lid  
**wil ik** mijn aanmelding voor een specifieke avond annuleren  
**zodat** de wedstrijdleider weet dat ik niet kom.

**Acceptatiecriteria:**
- Na kiezen van "Annuleren" verschijnt een bevestigingsvraag.
- Na bevestiging wordt de aanmeldingsstatus bijgewerkt naar `afgemeld`.
- Het paar verdwijnt uit de publieke deelnemersweergave.
- Een combipaar dat afhankelijk is van deze aanmelding, wordt ook gemarkeerd.

---

### US-20 — Eén van de twee beschikbaar opgeven

**Als** Lid  
**wil ik** kunnen aangeven dat slechts één persoon van het paar beschikbaar is  
**zodat** de wedstrijdleider weet dat die persoon als losloper beschikbaar is.

**Acceptatiecriteria:**
- Ik kan kiezen welk lid van het paar beschikbaar is.
- Na opslaan wordt de aanmelding zichtbaar als losloper voor Wedstrijdleiders en Admins.
- De status wordt bijgewerkt naar `beschikbaar_solo`.

---

### US-21 — Combipaar doorgeven

**Als** Lid  
**wil ik** een combipaar doorgeven zodat ik samen met een ander paar speel  
**zodat** beide paren op die avond toch kunnen deelnemen.

**Acceptatiecriteria:**
- Ik kan kiezen uit: alle vaste paren (ook afgemelde) én alle paren aangemeld voor die datum.
- Na selectie zien beide paren in hun eigen overzicht met wie ze gaan spelen.
- Het gekozen andere paar wordt automatisch afgemeld als zelfstandig paar (status `afgemeld`).
- De aanmeldingsstatus van beide paren wordt bijgewerkt naar `combipaar`.
- Als het andere paar zelf ook al een combipaarwijziging had, wordt een waarschuwing getoond.

---

### US-22 — Afmelden als vast partnership

**Als** Lid dat aangemeld staat als vast partnership  
**wil ik** me afmelden als vast partnership  
**zodat** we niet meer automatisch worden aangemeld voor toekomstige avonden.

**Acceptatiecriteria:**
- De optie "Afmelden als vast partnership" is alleen zichtbaar als de aanmelding van het type `vast` is.
- Na bevestiging worden toekomstige aanmeldingen vanuit dit vast partnership verwijderd.
- Reeds verstreken aanmeldingen blijven in de historische data bewaard.
- Ik kan daarna voor dezelfde datum opnieuw los aanmelden als ik wil.

---

## 6. Beheerfuncties — Wedstrijdleider

---

### US-23 — Clubavond toevoegen

**Als** Wedstrijdleider of Admin  
**wil ik** een nieuwe clubavond toevoegen aan het seizoen  
**zodat** leden zich hiervoor kunnen aanmelden.

**Acceptatiecriteria:**
- Ik kan een datum, type (`regulier` of `training`) en het actieve seizoen opgeven.
- Een training mag alleen worden toegevoegd als er een reguliere avond in dezelfde week bestaat.
- Na opslaan is de avond zichtbaar in de aanmeldingsflow voor leden.
- Trainingsdatums zijn alleen zichtbaar voor trainingsgerechtigde leden.

---

### US-24 — Clubavond bewerken of verwijderen

**Als** Wedstrijdleider of Admin  
**wil ik** een bestaande clubavond kunnen bewerken of verwijderen  
**zodat** ik fouten kan corrigeren of afgelaste avonden kan verwijderen.

**Acceptatiecriteria:**
- Ik kan datum en type van een bestaande avond aanpassen.
- Bij verwijderen van een avond met bestaande aanmeldingen, verschijnt een waarschuwing.
- Na bevestiging worden de bijbehorende aanmeldingen ook verwijderd.

---

### US-25 — Aanmeldingenoverzicht per avond inzien

**Als** Wedstrijdleider of Admin  
**wil ik** per avond een volledig overzicht zien van alle aanmeldingen, afmeldingen en wijzigingen  
**zodat** ik de avond goed kan voorbereiden.

**Acceptatiecriteria:**
- Ik kan een avond selecteren en zie alle aangemelde paren met hun status.
- Statuswijzigingen (invaller, combipaar, beschikbaar_solo, afgemeld) zijn duidelijk zichtbaar.
- De tijdstempel van elke wijziging wordt getoond.
- Ik kan het overzicht filteren op status.

---

## 7. Beheerfuncties — Admin

---

### US-26 — Seizoen aanmaken

**Als** Admin  
**wil ik** een nieuw seizoen aanmaken  
**zodat** clubavonden en aanmeldingen aan het juiste seizoen worden gekoppeld.

**Acceptatiecriteria:**
- Ik kan een naam (bijv. "2025–2026"), startdatum en einddatum opgeven.
- Ik kan een seizoen als actief markeren; dit deactiveert automatisch het vorige seizoen.
- Alleen avonden binnen het actieve seizoen zijn selecteerbaar bij aanmelden.

---

### US-27 — Ledenlijst beheren

**Als** Admin  
**wil ik** leden handmatig kunnen toevoegen, bewerken en verwijderen  
**zodat** de ledenlijst actueel blijft.

**Acceptatiecriteria:**
- Ik kan een nieuw lid toevoegen met voornaam, achternaam en lidnummer.
- Ik kan bestaande gegevens van een lid bewerken.
- Bij verwijderen van een lid met aanmeldingen, worden historische aanmeldingen geanonimiseerd (zie US-35).
- Lidnummers zijn uniek; een duplicaat geeft een foutmelding.

---

### US-28 — Trainingsgerechtigdheid instellen

**Als** Admin  
**wil ik** per lid kunnen instellen of diegene trainingsgerechtigde is  
**zodat** trainingsdatums alleen zichtbaar zijn voor de juiste groep mensen.

**Acceptatiecriteria:**
- In het ledenbeheer is per lid een schakelaar beschikbaar voor `training_eligible`.
- Na aanpassen ziet het lid direct wel of geen trainingsdatums in de aanmeldingsflow.

---

## 8. Ledenimport

---

### US-29 — CSV- of Excel-bestand uploaden

**Als** Admin  
**wil ik** een bestaande ledenlijst uploaden als `.csv` of `.xlsx`  
**zodat** ik niet alle leden handmatig hoef in te voeren.

**Acceptatiecriteria:**
- Ik kan een `.csv` of `.xlsx` bestand uploaden via het beheerpaneel.
- Bestanden groter dan 5 MB worden geweigerd met een foutmelding.
- Bestanden met een ongeldig formaat worden geweigerd met een duidelijke melding.

---

### US-30 — Kolommen koppelen bij import

**Als** Admin  
**wil ik** na het uploaden de kolommen van mijn bestand kunnen koppelen aan de velden in de app  
**zodat** de import correct verwerkt wordt ongeacht de kolomnamen in mijn bronbestand.

**Acceptatiecriteria:**
- Na uploaden zie ik de kolomkoppen van het bestand en kan ik per veld (`Voornaam`, `Achternaam`, `Lidnummer`) de bijbehorende kolom selecteren.
- Alle drie de velden zijn verplicht te koppelen voordat ik door kan gaan.

---

### US-31 — Preview en bevestigen van import

**Als** Admin  
**wil ik** een preview zien van de te importeren leden voordat de import definitief wordt  
**zodat** ik fouten kan ontdekken voordat ze in de database terechtkomen.

**Acceptatiecriteria:**
- De preview toont de eerste 20 rijen van de import.
- Rijen met ontbrekende verplichte velden zijn rood gemarkeerd en worden overgeslagen.
- Bestaande leden (zelfde lidnummer) zijn gemarkeerd als "wordt bijgewerkt" of "wordt overgeslagen" (te kiezen).
- Nieuwe leden zijn gemarkeerd als "nieuw".
- Ik kan de import bevestigen of annuleren.

---

### US-32 — Importrapport ontvangen

**Als** Admin  
**wil ik** na de import een rapport zien van het resultaat  
**zodat** ik weet hoeveel leden zijn toegevoegd, bijgewerkt of overgeslagen.

**Acceptatiecriteria:**
- Het rapport toont: aantal nieuw toegevoegd, aantal bijgewerkt, aantal overgeslagen (en reden).
- Het rapport is direct zichtbaar na afronding van de import.

---

## 9. GDPR & Privacy

---

### US-33 — Privacymelding bij eerste gebruik

**Als** nieuwe gebruiker  
**wil ik** bij mijn eerste bezoek een privacymelding zien  
**zodat** ik weet welke gegevens de app opslaat en waarvoor.

**Acceptatiecriteria:**
- Bij het eerste bezoek na aanmaken van een account verschijnt een privacymelding.
- De melding bevat een link naar de volledige privacybeleidspagina.
- Ik moet de melding actief sluiten; de app is daarna volledig bruikbaar.
- De bevestiging wordt opgeslagen zodat de melding niet bij elk bezoek opnieuw verschijnt.

---

### US-34 — Privacybeleid raadplegen

**Als** gebruiker  
**wil ik** het privacybeleid van de app kunnen lezen  
**zodat** ik weet hoe mijn gegevens worden gebruikt, bewaard en wie de verwerkingsverantwoordelijke is.

**Acceptatiecriteria:**
- Er is een privacybeleidspagina bereikbaar via de voettekst van de app.
- De pagina beschrijft: welke gegevens worden opgeslagen, doel van verwerking, bewaartermijn, contactgegevens van de verwerkingsverantwoordelijke.
- De pagina is ook bereikbaar zonder inloggen.

---

### US-35 — Lid verwijderen (recht op vergetelheid)

**Als** Admin  
**wil ik** een lid volledig kunnen verwijderen uit de app  
**zodat** we voldoen aan het GDPR-recht op vergetelheid.

**Acceptatiecriteria:**
- Na verwijdering wordt het member record uit de database verwijderd.
- Historische aanmeldingen worden geanonimiseerd: naam vervangen door "Verwijderd lid", lidnummer verwijderd.
- De aanmeldingsdata zelf (datum, type, status) blijft bewaard voor statistisch gebruik.
- Er verschijnt een bevestigingsvraag vóór verwijdering.

---

### US-36 — Seizoendata archiveren of verwijderen

**Als** Admin  
**wil ik** oude seizoendata kunnen archiveren of verwijderen  
**zodat** we persoonsgegevens niet langer bewaren dan noodzakelijk.

**Acceptatiecriteria:**
- Ik kan een afgesloten seizoen selecteren en kiezen voor "Archiveren" of "Verwijderen".
- Bij "Archiveren" blijft de data bewaard maar is niet meer zichtbaar in de actieve weergaven.
- Bij "Verwijderen" worden alle aanmeldingsgegevens van dat seizoen permanent gewist.
- Er verschijnt een bevestigingsvraag met vermelding van hoeveel records worden verwijderd.
- Het actieve seizoen kan niet worden verwijderd.

---

## 10. PWA & Installatie

---

### US-37 — App installeren op Android

**Als** Lid met een Android-telefoon  
**wil ik** de app kunnen installeren op mijn startscherm  
**zodat** ik de app snel kan openen zonder een browser te openen.

**Acceptatiecriteria:**
- De app voldoet aan de PWA-installatievereisten (manifest, service worker, HTTPS).
- Bij het eerste bezoek in een ondersteunende browser verschijnt een installatie-banner.
- Na installatie opent de app in standalone modus (zonder adresbalk).

---

### US-38 — App installeren op iPhone

**Als** Lid met een iPhone  
**wil ik** weten hoe ik de app kan toevoegen aan mijn startscherm  
**zodat** ik de app snel kan openen.

**Acceptatiecriteria:**
- De app toont een instructiemodal voor iOS-gebruikers met stap-voor-stap uitleg: "Tik op Deel → Zet op beginscherm".
- De instructie wordt alleen getoond op iOS-apparaten en alleen als de app nog niet standalone draait.

---

### US-39 — Offlinemelding

**Als** gebruiker zonder internetverbinding  
**wil ik** een duidelijke melding zien dat de app offline is  
**zodat** ik weet waarom de inhoud niet laadt en niet denk dat de app kapot is.

**Acceptatiecriteria:**
- De service worker toont een offline-pagina als er geen verbinding is.
- De offline-pagina legt uit dat de app een internetverbinding vereist.
- Zodra de verbinding hersteld is, kan de gebruiker de pagina vernieuwen.

---

### US-40 — Foutmeldingen bij ongeldige acties

**Als** gebruiker  
**wil ik** begrijpelijke foutmeldingen zien als ik iets doe dat niet toegestaan is  
**zodat** ik weet wat er mis is en hoe ik verder kan.

**Acceptatiecriteria:**
- Foutmeldingen zijn in het Nederlands en beschrijven het probleem zonder technische termen.
- De volgende situaties geven een specifieke foutmelding:
  - Paar al aangemeld voor de gekozen datum.
  - Datum ligt in het verleden.
  - Lid niet trainingsgerechtigde voor trainingsdatum.
  - Uitnodigingslink al gebruikt of verlopen.
  - Toegang tot pagina zonder de juiste rol.
- Na een foutmelding blijft de gebruiker op de huidige stap staan (geen verlies van ingevulde gegevens).
