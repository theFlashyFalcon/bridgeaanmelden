"""Genereer de gebruiksaanwijzing van de Crash-app als PDF."""

from fpdf import FPDF
from fpdf.enums import XPos, YPos


FONT_DIR = r"C:\Windows\Fonts"

class PDF(FPDF):
    PRIMARY = (30, 58, 95)    # donkerblauw
    ACCENT  = (52, 120, 200)  # helder blauw
    MUTED   = (110, 110, 110)
    LIGHT   = (245, 247, 250)
    WHITE   = (255, 255, 255)
    BLACK   = (30, 30, 30)
    GREEN   = (39, 130, 70)
    YELLOW  = (180, 130, 0)
    RED     = (180, 40, 40)

    def _setup_fonts(self):
        import os
        base = FONT_DIR
        try:
            self.add_font("Arial", "",  os.path.join(base, "arial.ttf"))
            self.add_font("Arial", "B", os.path.join(base, "arialbd.ttf"))
            self.add_font("Arial", "I", os.path.join(base, "ariali.ttf"))
            self._uf = "Arial"
        except Exception:
            self._uf = "Helvetica"  # fallback zonder unicode symbolen

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self._uf, "I", 8)
        self.set_text_color(*self.MUTED)
        self.cell(0, 8, "Crash — Bridge Club Aanmeldingsapp — Gebruiksaanwijzing",
                  align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*self.ACCENT)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_font(self._uf, "I", 8)
        self.set_text_color(*self.MUTED)
        self.cell(0, 8, f"Pagina {self.page_no()}", align="C")

    # ── helpers ────────────────────────────────────────────────────────────

    def h1(self, text):
        self.ln(4)
        self.set_fill_color(*self.PRIMARY)
        self.set_text_color(*self.WHITE)
        self.set_font(self._uf, "B", 15)
        self.cell(0, 10, text, fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*self.BLACK)
        self.ln(3)

    def h2(self, text):
        self.ln(3)
        self.set_text_color(*self.ACCENT)
        self.set_font(self._uf, "B", 12)
        self.cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*self.ACCENT)
        self.set_line_width(0.4)
        self.line(self.l_margin, self.get_y(), self.l_margin + 60, self.get_y())
        self.set_text_color(*self.BLACK)
        self.ln(2)

    def h3(self, text):
        self.ln(2)
        self.set_font(self._uf, "B", 10)
        self.set_text_color(*self.PRIMARY)
        self.cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*self.BLACK)
        self.ln(1)

    def body(self, text, indent=0):
        self.set_font(self._uf, "", 9.5)
        self.set_text_color(*self.BLACK)
        self.set_x(self.l_margin + indent)
        self.multi_cell(0, 5.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet(self, text, indent=4):
        self.set_font(self._uf, "", 9.5)
        self.set_text_color(*self.BLACK)
        x = self.l_margin + indent
        self.set_x(x)
        self.cell(4, 5.5, "•")
        self.set_x(x + 4)
        self.multi_cell(self.w - self.r_margin - x - 4, 5.5, text,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def note(self, text):
        self.set_fill_color(*self.LIGHT)
        self.set_draw_color(200, 210, 230)
        self.set_line_width(0.3)
        self.set_font(self._uf, "I", 9)
        self.set_text_color(*self.MUTED)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5, text, fill=True, border=1,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*self.BLACK)
        self.ln(1)

    def code(self, text):
        self.set_fill_color(240, 240, 240)
        self.set_font("Courier", "", 9)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5, text, fill=True,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*self.BLACK)
        self.ln(1)

    def table(self, headers, rows, col_widths=None):
        """Eenvoudige tabel."""
        usable = self.w - self.l_margin - self.r_margin
        if col_widths is None:
            w = usable / len(headers)
            col_widths = [w] * len(headers)

        # header
        self.set_fill_color(*self.PRIMARY)
        self.set_text_color(*self.WHITE)
        self.set_font(self._uf, "B", 8.5)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1, fill=True, align="L")
        self.ln()

        # rows
        self.set_font(self._uf, "", 8.5)
        for ri, row in enumerate(rows):
            fill = ri % 2 == 1
            self.set_fill_color(*self.LIGHT)
            self.set_text_color(*self.BLACK)
            # multi-line row support
            line_heights = []
            for ci, cell in enumerate(row):
                lines = self._split_text(cell, col_widths[ci] - 2)
                line_heights.append(len(lines))
            max_lines = max(line_heights) if line_heights else 1
            row_h = 5.5 * max_lines
            x0 = self.get_x()
            y0 = self.get_y()
            for ci, cell in enumerate(row):
                self.set_xy(x0 + sum(col_widths[:ci]), y0)
                self.multi_cell(col_widths[ci], 5.5, cell,
                                border=1, fill=fill,
                                new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.set_xy(x0, y0 + row_h)
            self.ln(0)
        self.ln(3)

    def _split_text(self, text, width):
        """Estimate number of lines for multi_cell."""
        self.set_font(self._uf, "", 8.5)
        words = text.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            if self.get_string_width(test) <= width - 2:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [""]

    def role_badge(self, label, color):
        self.set_fill_color(*color)
        self.set_text_color(*self.WHITE)
        self.set_font(self._uf, "B", 8)
        self.cell(self.get_string_width(label) + 4, 5.5, label,
                  fill=True, align="C")
        self.set_text_color(*self.BLACK)


# ═══════════════════════════════════════════════════════════════════════════════

def build_pdf():
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(18, 20, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf._setup_fonts()

    # ── Titelpagina ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(*PDF.PRIMARY)
    pdf.rect(0, 0, 210, 80, "F")

    pdf.set_font(pdf._uf, "B", 32)
    pdf.set_text_color(*PDF.WHITE)
    pdf.set_y(22)
    pdf.cell(0, 14, "Crash", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(pdf._uf, "", 14)
    pdf.cell(0, 9, "Bridge Club Aanmeldingsapp", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(pdf._uf, "I", 11)
    pdf.cell(0, 8, "Gebruiksaanwijzing & Functionaliteitsomschrijving", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(88)
    pdf.set_text_color(*PDF.BLACK)
    pdf.set_font(pdf._uf, "", 10)
    pdf.cell(0, 7, "Deze handleiding beschrijft alle functies van de Crash-app:", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, "aanmelden voor avonden, berichten, ranking, uitslagen en beheer.",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # drie rollen als badges
    pdf.ln(8)
    roles = [("lid", PDF.ACCENT), ("wedstrijdleider", PDF.YELLOW), ("admin", PDF.RED)]
    total_w = sum(pdf.get_string_width(r) + 4 + 8 for r, _ in roles)
    pdf.set_x((210 - total_w) / 2)
    for label, color in roles:
        pdf.role_badge(label, color)
        pdf.set_x(pdf.get_x() + 8)

    # ── Inhoudsopgave ────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font(pdf._uf, "B", 16)
    pdf.set_text_color(*PDF.PRIMARY)
    pdf.cell(0, 12, "Inhoudsopgave", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*PDF.ACCENT)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    toc = [
        ("1.", "Wat is de app?", 3),
        ("2.", "Rollen", 3),
        ("3.", "Account aanmaken en inloggen", 3),
        ("4.", "Agenda (homepage)", 4),
        ("5.", "Aanmelden voor een evenement", 4),
        ("6.", "Berichtenbox", 5),
        ("7.", "Ranking", 5),
        ("8.", "Uitslagen", 5),
        ("9.", "Mijn profiel", 5),
        ("10.", "Wedstrijdleider — Clubagenda", 6),
        ("11.", "Admin — Gebruikersbeheer", 7),
        ("12.", "Admin — Weergave simuleren", 8),
        ("13.", "Technische details", 8),
    ]
    pdf.set_text_color(*PDF.BLACK)
    for num, title, page in toc:
        pdf.set_font(pdf._uf, "B", 9.5)
        pdf.cell(10, 6.5, num)
        pdf.set_font(pdf._uf, "", 9.5)
        pdf.cell(0, 6.5, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── 1. Wat is de app ─────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("1. Wat is de app?")
    pdf.body(
        "De Crash-app is een webapplicatie voor de bridgeclub Crash. Leden kunnen zich "
        "aanmelden voor clubavonden en andere evenementen, berichten sturen, de ranking "
        "bekijken en uitslagen raadplegen. Beheerders beheren de agenda en leden."
    )
    pdf.ln(2)
    pdf.body(
        "De app draait in de browser en is ook te installeren als app op je telefoon "
        "(via 'Zet op beginscherm' in Safari op iOS). Er is geen aparte installatie nodig."
    )

    # ── 2. Rollen ────────────────────────────────────────────────────────────
    pdf.h1("2. Rollen")
    pdf.body("Er zijn drie rollen in de app:")
    pdf.ln(2)
    pdf.table(
        ["Rol", "Wat kan je?"],
        [
            ["lid",
             "Agenda bekijken, aan- en afmelden voor evenementen, berichten sturen, "
             "ranking en uitslagen inzien, profiel bekijken."],
            ["wedstrijdleider",
             "Alles van lid + agenda en evenementen beheren, aanmeldingen van alle leden "
             "inzien, partnerverzoeken goedkeuren of afwijzen, handmatige paren toevoegen."],
            ["admin",
             "Alles van wedstrijdleider + gebruikersbeheer, uitnodigingen versturen, "
             "roltoewijzingen beheren, aanwezigheidsstatistieken inzien, "
             "seizoenen beheren, SMTP-verbinding testen."],
        ],
        col_widths=[38, 136],
    )
    pdf.note(
        "De admin kan via het 'Weergave'-menu in de navigatie tijdelijk "
        "de app bekijken alsof hij/zij een lid of wedstrijdleider is."
    )

    # ── 3. Account ───────────────────────────────────────────────────────────
    pdf.h1("3. Account aanmaken en inloggen")

    pdf.h2("Nieuw account aanmaken")
    pdf.body(
        "Ga naar de homepage en klik op 'Account aanmaken'. Vul je voornaam, achternaam, "
        "lidnummer en e-mailadres in en kies een wachtwoord. De aanvraag gaat naar de "
        "beheerder ter goedkeuring. Zodra die goedkeurt ontvang je een bevestigingsmail."
    )

    pdf.h2("Inloggen")
    pdf.body(
        "Klik op 'Inloggen' in de navigatiebalk (of ga naar /login). Vul je e-mailadres "
        "en wachtwoord in."
    )

    pdf.h2("Wachtwoord vergeten")
    pdf.body(
        "Op de loginpagina staat 'Wachtwoord vergeten'. Vul je e-mailadres in en je "
        "ontvangt een resetlink per e-mail (vereist geconfigureerde e-mailserver)."
    )

    pdf.h2("Uitloggen")
    pdf.body("Klik op 'Uitloggen' rechtsboven in de navigatiebalk.")

    # ── 4. Agenda ────────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("4. Agenda (homepage /)")
    pdf.body(
        "De agenda is het startpunt van de app. Je ziet alle komende evenementen "
        "van het actieve seizoen."
    )

    pdf.h2("Filtertabs")
    pdf.body("Bovenaan staan tabs om te filteren op type:")
    pdf.bullet("Alle — alle komende evenementen")
    pdf.bullet("Clubavond — reguliere wekelijkse avonden")
    pdf.bullet("Avondeten — eten voor jeugdtraining")
    pdf.bullet("Training — jeugdtraining (alleen voor leden met trainingstoegang)")
    pdf.bullet("Speciaal — speciale evenementen")
    pdf.bullet("Weergave ((gear)) — stel in welke typen je wil zien (opgeslagen per account)")

    pdf.h2("Evenementkaarten")
    pdf.body("Elk evenement toont:")
    pdf.bullet("Datum, naam en evenementtype")
    pdf.bullet("Inschrijfdeadline indien ingesteld (* Inschrijven voor...)")
    pdf.bullet("Jouw aanmeldstatus: aangemeld (met partnernaam) of niet aangemeld")
    pdf.bullet("Knop 'Aanmelden' of 'Wijzigen'")
    pdf.bullet("Knop 'Bekijk aanmeldingen' voor wedstrijdleiders en admins")

    pdf.h2("Bulk aanmelden / afmelden")
    pdf.body(
        "Twee knoppen staan boven de evenementenlijst:"
    )
    pdf.bullet("'Voor alles aanmelden' — meld je in één klik aan voor alle komende evenementen")
    pdf.bullet("'Voor alles afmelden' — meld je af voor alles (vraagt bevestiging)")

    pdf.h2("Definitief aanmelden")
    pdf.body(
        "Als je filtert op een specifiek type (bijv. 'Clubavond'), verschijnt de knop "
        "'Meld mij definitief aan voor alle clubavonden'. Dit registreert een vaste "
        "aanmelding: je wordt automatisch aangemeld voor elk nieuw evenement van dat "
        "type dat later wordt aangemaakt. Je ontvangt daarvoor een automatisch bericht "
        "vanuit de app."
    )

    # ── 5. Aanmelden ─────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("5. Aanmelden voor een evenement (/aanmelden/{id})")
    pdf.body(
        "Klik op 'Aanmelden' bij een evenement. Het formulier past zich aan het type aan:"
    )
    pdf.ln(2)
    pdf.table(
        ["Deelnemerstype", "Wat invullen"],
        [
            ["Paren",       "Voornaam + achternaam van je partner"],
            ["Individueel", "Geen partner nodig"],
            ["Viertallen",  "Maximaal 3 teamgenoten (elk met voor- en achternaam)"],
        ],
        col_widths=[42, 132],
    )

    pdf.h2("Partner zoeken")
    pdf.body(
        "De app controleert of de ingevulde partnernaam voorkomt in de ledenlijst. "
        "Staat de naam er niet in, dan wordt automatisch een partnerverzoek aangemaakt "
        "dat de wedstrijdleider handmatig moet goedkeuren of afwijzen."
    )

    pdf.h2("Inschrijftermijn")
    pdf.body(
        "Als er een inschrijftermijn is ingesteld (bijv. 24 uur voor aanvang), "
        "wordt een aanmelding na die deadline als 'te laat' gemarkeerd. "
        "De wedstrijdleider kan te-laat-aanmeldingen goedkeuren of verwijderen."
    )

    pdf.h2("Afmelden")
    pdf.body("Klik op de aanmeldknop bij het evenement en kies 'Afmelden'.")

    # ── 6. Berichten ─────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("6. Berichtenbox (/berichten)")
    pdf.body(
        "Intern berichtensysteem waarmee leden onderling en met de wedstrijdleider "
        "kunnen communiceren."
    )

    pdf.h2("Nieuw bericht sturen")
    pdf.body("Klik '+ Nieuw bericht' en vul in:")
    pdf.bullet("Ontvanger — voornaam + achternaam (met autocomplete op de ledenlijst)")
    pdf.bullet("Onderwerp — verplicht")
    pdf.bullet("Bericht — de tekst")

    pdf.h2("Conversaties")
    pdf.body(
        "Berichten zijn georganiseerd in threads. Klik op een gesprek om het te openen "
        "en te reageren. Ongelezen berichten worden vet weergegeven met een oranje badge. "
        "De navigatiebalk toont het aantal ongelezen berichten als badge naast 'Berichtenbox'."
    )

    pdf.h2("Nieuwsberichten")
    pdf.body(
        "Wedstrijdleiders en admins kunnen nieuwsberichten versturen zonder specifieke "
        "ontvanger. Die verschijnen in het tabblad 'Nieuws' voor alle leden."
    )

    # ── 7. Ranking ───────────────────────────────────────────────────────────
    pdf.h1("7. Ranking (/ranking)")
    pdf.body(
        "Toont de actuele clubranking als tabel, gebaseerd op een geupload CSV-bestand. "
        "De kolomkoppen en rijen worden automatisch overgenomen uit het bestand."
    )
    pdf.bullet("Wedstrijdleiders en admins zien de knop 'Uploaden' om een nieuw CSV te laden")
    pdf.bullet("Datum en naam van de uploader worden vermeld onder de tabel")

    # ── 8. Uitslagen ─────────────────────────────────────────────────────────
    pdf.h1("8. Uitslagen (/uitslagen)")
    pdf.body(
        "Overzicht van beschikbare PDF-uitslagen per clubavond (trainingen en avondeten "
        "worden niet getoond)."
    )
    pdf.bullet("Zoekbalk: zoek op naam of datum in dd/mm/jjjj-formaat")
    pdf.bullet("Klik op een avond om de PDF-uitslag te downloaden")
    pdf.bullet("Wedstrijdleiders/admins zien een 'Uploaden'-knop per avond om een PDF toe te voegen")

    # ── 9. Profiel ───────────────────────────────────────────────────────────
    pdf.h1("9. Mijn profiel (/profiel)")
    pdf.body("Persoonlijke overzichtspagina met drie secties:")
    pdf.bullet("Accountgegevens: naam, lidnummer, e-mail, rol")
    pdf.bullet(
        "Definitieve aanmeldingen: welke evenementtypen je vast aangemeld bent en tot wanneer"
    )
    pdf.bullet(
        "Aanmeldingsgeschiedenis: de laatste 50 aanmeldingen met datum, avond, status en partner"
    )

    # ── 10. Wedstrijdleider ───────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("10. Wedstrijdleider — Clubagenda")

    pdf.h2("Avonden beheren (/beheer/avonden)")
    pdf.body(
        "Overzicht van alle geplande evenementen. Via het 'Aanmaken'-dropdown kun je "
        "seizoenen en evenementen toevoegen."
    )

    pdf.h3("Seizoen aanmaken")
    pdf.body("Vul naam, startdatum en einddatum in. Optioneel: meteen activeren.")
    pdf.note(
        "Er kan slechts één seizoen tegelijk actief zijn. Alleen evenementen in het "
        "actieve seizoen verschijnen in de agenda voor leden."
    )

    pdf.h3("Evenement aanmaken")
    pdf.body("Beschikbare typen: Clubavond, Eten voor jeugdtraining, Training, Speciaal.")
    pdf.body("In te vullen:")
    pdf.bullet("Naam en datum")
    pdf.bullet("Deelnemerstype: Individueel, Paren of Viertallen")
    pdf.bullet(
        "Inschrijftermijn (optioneel): bijv. '24 uren' of '2 dagen'. "
        "Aanmeldingen na deze deadline zijn 'te laat'."
    )
    pdf.bullet(
        "Herhalen: vink 'Herhaal deze gebeurtenis' aan om de avond wekelijks of dagelijks "
        "aan te maken tot een opgegeven einddatum."
    )
    pdf.body(
        "Het seizoen wordt automatisch bepaald op basis van de datum. "
        "Als er geen seizoen bestaat voor die datum, verschijnt een foutmelding."
    )

    pdf.h2("Af- en aanmeldingen (/beheer/af-aanmeldingen)")
    pdf.body(
        "Overzicht van alle aankomende evenementen met filteropties per type. "
        "Per evenement staat het aantal openstaande partnerverzoeken."
    )

    pdf.h3("Detail per avond")
    pdf.body("Klik op een evenement voor het detailoverzicht:")
    pdf.table(
        ["Sectie", "Inhoud"],
        [
            ["Volledig aangemeld",   "Paren die compleet zijn aangemeld"],
            ["Solo / loslopers",     "Aangemeld zonder partner"],
            ["Afgemeld",             "Leden die zich hebben afgemeld"],
            ["Handmatige paren",     "Paren die niet via een account zijn ingevoerd"],
            ["Partnerverzoeken",     "Verzoeken voor een partner buiten de ledenlijst — "
                                    "goedkeuren of afwijzen"],
            ["Te laat aangemeld",    "Aanmeldingen na de inschrijftermijn — "
                                    "goedkeuren of verwijderen"],
        ],
        col_widths=[48, 126],
    )
    pdf.body(
        "Via 'Paar handmatig toevoegen' voeg je een naam 1 en naam 2 toe (of alleen "
        "naam 1 voor een solo). Via 'Printversie' genereer je een afdrukpagina met alle paren."
    )

    pdf.h2("Aanmeldingenoverzicht (/beheer/aanmeldingen)")
    pdf.body(
        "Compacter overzicht per evenement: alle aanmeldingen en de 10 meest recente "
        "wijzigingen."
    )

    pdf.h2("Loslopers (/beheer/loslopers)")
    pdf.body(
        "Overzicht van alle leden die op dit moment aangemeld zijn als "
        "'beschikbaar solo' (zonder partner)."
    )

    # ── 11. Admin gebruikersbeheer ────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("11. Admin — Gebruikersbeheer")

    pdf.h2("Inkomende verzoeken (/beheer/aanvragen)")
    pdf.body(
        "Lijst van accountaanvragen. Per aanvraag:"
    )
    pdf.bullet("Goedkeuren: wijs een rol toe, verstuur activatiemail")
    pdf.bullet("Afwijzen: aanvraag wordt afgewezen")
    pdf.body(
        "Ook zichtbaar: contactberichten die via de homepage zijn verstuurd door "
        "niet-ingelogde bezoekers."
    )

    pdf.h2("Uitnodigingen (/beheer/uitnodigingen)")
    pdf.body(
        "Stuur een uitnodigingslink direct naar een e-mailadres. "
        "De ontvanger kan via de link direct een account aanmaken zonder goedkeuringsproces. "
        "Stel de rol vooraf in. Beheer van bestaande uitnodigingen: "
        "verwijder afgehandelde of alle uitnodigingen."
    )
    pdf.body(
        "Via de knop 'SMTP-test' stuur je een testmail naar je eigen e-mailadres om "
        "de e-mailconfiguratie te controleren."
    )

    pdf.h2("Roltoewijzingen (/beheer/rollen)")
    pdf.body(
        "Wijs een rol toe aan een e-mailadres. Als dat e-mailadres later een account "
        "aanmaakt, krijgt het automatisch de ingestelde rol (lid, wedstrijdleider of admin)."
    )

    pdf.h2("Gebruikerslijst (/leden)")
    pdf.body(
        "Overzicht van alle loginaccounts: naam, lidnummer, e-mail en rol. "
        "Hier zijn de echte accounts van leden te zien."
    )

    pdf.h2("Ledenlijst (/beheer/leden)")
    pdf.body(
        "Aparte lijst van bridgeleden voor de partnerzoekfunctie bij aanmelden. "
        "Dit zijn geen loginaccounts maar namen in de autocomplete. "
        "Bevat voornaam, achternaam en optioneel NBB-nummer."
    )
    pdf.body("Toevoegen via:")
    pdf.bullet("Handmatig — één lid tegelijk invoeren")
    pdf.bullet(
        "CSV-import — upload een bestand met kolommen 'voornaam', 'achternaam', "
        "optioneel 'nbb_nummer'"
    )

    pdf.h2("Aanwezigheidsstatistieken (/beheer/aanwezigheid)")
    pdf.body(
        "Per seizoen: voor elk lid het aantal avonden aanwezig en afgemeld, "
        "weergegeven met een procentuele balk. Kies het seizoen via het dropdownmenu."
    )

    pdf.h2("Seizoenen (/beheer/seizoenen)")
    pdf.body(
        "Overzicht van alle seizoenen met naam, start- en einddatum en status "
        "(actief / inactief). Klik 'Activeer' om een ander seizoen actief te maken. "
        "Seizoenen zijn ook aanmakbaar vanuit het avondenbeheer."
    )

    # ── 12. Weergave simuleren ────────────────────────────────────────────────
    pdf.h1("12. Admin — Weergave simuleren")
    pdf.body(
        "Admins kunnen de app tijdelijk bekijken als een andere rol via het "
        "'Weergave'-dropdownmenu in de navigatie:"
    )
    pdf.bullet("Als lid — geen beheermenu's zichtbaar")
    pdf.bullet("Als wedstrijdleider — beheermenu's van wedstrijdleider zichtbaar")
    pdf.bullet("Admin (standaard) — terug naar volledige adminweergave")
    pdf.body(
        "Een gele banner bovenaan de pagina geeft aan dat je in een andere weergave zit."
    )

    # ── 13. Technische details ────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("13. Technische details (voor beheerders)")

    pdf.h2("Installatie")
    pdf.body("Vereist Python 3.12. Installeer afhankelijkheden:")
    pdf.code("pip install -r requirements.txt")

    pdf.h2("Omgevingsvariabelen (.env)")
    pdf.table(
        ["Variabele", "Beschrijving"],
        [
            ["SECRET_KEY",      "Geheime sleutel voor sessiebeheer (verplicht in productie)"],
            ["ADMIN_EMAIL",     "E-mailadres van de eerste beheerder"],
            ["ADMIN_PASSWORD",  "Wachtwoord voor automatisch aanmaken admin bij eerste start"],
            ["DATABASE_URL",    "Database-URL (standaard: lokaal SQLite bridgeclub.db). "
                                "Gebruik postgresql://... voor PostgreSQL."],
            ["BASE_URL",        "Publieke URL van de app (voor links in e-mails)"],
            ["SMTP_HOST",       "Hostnaam van de e-mailserver"],
            ["SMTP_PORT",       "Poort (standaard 587)"],
            ["SMTP_USER",       "Gebruikersnaam SMTP"],
            ["SMTP_PASSWORD",   "Wachtwoord SMTP"],
            ["SMTP_FROM",       "Afzenderadres voor uitgaande mail"],
        ],
        col_widths=[48, 126],
    )

    pdf.h2("App starten (lokaal)")
    pdf.body("Via het snelstartscript:")
    pdf.code("start_local.bat")
    pdf.body("Of handmatig:")
    pdf.code("uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
    pdf.body("De app is daarna bereikbaar op http://localhost:8000")

    pdf.h2("Database en migraties")
    pdf.body(
        "Bij elke start worden automatisch ontbrekende tabellen en kolommen "
        "aangemaakt via create_all en de ingebouwde migratiefunctie. "
        "Alembic-migraties zijn beschikbaar voor handmatige upgrades:"
    )
    pdf.code("alembic upgrade head")

    pdf.h2("Deployment (productie)")
    pdf.body("De Procfile start de app via:")
    pdf.code("uvicorn app.main:app --host 0.0.0.0 --port $PORT")
    pdf.body(
        "Werkt op platforms als Render of Heroku. Stel DATABASE_URL, SECRET_KEY, "
        "ADMIN_EMAIL en de SMTP-variabelen in als omgevingsvariabelen op het platform."
    )

    pdf.h2("PWA (Progressive Web App)")
    pdf.body(
        "De app is configureerbaar als PWA. Op iOS verschijnt een installatieprompt "
        "('Zet op beginscherm'). Op Android en desktop kan de app worden geïnstalleerd "
        "vanuit de browser."
    )

    return pdf


# ── Uitvoeren ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pdf = build_pdf()
    output_path = "Crash_Gebruiksaanwijzing.pdf"
    pdf.output(output_path)
    print(f"PDF aangemaakt: {output_path}")
