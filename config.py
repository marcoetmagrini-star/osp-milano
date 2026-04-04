"""
OSP Milano - Configurazione centrale
Formula COSAP con microzone OMI (aggiornata 2026)
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "osp.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
LOG_DIR = os.path.join(BASE_DIR, "logs")

PORT = int(os.environ.get("PORT", 8888))
SECRET_KEY = os.environ.get("OSP_SECRET_KEY", "osp-milano-2026-secret-key-change-in-production")
SESSION_HOURS = 8

MAX_GIORNI_OSP = 14
BOLLO_IMPORTO = 16.00
COSAP_MINIMO = 30.00

# ─────────────────────────────────────────────────────────────
# FORMULA COSAP UFFICIALE COMUNE DI MILANO
# COSAP = superficie_mq × giorni × tariffa_base × coeff_microzona × coeff_tipo
# + bollo digitale € 16,00
# ─────────────────────────────────────────────────────────────

# Tariffe base per categoria stradale (€/mq/giorno) - anno 2026
TARIFFE_BASE_COSAP = {
    "A": 4.50,
    "B": 3.00,
    "C": 1.80,
    "D": 1.20,
}

# Coefficienti per tipo di occupazione
COEFFICIENTI_TIPO_OCCUPAZIONE = {
    "TRASLOCO":            1.00,
    "SCARICO_MERCI":       0.80,
    "CONTAINER":           1.20,
    "AUTOGRU":             1.50,
    "AUTOSCALA":           1.50,
    "PIATTAFORMA":         1.30,
    "ISPEZIONE_FACCIATA":  1.00,
    "MANIFESTAZIONE":      2.00,
    "RIPRESE":             1.50,
    "VOLANTINAGGIO":       0.60,
    "EVENTO_COMMERCIALE":  2.50,
    "MERCATINO":           2.00,
    "LAVORI_STRADALI":     1.20,
    "CANTIERE":            1.20,
    "ALTRO":               1.00,
}

# ─────────────────────────────────────────────────────────────
# MICROZONE OMI - Coefficienti di zona
# ─────────────────────────────────────────────────────────────
MICROZONE_OMI = [
    # Zona 1 - Centro Storico (codici B = centrali, coefficienti reali OMI 2023)
    {"codice": "B02", "nome": "Brera / Moscova",                    "zona": 1, "coefficiente": 2.02778, "categoria_strada": "A"},
    {"codice": "B12", "nome": "Duomo / Centro Storico",             "zona": 1, "coefficiente": 2.83333, "categoria_strada": "A"},
    {"codice": "B13", "nome": "Porta Romana / Sant'Ambrogio",       "zona": 1, "coefficiente": 2.58333, "categoria_strada": "A"},
    {"codice": "B15", "nome": "Magenta / Castello",                 "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "B16", "nome": "Porta Ticinese / Navigli",           "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "B17", "nome": "Repubblica / Gioia",                 "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "B18", "nome": "Isola / Garibaldi",                  "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "B19", "nome": "Porta Venezia / Indipendenza",       "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "B20", "nome": "Porta Genova / Darsena",             "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "B21", "nome": "Arco della Pace / Sempione",         "zona": 1, "coefficiente": 2.69167, "categoria_strada": "A"},
    {"codice": "C16", "nome": "Cadorna / Magenta Est",              "zona": 1, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D30", "nome": "Corvetto / Lodi",                    "zona": 1, "coefficiente": 1.05172, "categoria_strada": "C"},
    # Zona 2 - Porta Venezia
    {"codice": "C15", "nome": "Buenos Aires / Loreto",              "zona": 2, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D10", "nome": "Padova / Casoretto",                 "zona": 2, "coefficiente": 1.19444, "categoria_strada": "C"},
    {"codice": "D35", "nome": "Greco / Segnano",                    "zona": 2, "coefficiente": 1.05172, "categoria_strada": "C"},
    {"codice": "D36", "nome": "Turro / Gorla",                      "zona": 2, "coefficiente": 1.05172, "categoria_strada": "C"},
    # Zona 3 - Città Studi
    {"codice": "C12", "nome": "Città Studi / Indipendenza",         "zona": 3, "coefficiente": 1.52778, "categoria_strada": "B"},
    {"codice": "D11", "nome": "Lambrate / Ortica",                  "zona": 3, "coefficiente": 1.06944, "categoria_strada": "C"},
    {"codice": "D12", "nome": "Mecenate / Linate",                  "zona": 3, "coefficiente": 1.27778, "categoria_strada": "C"},
    {"codice": "D13", "nome": "Precotto / Crescenzago",             "zona": 3, "coefficiente": 1.02778, "categoria_strada": "C"},
    # Zona 4 - Porta Vittoria
    {"codice": "C20", "nome": "Porta Vittoria / Umbria",            "zona": 4, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D15", "nome": "Forlanini / Taliedo",                "zona": 4, "coefficiente": 1.05556, "categoria_strada": "C"},
    {"codice": "D16", "nome": "Rogoredo / Santa Giulia",            "zona": 4, "coefficiente": 1.08333, "categoria_strada": "C"},
    {"codice": "D17", "nome": "Medaglie d'Oro / Cuoco",             "zona": 4, "coefficiente": 1.01389, "categoria_strada": "C"},
    {"codice": "D28", "nome": "Corsico / Lorenteggio Est",          "zona": 4, "coefficiente": 0.94444, "categoria_strada": "D"},
    # Zona 5 - Porta Romana
    {"codice": "C19", "nome": "Vigentino / Tibaldi",                "zona": 5, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D18", "nome": "Chiaravalle / Nosedo",               "zona": 5, "coefficiente": 1.00000, "categoria_strada": "C"},
    {"codice": "D20", "nome": "Stadera / Conchetta",                "zona": 5, "coefficiente": 1.08333, "categoria_strada": "C"},
    {"codice": "E07", "nome": "Chiesa Rossa / Gratosoglio",         "zona": 5, "coefficiente": 0.82986, "categoria_strada": "D"},
    {"codice": "R02", "nome": "Chiaravalle / area rurale",          "zona": 5, "coefficiente": 0.70000, "categoria_strada": "D"},
    # Zona 6 - Barona
    {"codice": "C18", "nome": "Barona / Famagosta",                 "zona": 6, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D21", "nome": "Lorenteggio / Cantalupa",            "zona": 6, "coefficiente": 1.13889, "categoria_strada": "C"},
    # Zona 7 - Baggio
    {"codice": "C17", "nome": "De Angeli / San Siro",               "zona": 7, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D24", "nome": "Baggio / Quinto Romano",             "zona": 7, "coefficiente": 1.16667, "categoria_strada": "C"},
    {"codice": "D25", "nome": "Muggiano / Figino",                  "zona": 7, "coefficiente": 0.97222, "categoria_strada": "D"},
    {"codice": "E05", "nome": "Trenno / Bonola",                    "zona": 7, "coefficiente": 0.82986, "categoria_strada": "D"},
    {"codice": "E06", "nome": "Pero / Settimo Milanese",            "zona": 7, "coefficiente": 0.82986, "categoria_strada": "D"},
    # Zona 8 - Fiera / Gallaratese
    {"codice": "C13", "nome": "Fiera / Sempione",                   "zona": 8, "coefficiente": 1.56597, "categoria_strada": "B"},
    # Zona 9 - Porta Garibaldi / Niguarda
    {"codice": "C14", "nome": "Niguarda / Bicocca",                 "zona": 9, "coefficiente": 1.56597, "categoria_strada": "B"},
    {"codice": "D31", "nome": "Dergano / Bovisa",                   "zona": 9, "coefficiente": 1.05172, "categoria_strada": "C"},
    {"codice": "D32", "nome": "Affori / Bruzzano",                  "zona": 9, "coefficiente": 1.05172, "categoria_strada": "C"},
    {"codice": "D33", "nome": "Quarto Oggiaro / Vialba",            "zona": 9, "coefficiente": 1.05172, "categoria_strada": "C"},
    {"codice": "D34", "nome": "Comasina / Maggiolina",              "zona": 9, "coefficiente": 1.05172, "categoria_strada": "C"},
    {"codice": "E08", "nome": "Sacco / Musocco Nord",               "zona": 9, "coefficiente": 0.82986, "categoria_strada": "D"},
]

COEFF_MICROZONA_DEFAULT_PER_ZONA = {
    1: 2.69, 2: 1.57, 3: 1.40, 4: 1.10,
    5: 1.05, 6: 1.10, 7: 1.10, 8: 1.57, 9: 1.05,
}

# ─────────────────────────────────────────────────────────────
# COMANDI DECENTRATI POLIZIA LOCALE
# ─────────────────────────────────────────────────────────────
COMANDI_DECENTRATI = {
    1: {"nome": "Comando Decentrato Zona 1", "quartieri": ["Duomo", "Brera", "Garibaldi", "Porta Venezia", "Porta Romana", "Navigli", "Ticinese"], "indirizzo": "Via Beccaria 19, 20122 Milano", "email": "pl.zona1@comune.milano.it", "pec": "pl.zona1@pec.comune.milano.it", "telefono": "02 88 44 1", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "A", "nil": ["Duomo", "Brera", "Venezia-Garibaldi", "Porta Romana", "Ticinese", "Navigli"]},
    2: {"nome": "Comando Decentrato Zona 2", "quartieri": ["Loreto", "Greco", "Turro", "Gorla", "Precotto", "Cimiano"], "indirizzo": "Via Agordat 3, 20127 Milano", "email": "pl.zona2@comune.milano.it", "pec": "pl.zona2@pec.comune.milano.it", "telefono": "02 88 44 2", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "B", "nil": ["Loreto", "Padova", "Greco", "Turro", "Gorla", "Precotto", "Cimiano"]},
    3: {"nome": "Comando Decentrato Zona 3", "quartieri": ["Città Studi", "Lambrate", "Ortica", "Casoretto"], "indirizzo": "Via Tremelloni 5, 20134 Milano", "email": "pl.zona3@comune.milano.it", "pec": "pl.zona3@pec.comune.milano.it", "telefono": "02 88 44 3", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "B", "nil": ["Città Studi", "Lambrate", "Ortica", "Casoretto"]},
    4: {"nome": "Comando Decentrato Zona 4", "quartieri": ["Vittoria", "Forlanini", "Taliedo", "Rogoredo", "Santa Giulia"], "indirizzo": "Via Oglio 18, 20135 Milano", "email": "pl.zona4@comune.milano.it", "pec": "pl.zona4@pec.comune.milano.it", "telefono": "02 88 44 4", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "B", "nil": ["Vittoria", "Medaglie d'Oro", "Forlanini", "Taliedo", "Rogoredo"]},
    5: {"nome": "Comando Decentrato Zona 5", "quartieri": ["Vigentino", "Chiaravalle", "Gratosoglio", "Tibaldi", "Chiesa Rossa"], "indirizzo": "Via Toffetti 22, 20136 Milano", "email": "pl.zona5@comune.milano.it", "pec": "pl.zona5@pec.comune.milano.it", "telefono": "02 88 44 5", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "C", "nil": ["Vigentino", "Tibaldi", "Chiesa Rossa", "Gratosoglio", "Chiaravalle"]},
    6: {"nome": "Comando Decentrato Zona 6", "quartieri": ["Barona", "Lorenteggio", "Giambellino", "Famagosta", "Ronchetto"], "indirizzo": "Via Ascanio Sforza 85, 20141 Milano", "email": "pl.zona6@comune.milano.it", "pec": "pl.zona6@pec.comune.milano.it", "telefono": "02 88 44 6", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "C", "nil": ["Barona", "Lorenteggio", "Giambellino", "Famagosta"]},
    7: {"nome": "Comando Decentrato Zona 7", "quartieri": ["San Siro", "Trenno", "Baggio", "De Angeli", "Quinto Romano"], "indirizzo": "Via Zurigo 36, 20147 Milano", "email": "pl.zona7@comune.milano.it", "pec": "pl.zona7@pec.comune.milano.it", "telefono": "02 88 44 7", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "C", "nil": ["San Siro", "Trenno", "Baggio", "De Angeli", "Quinto Romano"]},
    8: {"nome": "Comando Decentrato Zona 8", "quartieri": ["Fiera", "Sempione", "Gallaratese", "Quarto Oggiaro", "Affori", "Bruzzano"], "indirizzo": "Via Gallarate 179, 20157 Milano", "email": "pl.zona8@comune.milano.it", "pec": "pl.zona8@pec.comune.milano.it", "telefono": "02 88 44 8", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "B", "nil": ["Fiera", "Sempione", "Gallaratese", "Quarto Oggiaro", "Affori"]},
    9: {"nome": "Comando Decentrato Zona 9", "quartieri": ["Centrale", "Niguarda", "Bicocca", "Dergano", "Bovisa", "Comasina"], "indirizzo": "Via Pusiano 11, 20132 Milano", "email": "pl.zona9@comune.milano.it", "pec": "pl.zona9@pec.comune.milano.it", "telefono": "02 88 44 9", "orari": "Lun-Ven 8:30-12:00 / 14:00-16:30", "categoria_prevalente": "B", "nil": ["Centrale", "Niguarda", "Bicocca", "Dergano", "Bovisa", "Comasina"]},
}

CAP_TO_ZONA = {
    "20121": 1, "20122": 1, "20123": 1, "20124": 1, "20125": 1,
    "20129": 1, "20135": 1, "20136": 1, "20139": 1,
    "20126": 2, "20127": 2, "20128": 2,
    "20131": 3, "20132": 3, "20133": 3, "20134": 3,
    "20137": 4, "20138": 4,
    "20141": 5, "20142": 5, "20143": 5, "20144": 5,
    "20145": 6, "20146": 6,
    "20147": 7, "20148": 7, "20149": 7, "20151": 7,
    "20152": 8, "20153": 8, "20154": 8, "20155": 8,
    "20156": 8, "20157": 8, "20158": 8,
    "20159": 9, "20161": 9, "20162": 9,
}

TIPI_OCCUPAZIONE = {
    "TRASLOCO":            "Trasloco / Sgombero",
    "SCARICO_MERCI":       "Scarico / Carico Merci",
    "CONTAINER":           "Container / Cassone",
    "AUTOGRU":             "Autogru",
    "AUTOSCALA":           "Autoscala / Autopiattaforma",
    "PIATTAFORMA":         "Piattaforma Aerea / Elevatore",
    "ISPEZIONE_FACCIATA":  "Ispezione / Manutenzione Facciata",
    "MANIFESTAZIONE":      "Manifestazione / Evento",
    "RIPRESE":             "Riprese Fotografiche / Video",
    "VOLANTINAGGIO":       "Volantinaggio / Distribuzione Materiale",
    "EVENTO_COMMERCIALE":  "Attività Commerciale Temporanea",
    "MERCATINO":           "Mercatino / Bancarelle",
    "LAVORI_STRADALI":     "Lavori Stradali / Scavi",
    "CANTIERE":            "Cantiere Edilizio (< 14gg)",
    "ALTRO":               "Altro",
}

TIPI_SUPERFICIE = {
    "MARCIAPIEDE": "Marciapiede",
    "CARREGGIATA": "Carreggiata",
    "AREA_VERDE":  "Sterrato / Area Verde",
    "STALLI":      "Stalli di Sosta",
}

TIPI_MODULO_B = {"MANIFESTAZIONE", "EVENTO_COMMERCIALE", "MERCATINO", "RIPRESE", "VOLANTINAGGIO"}

DEBUG = os.environ.get("OSP_DEBUG", "false").lower() == "true"

STATI_PRATICA = {
    "BOZZA":        ("Bozza",         "gray"),
    "INVIATA":      ("Inviata",       "blue"),
    "PAGATA":       ("Pagata",        "orange"),
    "APPROVATA":    ("Approvata",     "green"),
    "RIFIUTATA":    ("Rifiutata",     "red"),
    "INTEGRAZIONI": ("Integrazioni",  "yellow"),
    "ANNULLATA":    ("Annullata",     "gray"),
    "SCADUTA":      ("Scaduta",       "red"),
}
