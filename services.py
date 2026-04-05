"""
OSP Milano - Servizi: COSAP, Zone, Email, PDF, Auth
"""
import hashlib, uuid, json, os, re, datetime, logging, sqlite3
from config import (
    TARIFFE_BASE_COSAP, COEFFICIENTI_TIPO_OCCUPAZIONE, COSAP_MINIMO, BOLLO_IMPORTO,
    MAX_GIORNI_OSP, COMANDI_DECENTRATI, CAP_TO_ZONA,
    TIPI_OCCUPAZIONE, COEFF_MICROZONA_DEFAULT_PER_ZONA, MICROZONE_OMI, SECRET_KEY,
    LOG_DIR, UPLOAD_DIR,
)

EMAIL_LOG_PATH = os.path.join(LOG_DIR, "emails.log")

# Tipi che usano Modulo B (attività commerciali/eventi)
TIPI_MODULO_B = {"MANIFESTAZIONE", "EVENTO_COMMERCIALE", "MERCATINO", "RIPRESE", "VOLANTINAGGIO"}
from database import get_conn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("osp")


# ─────────────────────────────────────────────────────────────
# UTILITÀ
# ─────────────────────────────────────────────────────────────

def gen_id():
    return str(uuid.uuid4())

def hash_password(pwd):
    return hashlib.sha256((pwd + SECRET_KEY).encode()).hexdigest()

def verify_password(pwd, hashed):
    return hash_password(pwd) == hashed

def gen_numero_pratica(zona):
    now = datetime.datetime.now()
    seq = str(uuid.uuid4().int)[:6]
    return f"OSP-{now.year}-Z{zona:02d}-{seq}"

def gen_numero_concessione(zona):
    now = datetime.datetime.now()
    seq = str(uuid.uuid4().int)[:5]
    return f"CON-{now.year}-Z{zona:02d}-{seq}"

def gen_iuv():
    return str(uuid.uuid4().int)[:18]


# ─────────────────────────────────────────────────────────────
# AUTH / SESSIONI
# ─────────────────────────────────────────────────────────────

def crea_sessione(utente_id):
    token = str(uuid.uuid4()) + str(uuid.uuid4())
    expires = (datetime.datetime.now() + datetime.timedelta(hours=8)).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessioni (token, utente_id, expires_at) VALUES (?, ?, ?)",
        (token, utente_id, expires)
    )
    conn.execute(
        "UPDATE utenti SET last_login=? WHERE id=?",
        (datetime.datetime.now().isoformat(), utente_id)
    )
    conn.commit()
    conn.close()
    return token

