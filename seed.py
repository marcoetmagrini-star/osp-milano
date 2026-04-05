"""
OSP Milano — Seed database con dati di test aggiornati
Schema v2: microzone OMI reali, richiedenti con residenza/documento, pratiche complete
"""
from database import init_db, get_conn
from services import gen_id, hash_password
from config import MICROZONE_OMI
import datetime


def seed():
    init_db()
    conn = get_conn()

    # ─────────────────────────────────────────────────────────────
    # 1. MICROZONE OMI (dati reali)
    # ─────────────────────────────────────────────────────────────
    for mz in MICROZONE_OMI:
        existing = conn.execute(
            "SELECT id FROM microzone WHERE codice=?", (mz["codice"],)
        ).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO microzone (id, codice, nome, zona, coefficiente, categoria_strada)
                VALUES (?,?,?,?,?,?)
            """, (gen_id(), mz["codice"], mz["nome"],
                  mz["zona"], mz["coefficiente"], mz["categoria_strada"]))
            print(f"  [seed] Microzona: {mz['codice']} {mz['nome']} (zona {mz['zona']}, coeff {mz['coefficiente']})")
    conn.commit()

    # ─────────────────────────────────────────────────────────────
    # 2. UTENTI OPERATORI (uno per zona + admin centrale)
    # ─────────────────────────────────────────────────────────────
    operatori = [
        ("admin",   "admin123",  "Amministratore", "Centrale",  "ADMIN",     0),
        ("zona1op", "zona1pass", "Marco",           "Rossi",     "OPERATORE", 1),
        ("zona2op", "zona2pass", "Laura",           "Bianchi",   "OPERATORE", 2),
        ("zona3op", "zona3pass", "Paolo",           "Verdi",     "OPERATORE", 3),
        ("zona4op", "zona4pass", "Anna",            "Ferrari",   "OPERATORE", 4),
        ("zona5op", "zona5pass", "Luca",            "Romano",    "OPERATORE", 5),
        ("zona6op", "zona6pass", "Sofia",           "Ricci",     "OPERATORE", 6),
        ("zona7op", "zona7pass", "Marco",           "Greco",     "OPERATORE", 7),
        ("zona8op", "zona8pass", "Giulia",          "Bruno",     "OPERATORE", 8),
        ("zona9op", "zona9pass", "Andrea",          "Gallo",     "OPERATORE", 9),
    ]
    for username, pwd, nome, cognome, tipo, zona in operatori:
        if not conn.execute("SELECT id FROM utenti WHERE username=?", (username,)).fetchone():
            uid = gen_id()
            conn.execute("""
                INSERT INTO utenti (id, tipo, zona, username, password_hash, nome, cognome, email)
                VALUES (?,?,?,?,?,?,?,?)
            """, (uid, tipo, zona if zona else None, username,
                  hash_password(pwd), nome, cognome,
                  f"{username}@comune.milano.it"))
            print(f"  [seed] Utente: {username} ({tipo} zona={zona})")
    conn.commit()

    # ─────────────────────────────────────────────────────────────
    # 3. UTENTI RICHIEDENTI DI TEST
    # ─────────────────────────────────────────────────────────────
    richiedenti_test = [
        {
            "username": "azienda1", "pwd": "pass1234",
            "nome": "Carlo", "cognome": "Bianchi",
            "tipo_soggetto": "PERSONA_GIURIDICA",
            "ragione_sociale": "Traslochi Milano Srl",
            "partita_iva": "02345678901",
            "codice_fiscale": "BNCCRL75A01F205X",
            "tipo_documento": "CI", "numero_documento": "AX1234567",
            "data_nascita": "1975-01-01", "luogo_nascita": "Milano (MI)",
            "residenza_via": "Via Roma", "residenza_civico": "10",
            "residenza_cap": "20121", "residenza_citta": "Milano", "residenza_provincia": "MI",
            "sede_via": "Via Roma", "sede_civico": "10",
            "sede_cap": "20121", "sede_citta": "Milano", "sede_provincia": "MI",
            "codice_sdi": "ABCDE12",
            "telefono": "02-1234567", "email": "info@traslochimilanosrl.it",
        },
        {
            "username": "privato1", "pwd": "pass1234",
            "nome": "Giuseppe", "cognome": "Verdi",
            "tipo_soggetto": "PERSONA_FISICA",
            "ragione_sociale": None, "partita_iva": None,
            "codice_fiscale": "VRDGPP60A01F205Y",
            "tipo_documento": "PASSAPORTO", "numero_documento": "YA9876543",
            "data_nascita": "1960-01-01", "luogo_nascita": "Parma (PR)",
            "residenza_via": "Via Garibaldi", "residenza_civico": "5",
            "residenza_cap": "20124", "residenza_citta": "Milano", "residenza_provincia": "MI",
            "sede_via": None, "sede_civico": None,
            "sede_cap": None, "sede_citta": None, "sede_provincia": None,
            "codice_sdi": None,
            "telefono": "333-1234567", "email": "giuseppe.verdi@email.it",
        },
        {
            "username": "eventi1", "pwd": "pass1234",
            "nome": "Sara", "cognome": "Bianchi",
            "tipo_soggetto": "PERSONA_GIURIDICA",
            "ragione_sociale": "Milano Events Srl",
            "partita_iva": "03456789012",
            "codice_fiscale": "BNCSR85B01F205Z",
            "tipo_documento": "CI", "numero_documento": "BX9876543",
            "data_nascita": "1985-02-01", "luogo_nascita": "Milano (MI)",
            "residenza_via": "Corso Buenos Aires", "residenza_civico": "20",
            "residenza_cap": "20124", "residenza_citta": "Milano", "residenza_provincia": "MI",
            "sede_via": "Corso Buenos Aires", "sede_civico": "20",
            "sede_cap": "20124", "sede_citta": "Milano", "sede_provincia": "MI",
            "codice_sdi": "XYZABC1",
            "telefono": "02-9876543", "email": "info@milanoevents.it",
        },
    ]

    created_richiedenti = {}
    for r in richiedenti_test:
        if not conn.execute("SELECT id FROM utenti WHERE username=?", (r["username"],)).fetchone():
            uid = gen_id()
            conn.execute("""
                INSERT INTO utenti (id, tipo, username, password_hash, nome, cognome, email)
                VALUES (?,?,?,?,?,?,?)
            """, (uid, "RICHIEDENTE", r["username"],
                  hash_password(r["pwd"]), r["nome"], r["cognome"], r["email"]))
            rid = gen_id()
            conn.execute("""
                INSERT INTO richiedenti
                (id, utente_id, tipo_soggetto,
                 nome, cognome, data_nascita, luogo_nascita,
                 codice_fiscale, ragione_sociale, partita_iva,
                 tipo_documento, numero_documento,
                 residenza_via, residenza_civico, residenza_cap,
                 residenza_citta, residenza_provincia,
                 sede_via, sede_civico, sede_cap, sede_citta, sede_provincia,
                 codice_sdi, email, telefono)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                rid, uid, r["tipo_soggetto"],
                r["nome"], r["cognome"], r["data_nascita"], r["luogo_nascita"],
                r["codice_fiscale"], r["ragione_sociale"], r["partita_iva"],
                r["tipo_documento"], r["numero_documento"],
                r["residenza_via"], r["residenza_civico"], r["residenza_cap"],
                r["residenza_citta"], r["residenza_provincia"],
                r["sede_via"], r["sede_civico"], r["sede_cap"],
                r["sede_citta"], r["sede_provincia"],
                r["codice_sdi"], r["email"], r["telefono"],
            ))
            created_richiedenti[r["username"]] = rid
            print(f"  [seed] Richiedente: {r['username']} ({r['tipo_soggetto']})")
    conn.commit()

    # ─────────────────────────────────────────────────────────────
    # 4. PRATICHE DI ESEMPIO
    # ─────────────────────────────────────────────────────────────
    def get_rid(username):
        row = conn.execute(
            "SELECT r.id FROM richiedenti r JOIN utenti u ON u.id=r.utente_id WHERE u.username=?",
            (username,)
        ).fetchone()
        return row["id"] if row else None

    def get_mz_id(codice):
        row = conn.execute("SELECT id FROM microzone WHERE codice=?", (codice,)).fetchone()
        return row["id"] if row else None

    def get_op_id(username):
        row = conn.execute("SELECT id FROM utenti WHERE username=?", (username,)).fetchone()
        return row["id"] if row else None

    oggi = datetime.date.today()

    pratiche_seed = [
        {
            "username": "azienda1",
            "numero": f"OSP-{oggi.year}-Z01-TEST01",
            "zona": 1, "tipo_modulo": "A", "tipo_occ": "TRASLOCO",
            "via": "Via Dante", "civico": "12", "cap": "20121", "nil": "Duomo",
            "riferimenti": "Fronte al civico 12, tra palo luce 15 e 17",
            "mz_codice": "B12",
            "tipo_sup": "CARREGGIATA",
            "superficie": 25.0, "metri_x": 5.0, "metri_y": 5.0,
            "data_inizio": str(oggi + datetime.timedelta(days=3)),
            "data_fine": str(oggi + datetime.timedelta(days=4)),
            "ora_inizio": "08:00", "ora_fine": "18:00", "giorni": 2,
            "scopo": "Trasloco appartamento 3° piano",
            "ha_mezzi_speciali": 1, "mezzo_autogru": 0, "mezzo_autoscala": 0,
            "mezzo_autoelevatore": 1, "mezzo_piattaforma": 0,
            "mezzo_targa": "AB123CD", "mezzo_marca": "Iveco", "mezzo_modello": "Daily",
            "mezzo_proprietario": "Traslochi Milano Srl",
            "ha_accesso_limitato": 0,
            "cosap": 567.89, "bollo": 16.0, "totale": 583.89,
            "coeff_mz": 2.83333, "coeff_tipo": 1.0, "tariffa": 4.5,
            "iuv": "100000000000000001",
            "stato": "PAGATA", "pag_stato": "PAGATO",
            "pag_data": datetime.datetime.now().isoformat(),
        },
        {
            "username": "privato1",
            "numero": f"OSP-{oggi.year}-Z02-TEST02",
            "zona": 2, "tipo_modulo": "A", "tipo_occ": "SCARICO_MERCI",
            "via": "Corso Buenos Aires", "civico": "55", "cap": "20124",
            "nil": "Loreto",
            "riferimenti": "Fronte negozio al civico 55",
            "mz_codice": "C15",
            "tipo_sup": "MARCIAPIEDE",
            "superficie": 12.0, "metri_x": 4.0, "metri_y": 3.0,
            "data_inizio": str(oggi + datetime.timedelta(days=1)),
            "data_fine": str(oggi + datetime.timedelta(days=1)),
            "ora_inizio": "09:00", "ora_fine": "13:00", "giorni": 1,
            "scopo": "Scarico mobili da negozio",
            "ha_mezzi_speciali": 0, "mezzo_autogru": 0, "mezzo_autoscala": 0,
            "mezzo_autoelevatore": 0, "mezzo_piattaforma": 0,
            "mezzo_targa": None, "mezzo_marca": None, "mezzo_modello": None,
            "mezzo_proprietario": None,
            "ha_accesso_limitato": 0,
            "cosap": 56.61, "bollo": 16.0, "totale": 72.61,
            "coeff_mz": 1.56597, "coeff_tipo": 0.8, "tariffa": 3.0,
            "iuv": "200000000000000002",
            "stato": "APPROVATA", "pag_stato": "PAGATO",
            "pag_data": datetime.datetime.now().isoformat(),
            "num_concessione": f"CON-{oggi.year}-Z02-00001",
            "data_concessione": datetime.datetime.now().isoformat(),
            "operatore_username": "zona2op",
        },
        {
            "username": "eventi1",
            "numero": f"OSP-{oggi.year}-Z01-TEST03",
            "zona": 1, "tipo_modulo": "B", "tipo_occ": "EVENTO_COMMERCIALE",
            "via": "Piazza del Duomo", "civico": "1", "cap": "20122", "nil": "Duomo",
            "riferimenti": "Area centrale piazza, lato Via Mercanti",
            "mz_codice": "B12",
            "tipo_sup": "MARCIAPIEDE",
            "superficie": 80.0, "metri_x": 10.0, "metri_y": 8.0,
            "data_inizio": str(oggi + datetime.timedelta(days=10)),
            "data_fine": str(oggi + datetime.timedelta(days=12)),
            "ora_inizio": "10:00", "ora_fine": "22:00", "giorni": 3,
            "scopo": "Mercatino gastronomico promozionale",
            "ha_mezzi_speciali": 0, "mezzo_autogru": 0, "mezzo_autoscala": 0,
            "mezzo_autoelevatore": 0, "mezzo_piattaforma": 0,
            "mezzo_targa": None, "mezzo_marca": None, "mezzo_modello": None,
            "mezzo_proprietario": None,
            "ha_accesso_limitato": 1, "accesso_ztl": 1,
            "accesso_localita": "Piazza del Duomo (ZTL attiva)",
            "accesso_veicolo_targa": "EF789GH",
            "cosap": 2039.82, "bollo": 16.0, "totale": 2055.82,
            "coeff_mz": 2.83333, "coeff_tipo": 2.5, "tariffa": 4.5,
            "iuv": "300000000000000003",
            "stato": "INVIATA", "pag_stato": "NON_PAGATO", "pag_data": None,
        },
        {
            "username": "azienda1",
            "numero": f"OSP-{oggi.year}-Z08-TEST04",
            "zona": 8, "tipo_modulo": "A", "tipo_occ": "AUTOGRU",
            "via": "Via Mac Mahon", "civico": "30", "cap": "20155", "nil": "Gallaratese",
            "riferimenti": "Fronte cantiere civico 30, tra i pali luce",
            "mz_codice": "C13",
            "tipo_sup": "CARREGGIATA",
            "superficie": 40.0, "metri_x": 8.0, "metri_y": 5.0,
            "data_inizio": str(oggi + datetime.timedelta(days=5)),
            "data_fine": str(oggi + datetime.timedelta(days=7)),
            "ora_inizio": "07:00", "ora_fine": "17:00", "giorni": 3,
            "scopo": "Installazione ponteggio con autogru",
            "ha_mezzi_speciali": 1, "mezzo_autogru": 1, "mezzo_autoscala": 0,
            "mezzo_autoelevatore": 0, "mezzo_piattaforma": 0,
            "mezzo_targa": "GH456IJ", "mezzo_marca": "Liebherr", "mezzo_modello": "LTM 1060",
            "mezzo_proprietario": "Ponteggi Srl",
            "ha_accesso_limitato": 0,
            "cosap": 282.48, "bollo": 16.0, "totale": 298.48,
            "coeff_mz": 1.56597, "coeff_tipo": 1.5, "tariffa": 3.0,
            "iuv": "400000000000000004",
            "stato": "INTEGRAZIONI", "pag_stato": "PAGATO",
            "pag_data": datetime.datetime.now().isoformat(),
        },
    ]

    for p in pratiche_seed:
        if conn.execute("SELECT id FROM pratiche WHERE numero_pratica=?", (p["numero"],)).fetchone():
            continue
        rid = get_rid(p["username"])
        if not rid:
            continue
        mz_id = get_mz_id(p.get("mz_codice"))
        op_id = get_op_id(p.get("operatore_username")) if p.get("operatore_username") else None
        pid = gen_id()
        conn.execute("""
            INSERT INTO pratiche (
                id, numero_pratica, richiedente_id, zona, microzona_id,
                tipo_modulo, tipo_occupazione,
                via, civico, cap, nil, riferimenti,
                tipo_superficie, superficie_mq, metri_x, metri_y,
                categoria_strada,
                data_inizio, data_fine, ora_inizio, ora_fine, giorni_effettivi,
                scopo,
                ha_mezzi_speciali, mezzo_autogru, mezzo_autoscala,
                mezzo_autoelevatore, mezzo_piattaforma,
                mezzo_targa, mezzo_marca, mezzo_modello, mezzo_proprietario,
                ha_accesso_limitato, accesso_ztl, accesso_localita,
                accesso_veicolo_targa,
                importo_cosap, importo_bollo, importo_totale,
                coefficiente_microzona, coefficiente_tipo, tariffa_base,
                iuv, stato, pagamento_stato, pagamento_data,
                numero_concessione, data_concessione, operatore_id,
                dichiarazioni_ok, prescrizioni_accettate, submitted_at
            ) VALUES (
                ?,?,?,?,?,
                ?,?,
                ?,?,?,?,?,
                ?,?,?,?,
                ?,
                ?,?,?,?,?,
                ?,
                ?,?,?,?,?,
                ?,?,?,?,
                ?,?,?,
                ?,
                ?,?,?,
                ?,?,?,
                ?,?,?,?,
                ?,?,?,
                1,1,?
            )
        """, (
            pid, p["numero"], rid, p["zona"], mz_id,
            p["tipo_modulo"], p["tipo_occ"],
            p["via"], p.get("civico"), p["cap"], p.get("nil"), p.get("riferimenti"),
            p["tipo_sup"], p["superficie"], p.get("metri_x"), p.get("metri_y"),
            "A" if p["zona"] == 1 else ("B" if p["zona"] in (2,3,4,9) else "C"),
            p["data_inizio"], p["data_fine"], p["ora_inizio"], p["ora_fine"], p["giorni"],
            p.get("scopo"),
            p.get("ha_mezzi_speciali", 0), p.get("mezzo_autogru", 0), p.get("mezzo_autoscala", 0),
            p.get("mezzo_autoelevatore", 0), p.get("mezzo_piattaforma", 0),
            p.get("mezzo_targa"), p.get("mezzo_marca"), p.get("mezzo_modello"), p.get("mezzo_proprietario"),
            p.get("ha_accesso_limitato", 0), p.get("accesso_ztl", 0), p.get("accesso_localita"),
            p.get("accesso_veicolo_targa"),
            p["cosap"], p["bollo"], p["totale"],
            p.get("coeff_mz"), p.get("coeff_tipo"), p.get("tariffa"),
            p["iuv"], p["stato"], p["pag_stato"], p.get("pag_data"),
            p.get("num_concessione"), p.get("data_concessione"), op_id,
            datetime.datetime.now().isoformat(),
        ))
        conn.execute("""
            INSERT INTO eventi_pratica (id, pratica_id, tipo, descrizione)
            VALUES (?,?,?,?)
        """, (gen_id(), pid, p["stato"], f"Pratica seed: {p['numero']}"))
        print(f"  [seed] Pratica: {p['numero']} (zona {p['zona']}, {p['stato']})")

    conn.commit()
    conn.close()

    print("\n✅ Seed completato!\n")
    print("  CREDENZIALI TEST:")
    print("  " + "─" * 50)
    print("  Admin centrale : admin    / admin123")
    print("  Zona 1 op.     : zona1op  / zona1pass")
    print("  Zona 2 op.     : zona2op  / zona2pass")
    print("  Zona 3 op.     : zona3op  / zona3pass")
    print("  Richiedente 1  : azienda1 / pass1234")
    print("  Richiedente 2  : privato1 / pass1234")
    print("  Richiedente 3  : eventi1  / pass1234")
    print("  " + "─" * 50)
    print(f"\n  Microzone OMI caricate: {len(MICROZONE_OMI)}")
    print()


if __name__ == "__main__":
    seed()
