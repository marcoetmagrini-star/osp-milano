"""
OSP Milano - Database SQLite
Schema aggiornato con tutti i campi ufficiali del Modulo A
"""
import sqlite3
import os
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    -- ─────────────────────────────────────────────────
    -- UTENTI (operatori e admin)
    -- ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS utenti (
        id          TEXT PRIMARY KEY,
        tipo        TEXT NOT NULL CHECK(tipo IN ('RICHIEDENTE','OPERATORE','ADMIN')),
        zona        INTEGER,
        username    TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nome        TEXT NOT NULL,
        cognome     TEXT NOT NULL,
        email       TEXT NOT NULL,
        attivo      INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT (datetime('now')),
        last_login  TEXT
    );

    -- ─────────────────────────────────────────────────
    -- RICHIEDENTI (persone fisiche e giuridiche)
    -- ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS richiedenti (
        id                    TEXT PRIMARY KEY,
        utente_id             TEXT REFERENCES utenti(id),
        tipo_soggetto         TEXT NOT NULL CHECK(tipo_soggetto IN ('PERSONA_FISICA','PERSONA_GIURIDICA')),

        -- Persona fisica
        nome                  TEXT,
        cognome               TEXT,
        data_nascita          TEXT,
        luogo_nascita         TEXT,
        codice_fiscale        TEXT,

        -- Residenza (indirizzo completo separato)
        residenza_via         TEXT,
        residenza_civico      TEXT,
        residenza_cap         TEXT,
        residenza_citta       TEXT,
        residenza_provincia   TEXT,

        -- Documento identità
        tipo_documento        TEXT,  -- CI, Passaporto, Patente
        numero_documento      TEXT,

        -- Persona giuridica
        ragione_sociale       TEXT,
        partita_iva           TEXT,
        codice_sdi            TEXT,   -- per fatturazione elettronica
        forma_giuridica       TEXT,
        legale_rappresentante TEXT,

        -- Sede legale (indirizzo completo separato)
        sede_via              TEXT,
        sede_civico           TEXT,
        sede_cap              TEXT,
        sede_citta            TEXT,
        sede_provincia        TEXT,

        -- Contatti
        telefono              TEXT NOT NULL,
        email                 TEXT NOT NULL,
        pec                   TEXT,

        created_at            TEXT DEFAULT (datetime('now'))
    );

    -- ─────────────────────────────────────────────────
    -- MICROZONE OMI (coefficienti COSAP)
    -- ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS microzone (
        id              TEXT PRIMARY KEY,
        codice          TEXT UNIQUE NOT NULL,  -- es. B02, D01
        nome            TEXT NOT NULL,
        zona            INTEGER NOT NULL,      -- 1-9
        coefficiente    REAL NOT NULL DEFAULT 1.0,
        categoria_strada TEXT NOT NULL DEFAULT 'B',
        created_at      TEXT DEFAULT (datetime('now'))
    );

    -- ─────────────────────────────────────────────────
    -- PRATICHE OSP (schema completo)
    -- ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS pratiche (
        id                TEXT PRIMARY KEY,
        numero_pratica    TEXT UNIQUE NOT NULL,
        richiedente_id    TEXT NOT NULL REFERENCES richiedenti(id),
        zona              INTEGER NOT NULL,
        microzona_id      TEXT REFERENCES microzone(id),
        tipo_modulo       TEXT NOT NULL CHECK(tipo_modulo IN ('A','B')),
        tipo_occupazione  TEXT NOT NULL,

        -- ── LOCALIZZAZIONE OSP ──
        via               TEXT NOT NULL,
        civico            TEXT,
        cap               TEXT NOT NULL,
        riferimenti       TEXT,      -- palo luce, riferimenti utili per cartelli
        nil               TEXT,
        lat               REAL,
        lng               REAL,

        -- Superficie
        tipo_superficie   TEXT NOT NULL,  -- MARCIAPIEDE, CARREGGIATA, AREA_VERDE, STALLI
        rientrante_stalli INTEGER DEFAULT 0,   -- 1 se rientrante negli stalli
        eccedente_stalli  INTEGER DEFAULT 0,   -- 1 se eccedente gli stalli
        eccedente_dove    TEXT,                -- dove eccede (MARCIAPIEDE/CARREGGIATA/AREA_VERDE)
        superficie_mq     REAL NOT NULL,
        metri_x           REAL,               -- larghezza in metri
        metri_y           REAL,               -- lunghezza in metri
        categoria_strada  TEXT NOT NULL CHECK(categoria_strada IN ('A','B','C','D')),

        -- ── PERIODO (max 14 giorni) ──
        data_inizio       TEXT NOT NULL,
        data_fine         TEXT NOT NULL,
        ora_inizio        TEXT,               -- HH:MM
        ora_fine          TEXT,               -- HH:MM
        giorni_effettivi  INTEGER NOT NULL,

        -- ── DESCRIZIONE ──
        scopo             TEXT NOT NULL,      -- descrizione attività (max 40 char per PDF)
        descrizione       TEXT,              -- descrizione estesa
        motivazione       TEXT,

        -- ── MEZZI OPERATIVI SPECIALI ──
        ha_mezzi_speciali     INTEGER DEFAULT 0,
        mezzo_autogru         INTEGER DEFAULT 0,
        mezzo_autoscala       INTEGER DEFAULT 0,
        mezzo_autoelevatore   INTEGER DEFAULT 0,
        mezzo_piattaforma     INTEGER DEFAULT 0,
        mezzo_altro           INTEGER DEFAULT 0,
        mezzo_altro_desc      TEXT,
        mezzo_targa           TEXT,
        mezzo_marca           TEXT,
        mezzo_modello         TEXT,
        mezzo_proprietario    TEXT,

        -- ── ACCESSI SPECIALI (ZTL/etc) ──
        ha_accesso_limitato       INTEGER DEFAULT 0,
        accesso_corsia_mezzi      INTEGER DEFAULT 0,
        accesso_ztl               INTEGER DEFAULT 0,
        accesso_area_pedonale     INTEGER DEFAULT 0,
        accesso_altro             INTEGER DEFAULT 0,
        accesso_altro_desc        TEXT,
        accesso_localita          TEXT,
        accesso_veicolo_marca     TEXT,
        accesso_veicolo_modello   TEXT,
        accesso_veicolo_targa     TEXT,
        accesso_veicolo_proprietario TEXT,

        -- ── FASE SUCCESSIVA (OSP2) ──
        ha_fase_successiva        INTEGER DEFAULT 0,
        osp2_via                  TEXT,
        osp2_civico               TEXT,
        osp2_riferimenti          TEXT,
        osp2_superficie_mq        REAL,
        osp2_metri_x              REAL,
        osp2_metri_y              REAL,
        osp2_tipo_superficie      TEXT,
        osp2_rientrante_stalli    INTEGER DEFAULT 0,
        osp2_eccedente_stalli     INTEGER DEFAULT 0,
        osp2_eccedente_dove       TEXT,
        osp2_data_inizio          TEXT,
        osp2_data_fine            TEXT,
        osp2_ora_inizio           TEXT,
        osp2_ora_fine             TEXT,
        osp2_scopo                TEXT,
        osp2_ha_mezzi_speciali    INTEGER DEFAULT 0,

        -- ── MODULO B (eventi/attività commerciali) ──
        attivita_commerciale  INTEGER DEFAULT 0,
        attivita_pubblicita   INTEGER DEFAULT 0,
        attivita_spettacolo   INTEGER DEFAULT 0,
        dettagli_attivita     TEXT,

        -- ── STATO PRATICA ──
        stato             TEXT NOT NULL DEFAULT 'BOZZA',
        note_operatore    TEXT,
        motivo_rifiuto    TEXT,
        operatore_id      TEXT REFERENCES utenti(id),

        -- ── PAGAMENTO ──
        importo_cosap          REAL,
        importo_cosap_osp2     REAL,
        importo_bollo          REAL DEFAULT 16.00,
        importo_totale         REAL,
        coefficiente_microzona REAL,
        coefficiente_tipo      REAL,
        tariffa_base           REAL,
        iuv                    TEXT UNIQUE,
        pagamento_stato        TEXT DEFAULT 'NON_PAGATO',
        pagamento_data         TEXT,
        pagamento_canale       TEXT,

        -- ── CONCESSIONE ──
        numero_concessione TEXT UNIQUE,
        concessione_path   TEXT,
        data_concessione   TEXT,

        -- ── ALLEGATI & DICHIARAZIONI ──
        dichiarazioni_ok          INTEGER DEFAULT 0,
        prescrizioni_accettate    INTEGER DEFAULT 0,

        -- ── TIMESTAMPS ──
        created_at        TEXT DEFAULT (datetime('now')),
        updated_at        TEXT DEFAULT (datetime('now')),
        submitted_at      TEXT,
        approved_at       TEXT
    );

    CREATE TABLE IF NOT EXISTS allegati (
        id          TEXT PRIMARY KEY,
        pratica_id  TEXT NOT NULL REFERENCES pratiche(id),
        tipo        TEXT NOT NULL,  -- DOC_ID, VISURA, ALTRO
        nome_file   TEXT NOT NULL,
        percorso    TEXT NOT NULL,
        mime_type   TEXT,
        dimensione  INTEGER,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS eventi_pratica (
        id          TEXT PRIMARY KEY,
        pratica_id  TEXT NOT NULL REFERENCES pratiche(id),
        tipo        TEXT NOT NULL,
        descrizione TEXT NOT NULL,
        utente_id   TEXT,
        metadata    TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sessioni (
        token       TEXT PRIMARY KEY,
        utente_id   TEXT NOT NULL REFERENCES utenti(id),
        created_at  TEXT DEFAULT (datetime('now')),
        expires_at  TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pratiche_zona ON pratiche(zona);
    CREATE INDEX IF NOT EXISTS idx_pratiche_stato ON pratiche(stato);
    CREATE INDEX IF NOT EXISTS idx_pratiche_richiedente ON pratiche(richiedente_id);
    CREATE INDEX IF NOT EXISTS idx_pratiche_microzona ON pratiche(microzona_id);
    CREATE INDEX IF NOT EXISTS idx_eventi_pratica ON eventi_pratica(pratica_id);
    CREATE INDEX IF NOT EXISTS idx_sessioni_token ON sessioni(token);
    CREATE INDEX IF NOT EXISTS idx_microzone_zona ON microzone(zona);
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Inizializzato: {DB_PATH}")