def get_utente_da_token(token):
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        """SELECT u.* FROM utenti u
           JOIN sessioni s ON s.utente_id = u.id
           WHERE s.token=? AND s.expires_at > datetime('now') AND u.attivo=1""",
        (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def elimina_sessione(token):
    conn = get_conn()
    conn.execute("DELETE FROM sessioni WHERE token=?", (token,))
    conn.commit()
    conn.close()

def login(username, password):
    conn = get_conn()
    utente = conn.execute(
        "SELECT * FROM utenti WHERE username=? AND attivo=1", (username,)
    ).fetchone()
    conn.close()
    if not utente:
        return None, "Utente non trovato"
    if not verify_password(password, utente["password_hash"]):
        return None, "Password errata"
    token = crea_sessione(utente["id"])
    return dict(utente), token


# ─────────────────────────────────────────────────────────────
# ZONE
# ─────────────────────────────────────────────────────────────

def rileva_zona_da_cap(cap):
    cap_clean = re.sub(r'\D', '', str(cap))[:5]
    zona = CAP_TO_ZONA.get(cap_clean)
    if zona:
        return zona, COMANDI_DECENTRATI[zona]
    return 1, COMANDI_DECENTRATI[1]  # default zona 1

def get_categoria_strada_da_zona(zona):
    return COMANDI_DECENTRATI.get(zona, {}).get("categoria_prevalente", "C")

def get_info_zona(zona):
    return COMANDI_DECENTRATI.get(int(zona), COMANDI_DECENTRATI[1])


# ─────────────────────────────────────────────────────────────
# CALCOLO COSAP
# ─────────────────────────────────────────────────────────────

def get_coeff_microzona(microzona_id=None, zona=None):
    """Restituisce il coefficiente di microzona dal DB o dal default di zona."""
    if microzona_id:
        try:
            conn = get_conn()
            r = conn.execute(
                "SELECT coefficiente, categoria_strada FROM microzone WHERE id=?",
                (microzona_id,)
            ).fetchone()
            conn.close()
            if r:
                return float(r["coefficiente"]), r["categoria_strada"]
        except Exception:
            pass
    zona_int = int(zona) if zona else 1
    coeff = COEFF_MICROZONA_DEFAULT_PER_ZONA.get(zona_int, 1.0)
    cat = COMANDI_DECENTRATI.get(zona_int, {}).get("categoria_prevalente", "C")
    return coeff, cat

def calcola_cosap(superficie_mq, giorni, categoria_strada, tipo_occupazione,
                  coeff_microzona=None, microzona_id=None, zona=None):
    """
    Formula COSAP Comune di Milano:
    COSAP = superficie × giorni × tariffa_base(categoria) × coeff_microzona × coeff_tipo
    """
    if coeff_microzona is None:
        coeff_microzona, categoria_strada = get_coeff_microzona(microzona_id, zona)

    tariffa = TARIFFE_BASE_COSAP.get(categoria_strada, TARIFFE_BASE_COSAP["C"])
    coeff_tipo = COEFFICIENTI_TIPO_OCCUPAZIONE.get(tipo_occupazione, 1.0)
    cosap = superficie_mq * giorni * tariffa * coeff_microzona * coeff_tipo
    cosap = max(cosap, COSAP_MINIMO)
    cosap = round(cosap, 2)
    totale = round(cosap + BOLLO_IMPORTO, 2)
    return {
        "cosap": cosap,
        "bollo": BOLLO_IMPORTO,
        "totale": totale,
        "dettaglio": (
            f"{superficie_mq} mq × {giorni} gg × "
            f"€{tariffa}/mq/gg (cat.{categoria_strada}) × "
            f"coeff.zona {coeff_microzona} × coeff.tipo {coeff_tipo}"
        ),
        "categoria_strada": categoria_strada,
        "tariffa_base": tariffa,
        "coefficiente_microzona": coeff_microzona,
        "coefficiente_tipo": coeff_tipo,
        "giorni": giorni,
    }

def calcola_giorni(data_inizio_str, data_fine_str):
    try:
        d1 = datetime.date.fromisoformat(data_inizio_str)
        d2 = datetime.date.fromisoformat(data_fine_str)
        delta = (d2 - d1).days + 1
        return max(1, delta)
    except Exception:
        return 1


# ─────────────────────────────────────────────────────────────
# PRATICHE
# ─────────────────────────────────────────────────────────────

def crea_pratica(richiedente_id, zona, dati):
    pratica_id = gen_id()
    numero = gen_numero_pratica(zona)
    giorni = calcola_giorni(dati["data_inizio"], dati["data_fine"])
    microzona_id = dati.get("microzona_id")
    coeff_microzona, categoria_strada = get_coeff_microzona(microzona_id, zona)
    # Override categoria se fornita esplicitamente
    if dati.get("categoria_strada"):
        categoria_strada = dati["categoria_strada"]
    cosap_info = calcola_cosap(
        float(dati["superficie_mq"]),
        giorni,
        categoria_strada,
        dati["tipo_occupazione"],
        coeff_microzona=coeff_microzona,
    )
    # Calcola COSAP fase 2 se presente
    cosap_osp2 = None
    if dati.get("ha_fase_successiva") and dati.get("osp2_superficie_mq"):
        giorni2 = calcola_giorni(
            dati.get("osp2_data_inizio", dati["data_inizio"]),
            dati.get("osp2_data_fine", dati["data_fine"])
        )
        c2 = calcola_cosap(
            float(dati["osp2_superficie_mq"]), giorni2,
            categoria_strada, dati["tipo_occupazione"],
            coeff_microzona=coeff_microzona,
        )
        cosap_osp2 = c2["cosap"]
        cosap_info["cosap"] += cosap_osp2
        cosap_info["totale"] = round(cosap_info["cosap"] + BOLLO_IMPORTO, 2)

    iuv = gen_iuv()
    tipo_modulo = "B" if dati["tipo_occupazione"] in TIPI_MODULO_B else "A"

    conn = get_conn()
    conn.execute("""
        INSERT INTO pratiche (
            id, numero_pratica, richiedente_id, zona, microzona_id,
            tipo_modulo, tipo_occupazione,
            -- Localizzazione OSP
            via, civico, cap, riferimenti, nil, lat, lng,
            tipo_superficie, rientrante_stalli, eccedente_stalli, eccedente_dove,
            superficie_mq, metri_x, metri_y, categoria_strada,
            -- Periodo
            data_inizio, data_fine, ora_inizio, ora_fine, giorni_effettivi,
            -- Descrizione
            scopo, descrizione, motivazione,
            -- Mezzi speciali
            ha_mezzi_speciali, mezzo_autogru, mezzo_autoscala, mezzo_autoelevatore,
            mezzo_piattaforma, mezzo_altro, mezzo_altro_desc,
            mezzo_targa, mezzo_marca, mezzo_modello, mezzo_proprietario,
            -- Accessi
            ha_accesso_limitato, accesso_corsia_mezzi, accesso_ztl,
            accesso_area_pedonale, accesso_altro, accesso_altro_desc,
            accesso_localita, accesso_veicolo_marca, accesso_veicolo_modello,
            accesso_veicolo_targa, accesso_veicolo_proprietario,
            -- Fase 2
            ha_fase_successiva, osp2_via, osp2_civico, osp2_riferimenti,
            osp2_superficie_mq, osp2_metri_x, osp2_metri_y, osp2_tipo_superficie,
            osp2_rientrante_stalli, osp2_eccedente_stalli, osp2_eccedente_dove,
            osp2_data_inizio, osp2_data_fine, osp2_ora_inizio, osp2_ora_fine, osp2_scopo,
            osp2_ha_mezzi_speciali,
            -- Modulo B
            attivita_commerciale, attivita_pubblicita, attivita_spettacolo, dettagli_attivita,
            -- Pagamento
            importo_cosap, importo_cosap_osp2, importo_bollo, importo_totale,
            coefficiente_microzona, coefficiente_tipo, tariffa_base, iuv,
            -- Stato
            stato, dichiarazioni_ok, prescrizioni_accettate
        ) VALUES (
            ?,?,?,?,?,
            ?,?,
            ?,?,?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,?,
            ?,?,?,
            ?,?,?,?,
            ?,?,?,
            ?,?,?,?,
            ?,?,?,
            ?,?,?,
            ?,?,?,?,
            ?,?,?,?,?,?,?,
            ?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            'INVIATA',?,?
        )
    """, (
        pratica_id, numero, richiedente_id, zona, microzona_id,
        tipo_modulo, dati["tipo_occupazione"],
        # Localizzazione
        dati["via"], dati.get("civico",""), dati["cap"],
        dati.get("riferimenti"), dati.get("nil"), dati.get("lat"), dati.get("lng"),
        dati["tipo_superficie"],
        1 if dati.get("rientrante_stalli") else 0,
        1 if dati.get("eccedente_stalli") else 0,
        dati.get("eccedente_dove"),
        float(dati["superficie_mq"]),
        float(dati["metri_x"]) if dati.get("metri_x") else None,
        float(dati["metri_y"]) if dati.get("metri_y") else None,
        categoria_strada,
        # Periodo
        dati["data_inizio"], dati["data_fine"],
        dati.get("ora_inizio"), dati.get("ora_fine"), giorni,
        # Descrizione
        (dati.get("scopo") or dati.get("descrizione",""))[:40],
        dati.get("descrizione"), dati.get("motivazione"),
        # Mezzi speciali
        1 if dati.get("ha_mezzi_speciali") else 0,
        1 if dati.get("mezzo_autogru") else 0,
        1 if dati.get("mezzo_autoscala") else 0,
        1 if dati.get("mezzo_autoelevatore") else 0,
        1 if dati.get("mezzo_piattaforma") else 0,
        1 if dati.get("mezzo_altro") else 0,
        dati.get("mezzo_altro_desc"),
        dati.get("mezzo_targa"), dati.get("mezzo_marca"),
        dati.get("mezzo_modello"), dati.get("mezzo_proprietario"),
        # Accessi
        1 if dati.get("ha_accesso_limitato") else 0,
        1 if dati.get("accesso_corsia_mezzi") else 0,
        1 if dati.get("accesso_ztl") else 0,
        1 if dati.get("accesso_area_pedonale") else 0,
        1 if dati.get("accesso_altro") else 0,
        dati.get("accesso_altro_desc"),
        dati.get("accesso_localita"),
        dati.get("accesso_veicolo_marca"), dati.get("accesso_veicolo_modello"),
        dati.get("accesso_veicolo_targa"), dati.get("accesso_veicolo_proprietario"),
        # Fase 2
        1 if dati.get("ha_fase_successiva") else 0,
        dati.get("osp2_via"), dati.get("osp2_civico"), dati.get("osp2_riferimenti"),
        float(dati["osp2_superficie_mq"]) if dati.get("osp2_superficie_mq") else None,
        float(dati["osp2_metri_x"]) if dati.get("osp2_metri_x") else None,
        float(dati["osp2_metri_y"]) if dati.get("osp2_metri_y") else None,
        dati.get("osp2_tipo_superficie"),
        1 if dati.get("osp2_rientrante_stalli") else 0,
        1 if dati.get("osp2_eccedente_stalli") else 0,
        dati.get("osp2_eccedente_dove"),
        dati.get("osp2_data_inizio"), dati.get("osp2_data_fine"),
        dati.get("osp2_ora_inizio"), dati.get("osp2_ora_fine"),
        (dati.get("osp2_scopo",""))[:40],
        1 if dati.get("osp2_ha_mezzi_speciali") else 0,
        # Modulo B
        1 if dati.get("attivita_commerciale") else 0,
        1 if dati.get("attivita_pubblicita") else 0,
        1 if dati.get("attivita_spettacolo") else 0,
        dati.get("dettagli_attivita"),
        # Pagamento
        cosap_info["cosap"], cosap_osp2, BOLLO_IMPORTO, cosap_info["totale"],
        coeff_microzona, cosap_info["coefficiente_tipo"], cosap_info["tariffa_base"], iuv,
        # Stato
        1 if dati.get("dichiarazioni_ok") else 1,
        1 if dati.get("prescrizioni_accettate") else 0,
    ))

    log_evento(conn, pratica_id, "INVIATA", "Pratica inviata dal richiedente", richiedente_id)
    conn.commit()
    conn.close()

    invia_email_conferma_ricezione(pratica_id)
    return pratica_id, numero, cosap_info

def get_pratica(pratica_id):
    conn = get_conn()
    r = conn.execute("""
        SELECT p.*,
               ri.tipo_soggetto, ri.nome, ri.cognome, ri.ragione_sociale,
               ri.codice_fiscale, ri.partita_iva,
               ri.email as richiedente_email, ri.telefono, ri.pec,
               ri.data_nascita, ri.luogo_nascita,
               ri.residenza_via, ri.residenza_civico, ri.residenza_cap,
               ri.residenza_citta, ri.residenza_provincia,
               ri.tipo_documento, ri.numero_documento,
               ri.sede_via, ri.sede_civico, ri.sede_cap,
               ri.sede_citta, ri.sede_provincia,
               ri.codice_sdi,
               mz.codice as microzona_codice, mz.nome as microzona_nome
        FROM pratiche p
        JOIN richiedenti ri ON ri.id = p.richiedente_id
        LEFT JOIN microzone mz ON mz.id = p.microzona_id
        WHERE p.id=?
    """, (pratica_id,)).fetchone()
    conn.close()
    return dict(r) if r else None

def get_pratiche_zona(zona, stato=None, limit=100, offset=0):
    conn = get_conn()
    q = """
        SELECT p.*, ri.tipo_soggetto, ri.nome, ri.cognome, ri.ragione_sociale,
               ri.email as richiedente_email
        FROM pratiche p
        JOIN richiedenti ri ON ri.id = p.richiedente_id
        WHERE p.zona=?
    """
    params = [zona]
    if stato:
        q += " AND p.stato=?"
        params.append(stato)
    q += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pratiche_richiedente(richiedente_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM pratiche WHERE richiedente_id=? ORDER BY created_at DESC",
        (richiedente_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_allegati(pratica_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM allegati WHERE pratica_id=? ORDER BY created_at",
        (pratica_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_eventi(pratica_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM eventi_pratica WHERE pratica_id=? ORDER BY created_at",
        (pratica_id,)
    ).fetchall()
    conn.close()
    return [dict(r) if isinstance(r, sqlite3.Row) else r for r in rows]

def log_evento(conn, pratica_id, tipo, descrizione, utente_id=None, metadata=None):
    conn.execute(
        "INSERT INTO eventi_pratica (id,pratica_id,tipo,descrizione,utente_id,metadata) VALUES (?,?,?,?,?,?)",
        (gen_id(), pratica_id, tipo, descrizione, utente_id,
         json.dumps(metadata) if metadata else None)
    )

def aggiorna_stato_pratica(pratica_id, nuovo_stato, operatore_id, note=None, motivo_rifiuto=None):
    conn = get_conn()
    now = datetime.datetime.now().isoformat()

    extra_sql = ""
    extra_params = []

    if nuovo_stato == "APPROVATA":
        num_con = gen_numero_concessione(
            conn.execute("SELECT zona FROM pratiche WHERE id=?", (pratica_id,)).fetchone()[0]
        )
        extra_sql = ", numero_concessione=?, data_concessione=?, approved_at=?"
        extra_params = [num_con, now, now]
    elif nuovo_stato == "RIFIUTATA" and motivo_rifiuto:
        extra_sql = ", motivo_rifiuto=?"
        extra_params = [motivo_rifiuto]

    conn.execute(
        f"UPDATE pratiche SET stato=?, operatore_id=?, note_operatore=?, updated_at=? {extra_sql} WHERE id=?",
        [nuovo_stato, operatore_id, note, now] + extra_params + [pratica_id]
    )
    log_evento(conn, pratica_id, nuovo_stato, f"Stato aggiornato a {nuovo_stato}", operatore_id,
               {"note": note, "motivo": motivo_rifiuto})
    conn.commit()
    pratica = conn.execute("SELECT * FROM pratiche WHERE id=?", (pratica_id,)).fetchone()
    conn.close()

    # Email automatiche
    if nuovo_stato == "APPROVATA":
        invia_email_concessione(pratica_id)
    elif nuovo_stato == "RIFIUTATA":
        invia_email_rifiuto(pratica_id)
    elif nuovo_stato == "INTEGRAZIONI":
        invia_email_integrazioni(pratica_id)

    return dict(pratica) if pratica else None

def conferma_pagamento(pratica_id, canale="MOCK"):
    conn = get_conn()
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "UPDATE pratiche SET pagamento_stato='PAGATO', pagamento_data=?, pagamento_canale=?, stato='PAGATA', updated_at=? WHERE id=?",
        (now, canale, now, pratica_id)
    )
    pratica = conn.execute("SELECT zona FROM pratiche WHERE id=?", (pratica_id,)).fetchone()
    log_evento(conn, pratica_id, "PAGATA", f"Pagamento confermato via {canale}")
    conn.commit()
    conn.close()

    invia_email_pagamento(pratica_id)
    invia_notifica_operatori(pratica_id)


def get_kpi_zona(zona):
    conn = get_conn()
    totale = conn.execute("SELECT COUNT(*) FROM pratiche WHERE zona=?", (zona,)).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM pratiche WHERE zona=? AND stato IN ('PAGATA','INVIATA','INTEGRAZIONI')",
        (zona,)
    ).fetchone()[0]
    approvate = conn.execute(
        "SELECT COUNT(*) FROM pratiche WHERE zona=? AND stato='APPROVATA'", (zona,)
    ).fetchone()[0]
    rifiutate = conn.execute(
        "SELECT COUNT(*) FROM pratiche WHERE zona=? AND stato='RIFIUTATA'", (zona,)
    ).fetchone()[0]
    incasso = conn.execute(
        "SELECT COALESCE(SUM(importo_cosap),0) FROM pratiche WHERE zona=? AND pagamento_stato='PAGATO'",
        (zona,)
    ).fetchone()[0]
    conn.close()
    return {
        "totale": totale, "pendenti": pending, "approvate": approvate,
        "rifiutate": rifiutate, "incasso": round(incasso, 2)
    }

def get_kpi_globali():
    conn = get_conn()
    totale = conn.execute("SELECT COUNT(*) FROM pratiche").fetchone()[0]
    approvate = conn.execute("SELECT COUNT(*) FROM pratiche WHERE stato='APPROVATA'").fetchone()[0]
    pendenti = conn.execute("SELECT COUNT(*) FROM pratiche WHERE stato IN ('PAGATA','INVIATA','INTEGRAZIONI')").fetchone()[0]
    incasso = conn.execute("SELECT COALESCE(SUM(importo_cosap),0) FROM pratiche WHERE pagamento_stato='PAGATO'").fetchone()[0]
    per_zona = []
    for z in range(1, 10):
        cnt = conn.execute("SELECT COUNT(*) FROM pratiche WHERE zona=?", (z,)).fetchone()[0]
        pend = conn.execute("SELECT COUNT(*) FROM pratiche WHERE zona=? AND stato IN ('PAGATA','INVIATA','INTEGRAZIONI')", (z,)).fetchone()[0]
        per_zona.append({"zona": z, "totale": cnt, "pendenti": pend})
    conn.close()
    return {"totale": totale, "approvate": approvate, "pendenti": pendenti,
            "incasso": round(incasso, 2), "per_zona": per_zona}


# ─────────────────────────────────────────────────────────────
# EMAIL (log su file in dev)
# ─────────────────────────────────────────────────────────────

def log_email(destinatario, oggetto, corpo):
    os.makedirs(os.path.dirname(EMAIL_LOG_PATH), exist_ok=True)
    with open(EMAIL_LOG_PATH, "a", encoding="utf-8") as f:
        sep = "=" * 70
        f.write(f"\n{sep}\n")
        f.write(f"📧 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"A: {destinatario}\nOGGETTO: {oggetto}\n\n{corpo}\n")

def _get_pratica_email_data(pratica_id):
    p = get_pratica(pratica_id)
    if not p: return None
    zona_info = get_info_zona(p["zona"])
    nome_richiedente = p.get("ragione_sociale") or f"{p.get('nome','')} {p.get('cognome','')}".strip()
    return p, zona_info, nome_richiedente

def invia_email_conferma_ricezione(pratica_id):
    data = _get_pratica_email_data(pratica_id)
    if not data: return
    p, zona_info, nome = data
    oggetto = f"[OSP Milano] Pratica {p['numero_pratica']} ricevuta — {TIPI_OCCUPAZIONE.get(p['tipo_occupazione'], p['tipo_occupazione'])}"
    corpo = f"""Gentile {nome},

La sua domanda di occupazione temporanea di suolo pubblico è stata ricevuta.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RIEPILOGO PRATICA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Numero pratica : {p['numero_pratica']}
• Tipo           : {TIPI_OCCUPAZIONE.get(p['tipo_occupazione'], p['tipo_occupazione'])}
• Indirizzo      : {p['via']} {p['civico']}, Milano
• Periodo        : {p['data_inizio']} → {p['data_fine']} ({p['giorni_effettivi']} giorni)
• Superficie     : {p['superficie_mq']} mq
• Comando        : {zona_info['nome']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAGAMENTO DA EFFETTUARE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Canone COSAP   : €{p['importo_cosap']:.2f}
• Bollo digitale : €{p['importo_bollo']:.2f}
• TOTALE         : €{p['importo_totale']:.2f}
• IUV            : {p['iuv']}

Acceda al portale per effettuare il pagamento:
http://localhost:8888/pratica/{pratica_id}/paga

La concessione sarà emessa dopo la verifica del pagamento.

Per informazioni: {zona_info['email']} — {zona_info['telefono']}

Comune di Milano — Polizia Locale
"""
    log_email(p["richiedente_email"], oggetto, corpo)

def invia_email_pagamento(pratica_id):
    data = _get_pratica_email_data(pratica_id)
    if not data: return
    p, zona_info, nome = data
    oggetto = f"[OSP Milano] ✅ Pagamento confermato — Pratica {p['numero_pratica']}"
    corpo = f"""Gentile {nome},

Il pagamento di €{p['importo_totale']:.2f} per la pratica {p['numero_pratica']} è stato ricevuto.

La sua pratica è ora in revisione presso il {zona_info['nome']}.
La concessione sarà emessa entro la giornata lavorativa.

Per informazioni: {zona_info['email']} — {zona_info['telefono']}

Comune di Milano — Polizia Locale
"""
    log_email(p["richiedente_email"], oggetto, corpo)

def invia_notifica_operatori(pratica_id):
    data = _get_pratica_email_data(pratica_id)
    if not data: return
    p, zona_info, nome = data
    oggetto = f"[OSP PORTAL] 🔔 Nuova pratica pagata — {p['numero_pratica']} — {TIPI_OCCUPAZIONE.get(p['tipo_occupazione'])}"
    corpo = f"""Nuova pratica OSP da istruire per la Zona {p['zona']}:

• N. Pratica   : {p['numero_pratica']}
• Tipo         : {TIPI_OCCUPAZIONE.get(p['tipo_occupazione'])}
• Richiedente  : {nome} — {p['richiedente_email']}
• Indirizzo    : {p['via']} {p['civico']}, Milano
• Periodo      : {p['data_inizio']} → {p['data_fine']} ({p['giorni_effettivi']} giorni)
• Superficie   : {p['superficie_mq']} mq
• Pagamento    : CONFERMATO (€{p['importo_totale']:.2f})

Apri nel portale: http://localhost:8888/operatore/pratiche/{pratica_id}
"""
    log_email(zona_info["email"], oggetto, corpo)

def invia_email_concessione(pratica_id):
    data = _get_pratica_email_data(pratica_id)
    if not data: return
    p, zona_info, nome = data
    oggetto = f"[OSP Milano] ✅ CONCESSIONE RILASCIATA — {p.get('numero_concessione','N/A')}"
    corpo = f"""Gentile {nome},

La sua richiesta di occupazione temporanea di suolo pubblico è stata APPROVATA.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCESSIONE N. {p.get('numero_concessione','N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Pratica      : {p['numero_pratica']}
• Indirizzo    : {p['via']} {p['civico']}, Milano
• Periodo      : {p['data_inizio']} → {p['data_fine']}
• Superficie   : {p['superficie_mq']} mq
• Emessa il    : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}

OBBLIGHI:
• Esporre la concessione in modo visibile durante l'occupazione
• Rispettare superficie e orari autorizzati
• Ripristinare lo stato dei luoghi al termine

Scarica la concessione: http://localhost:8888/pratica/{pratica_id}/concessione

Per informazioni: {zona_info['email']}

Comune di Milano — Polizia Locale
"""
    log_email(p["richiedente_email"], oggetto, corpo)

def invia_email_rifiuto(pratica_id):
    data = _get_pratica_email_data(pratica_id)
    if not data: return
    p, zona_info, nome = data
    oggetto = f"[OSP Milano] Pratica {p['numero_pratica']} — Domanda non accolta"
    corpo = f"""Gentile {nome},

La sua richiesta di occupazione temporanea di suolo pubblico NON è stata accolta.

Motivazione: {p.get('motivo_rifiuto') or 'Non specificata'}

Il canone COSAP versato sarà rimborsato entro 30 giorni lavorativi.
Il bollo (€16,00) non è rimborsabile.

Per contestare: ricorso TAR Lombardia entro 60 giorni.
Per assistenza: {zona_info['email']}

Comune di Milano — Polizia Locale
"""
    log_email(p["richiedente_email"], oggetto, corpo)

def invia_email_integrazioni(pratica_id):
    data = _get_pratica_email_data(pratica_id)
    if not data: return
    p, zona_info, nome = data
    oggetto = f"[OSP Milano] Pratica {p['numero_pratica']} — Documentazione da integrare"
    corpo = f"""Gentile {nome},

La sua pratica richiede documentazione aggiuntiva.

Note dell'operatore: {p.get('note_operatore') or 'Vedere portale'}

Acceda al portale per caricare i documenti:
http://localhost:8888/pratica/{pratica_id}

Scadenza integrazioni: {(datetime.datetime.now() + datetime.timedelta(days=15)).strftime('%d/%m/%Y')}

Per informazioni: {zona_info['email']}

Comune di Milano — Polizia Locale
"""
    log_email(p["richiedente_email"], oggetto, corpo)


# ─────────────────────────────────────────────────────────────
# PDF CONCESSIONE
# ─────────────────────────────────────────────────────────────

import sqlite3

def genera_pdf_concessione(pratica_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    try:
        import qrcode
        from io import BytesIO
        from reportlab.platypus import Image as RLImage
        HAS_QR = True
    except ImportError:
        HAS_QR = False

    p = get_pratica(pratica_id)
    if not p: return None

    zona_info = get_info_zona(p["zona"])
    nome_richiedente = p.get("ragione_sociale") or f"{p.get('nome','')} {p.get('cognome','')}".strip()

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "uploads",
        f"concessione_{p['numero_pratica'].replace('-','_')}.pdf"
    )

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)

    styles = getSampleStyleSheet()
    BLU_MILANO = colors.HexColor("#003F8A")
    GRIGIO = colors.HexColor("#555555")

    stile_titolo = ParagraphStyle("Titolo", parent=styles["Normal"],
        fontSize=18, textColor=BLU_MILANO, spaceAfter=4,
        fontName="Helvetica-Bold", alignment=TA_CENTER)
    stile_sottotitolo = ParagraphStyle("Sottotitolo", parent=styles["Normal"],
        fontSize=11, textColor=GRIGIO, spaceAfter=2, alignment=TA_CENTER)
    stile_h2 = ParagraphStyle("H2", parent=styles["Normal"],
        fontSize=11, textColor=BLU_MILANO, spaceBefore=10, spaceAfter=4,
        fontName="Helvetica-Bold")
    stile_corpo = ParagraphStyle("Corpo", parent=styles["Normal"],
        fontSize=9, spaceAfter=3, leading=14)
    stile_nota = ParagraphStyle("Nota", parent=styles["Normal"],
        fontSize=8, textColor=GRIGIO, spaceAfter=2, fontName="Helvetica-Oblique")

    story = []

    # Header istituzionale
    story.append(Paragraph("COMUNE DI MILANO", stile_titolo))
    story.append(Paragraph("POLIZIA LOCALE — COMANDO DECENTRATO", stile_sottotitolo))
    story.append(Paragraph(zona_info["nome"].upper(), stile_sottotitolo))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=BLU_MILANO))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("CONCESSIONE DI OCCUPAZIONE TEMPORANEA DI SUOLO PUBBLICO", stile_titolo))
    story.append(Paragraph(f"N. {p.get('numero_concessione', 'N/A')}", ParagraphStyle(
        "NumCon", parent=styles["Normal"], fontSize=14, textColor=BLU_MILANO,
        fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.4*cm))

    # Dati pratica
    story.append(Paragraph("DATI PRATICA", stile_h2))
    dati_pratica = [
        ["Numero Pratica", p["numero_pratica"]],
        ["Data Emissione", datetime.datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Tipo Occupazione", TIPI_OCCUPAZIONE.get(p["tipo_occupazione"], p["tipo_occupazione"])],
        ["Modulo", f"Modulo {p['tipo_modulo']}"],
    ]
    t = Table(dati_pratica, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF2FA")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    # Concessionario
    story.append(Paragraph("CONCESSIONARIO", stile_h2))
    dati_con = [
        ["Ragione Sociale / Nome", nome_richiedente],
        ["Tipo Soggetto", "Persona Giuridica" if p.get("tipo_soggetto")=="PERSONA_GIURIDICA" else "Persona Fisica"],
        ["CF / P.IVA", p.get("codice_fiscale") or p.get("partita_iva") or "—"],
        ["Email", p.get("richiedente_email", "—")],
        ["Telefono", p.get("telefono", "—")],
    ]
    t2 = Table(dati_con, colWidths=[5*cm, 12*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF2FA")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.3*cm))

    # Dati occupazione
    story.append(Paragraph("DATI OCCUPAZIONE", stile_h2))
    dati_occ = [
        ["Indirizzo", f"{p['via']} {p['civico']}, Milano"],
        ["Superficie", f"{p['superficie_mq']} mq"],
        ["Tipo Superficie", p.get("tipo_superficie", "—").replace("_", " ").title()],
        ["Periodo", f"Dal {p['data_inizio']} al {p['data_fine']} ({p['giorni_effettivi']} giorni)"],
        ["Orario", f"{p.get('orario_inizio','—')} – {p.get('orario_fine','—')}"],
        ["Periodicità", p.get("periodicita", "CONTINUATIVA").title()],
        ["Descrizione", p.get("descrizione", "—")],
    ]
    t3 = Table(dati_occ, colWidths=[5*cm, 12*cm])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF2FA")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("PADDING", (0,0), (-1,-1), 6),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(t3)
    story.append(Spacer(1, 0.3*cm))

    # Canone
    story.append(Paragraph("CANONE PATRIMONIALE COSAP", stile_h2))
    dati_pag = [
        ["Canone COSAP", f"€ {p.get('importo_cosap',0):.2f}"],
        ["Bollo Digitale", f"€ {p.get('importo_bollo',16):.2f}"],
        ["TOTALE VERSATO", f"€ {p.get('importo_totale',0):.2f}"],
        ["Canale Pagamento", p.get("pagamento_canale", "PagoPA")],
        ["Data Pagamento", p.get("pagamento_data", "—")[:10] if p.get("pagamento_data") else "—"],
        ["IUV", p.get("iuv", "—")],
    ]
    t4 = Table(dati_pag, colWidths=[5*cm, 12*cm])
    t4.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF2FA")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (0,2), (0,2), "Helvetica-Bold"),
        ("BACKGROUND", (0,2), (-1,2), colors.HexColor("#D4EDDA")),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t4)
    story.append(Spacer(1, 0.4*cm))

    # Obblighi
    story.append(Paragraph("OBBLIGHI DEL CONCESSIONARIO", stile_h2))
    obblighi = [
        "Esporre la presente concessione in modo visibile durante tutta la durata dell'occupazione.",
        "Rispettare scrupolosamente i limiti di superficie e gli orari indicati nella concessione.",
        "Garantire la sicurezza dei pedoni e dei veicoli per tutta la durata dell'occupazione.",
        "Ripristinare lo stato originario dei luoghi al termine dell'occupazione autorizzata.",
        "Comunicare immediatamente al Comando Decentrato qualsiasi variazione rispetto al piano approvato.",
        "In caso di mancato rispetto delle condizioni, la concessione può essere revocata con effetto immediato.",
    ]
    for i, ob in enumerate(obblighi, 1):
        story.append(Paragraph(f"{i}. {ob}", stile_corpo))
    story.append(Spacer(1, 0.4*cm))

    # QR + firma
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.3*cm))

    qr_url = f"http://localhost:8888/verifica/{p['numero_pratica']}"
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=3, border=2)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        qr_rl = RLImage(buf, width=2.5*cm, height=2.5*cm)
    except Exception:
        qr_rl = None

    firma_data = [
        [
            Paragraph(f"Concessione emessa digitalmente il\n{datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n{zona_info['nome']}\n{zona_info['indirizzo']}\nTel: {zona_info['telefono']}", stile_nota),
            qr_rl or Paragraph("QR verifica", stile_nota),
            Paragraph(f"_____________________________\nFirma e Timbro\nResponsabile Ufficio Permessi\n{zona_info['nome']}", stile_nota),
        ]
    ]
    t_firma = Table(firma_data, colWidths=[7*cm, 3*cm, 7*cm])
    t_firma.setStyle(TableStyle([
        ("ALIGN", (1,0), (1,0), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))
    story.append(t_firma)
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Documento generato automaticamente dal Sistema Informativo OSP — Comune di Milano | "
        f"Verifica autenticità: {qr_url}",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                       textColor=GRIGIO, alignment=TA_CENTER)
    ))

    doc.build(story)

    # Aggiorna percorso nel DB
    conn = get_conn()
    conn.execute("UPDATE pratiche SET concessione_path=? WHERE id=?", (output_path, pratica_id))
    conn.commit()
    conn.close()

    return output_path
