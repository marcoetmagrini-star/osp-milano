"""
OSP Milano — Server principale Tornado
Portale digitale per Occupazione Temporanea Suolo Pubblico (max 14 giorni)
"""
import tornado.ioloop
import tornado.web
import tornado.escape
import os, json, datetime, uuid, re, hashlib, mimetypes
from config import (PORT, DEBUG, UPLOAD_DIR, COMANDI_DECENTRATI,
                    TIPI_OCCUPAZIONE, TIPI_MODULO_B, STATI_PRATICA,
                    MAX_GIORNI_OSP, SECRET_KEY, MICROZONE_OMI)
from database import init_db, get_conn
from services import (
    login, get_utente_da_token, elimina_sessione,
    crea_pratica, get_pratica, get_pratiche_zona, get_pratiche_richiedente,
    get_allegati, get_eventi, aggiorna_stato_pratica, conferma_pagamento,
    calcola_cosap, calcola_giorni, rileva_zona_da_cap,
    get_categoria_strada_da_zona, get_info_zona, get_coeff_microzona,
    get_kpi_zona, get_kpi_globali, genera_pdf_concessione,
    gen_id, hash_password, log_email,
    invia_email_concessione
)


# ─────────────────────────────────────────────────────────────
# BASE HANDLER
# ─────────────────────────────────────────────────────────────

class BaseHandler(tornado.web.RequestHandler):
    def prepare(self):
        self.set_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.set_header("Pragma", "no-cache")

    def get_current_user(self):
        token = self.get_cookie("session_token")
        return get_utente_da_token(token)

    def render_error(self, code, msg):
        self.set_status(code)
        self.render("error.html", code=code, msg=msg, utente=self.current_user)

    def json_out(self, data, status=200):
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(data, ensure_ascii=False, default=str))

    def require_login(self):
        if not self.current_user:
            self.redirect("/login?next=" + tornado.escape.url_escape(self.request.uri))
            return False
        return True

    def require_operatore(self):
        u = self.current_user
        if not u or u["tipo"] not in ("OPERATORE", "ADMIN"):
            self.redirect("/login")
            return False
        return True

    def get_richiedente(self):
        u = self.current_user
        if not u: return None
        conn = get_conn()
        r = conn.execute("SELECT * FROM richiedenti WHERE utente_id=?", (u["id"],)).fetchone()
        conn.close()
        return dict(r) if r else None

    @property
    def db(self):
        return get_conn()


# ─────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────

class LoginHandler(BaseHandler):
    def get(self):
        if self.current_user:
            u = self.current_user
            if u["tipo"] in ("OPERATORE", "ADMIN"):
                zona = u.get("zona") or 0
                self.redirect(f"/operatore/zona/{zona}" if zona else "/operatore/centrale")
            else:
                self.redirect("/portale")
            return
        self.render("login.html", errore=None, utente=None)

    def post(self):
        username = self.get_argument("username", "").strip()
        password = self.get_argument("password", "").strip()
        utente, token_or_err = login(username, password)
        if not utente:
            self.render("login.html", errore=token_or_err, utente=None)
            return
        self.set_cookie("session_token", token_or_err, httponly=True, path="/")
        nxt = self.get_argument("next", "")
        if utente["tipo"] in ("OPERATORE", "ADMIN"):
            zona = utente.get("zona") or 0
            self.redirect(f"/operatore/zona/{zona}" if zona else "/operatore/centrale")
        else:
            self.redirect(nxt or "/portale")

class LogoutHandler(BaseHandler):
    def get(self):
        token = self.get_cookie("session_token")
        if token:
            elimina_sessione(token)
        self.clear_cookie("session_token")
        self.redirect("/")


# ─────────────────────────────────────────────────────────────
# PAGINE PUBBLICHE
# ─────────────────────────────────────────────────────────────

class HomeHandler(BaseHandler):
    def get(self):
        self.render("home.html", utente=self.current_user,
                    comandi=COMANDI_DECENTRATI)

class VerificaConcessioneHandler(BaseHandler):
    def get(self, numero_pratica):
        conn = get_conn()
        p = conn.execute(
            "SELECT * FROM pratiche WHERE numero_pratica=?", (numero_pratica,)
        ).fetchone()
        conn.close()
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        if not p:
            self.render("verifica.html", pratica=None, utente=self.current_user,
                        zona_info={}, tipi=TIPI_OCCUPAZIONE, import_datetime=now_str)
            return
        self.render("verifica.html", pratica=dict(p),
                    zona_info=get_info_zona(p["zona"]),
                    tipi=TIPI_OCCUPAZIONE, utente=self.current_user,
                    import_datetime=now_str)


# ─────────────────────────────────────────────────────────────
# PORTALE RICHIEDENTE
# ─────────────────────────────────────────────────────────────

class PortaleHandler(BaseHandler):
    def get(self):
        if not self.require_login(): return
        u = self.current_user
        if u["tipo"] in ("OPERATORE", "ADMIN"):
            self.redirect("/operatore/centrale")
            return
        rich = self.get_richiedente()
        pratiche = get_pratiche_richiedente(rich["id"]) if rich else []
        self.render("portale_richiedente.html", utente=u, richiedente=rich,
                    pratiche=pratiche, stati=STATI_PRATICA, tipi=TIPI_OCCUPAZIONE)

class NuovaPraticaHandler(BaseHandler):
    def _get_microzone(self):
        conn = get_conn()
        rows = conn.execute("SELECT * FROM microzone ORDER BY zona, codice").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get(self):
        if not self.require_login(): return
        u = self.current_user
        rich = self.get_richiedente()
        microzone = self._get_microzone()
        oggi = datetime.date.today().isoformat()
        self.render("nuova_pratica.html",
                    utente=u, richiedente=rich,
                    tipi_occupazione=TIPI_OCCUPAZIONE,
                    comandi=COMANDI_DECENTRATI,
                    microzone=microzone,
                    max_giorni=MAX_GIORNI_OSP,
                    oggi=oggi,
                    errori=None, dati_form={})

    def post(self):
        if not self.require_login(): return
        u = self.current_user
        errori = []

        def ga(name, default=""):
            return self.get_argument(name, default).strip() if isinstance(self.get_argument(name, default), str) else self.get_argument(name, default)

        # ── Dati richiedente ──
        rich = self.get_richiedente()
        if not rich:
            tipo_soggetto = ga("tipo_soggetto")
            if not tipo_soggetto:
                errori.append("Seleziona tipo soggetto")
            if not ga("email"):
                errori.append("Email obbligatoria")
            if not ga("telefono"):
                errori.append("Telefono obbligatorio")
            if not ga("codice_fiscale"):
                errori.append("Codice Fiscale obbligatorio")
            if not ga("residenza_via"):
                errori.append("Indirizzo di residenza obbligatorio")
            if not ga("residenza_cap"):
                errori.append("CAP residenza obbligatorio")

            if not errori:
                rich_id = gen_id()
                conn = get_conn()
                conn.execute("""
                    INSERT INTO richiedenti
                    (id, utente_id, tipo_soggetto,
                     nome, cognome, data_nascita, luogo_nascita,
                     codice_fiscale, ragione_sociale, partita_iva,
                     tipo_documento, numero_documento,
                     residenza_via, residenza_civico, residenza_cap,
                     residenza_citta, residenza_provincia,
                     sede_via, sede_civico, sede_cap, sede_citta, sede_provincia,
                     codice_sdi, email, pec, telefono)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    rich_id, u["id"], tipo_soggetto,
                    ga("nome"), ga("cognome"), ga("data_nascita") or None, ga("luogo_nascita") or None,
                    ga("codice_fiscale").upper(), ga("ragione_sociale") or None, ga("partita_iva") or None,
                    ga("tipo_documento") or None, ga("numero_documento").upper() or None,
                    ga("residenza_via"), ga("residenza_civico") or None, ga("residenza_cap"),
                    ga("residenza_citta") or "Milano", ga("residenza_provincia") or "MI",
                    ga("sede_via") or None, ga("sede_civico") or None,
                    ga("sede_cap") or None, ga("sede_citta") or None, ga("sede_provincia") or None,
                    ga("codice_sdi").upper() or None,
                    ga("email"), ga("pec") or None, ga("telefono"),
                ))
                conn.commit()
                conn.close()
                rich = {"id": rich_id}

        if not rich:
            microzone = self._get_microzone()
            oggi = datetime.date.today().isoformat()
            self.render("nuova_pratica.html",
                        utente=u, richiedente=None,
                        tipi_occupazione=TIPI_OCCUPAZIONE, comandi=COMANDI_DECENTRATI,
                        microzone=microzone, max_giorni=MAX_GIORNI_OSP,
                        oggi=oggi, errori=errori, dati_form=self._get_form_data())
            return

        # ── Validazione campi OSP ──
        tipo_occ = ga("tipo_occupazione")
        via = ga("via")
        cap = ga("cap")
        riferimenti = ga("riferimenti")
        microzona_id = ga("microzona_id") or None

        # Tipo superficie dai checkbox
        tipi_sup = []
        if self.get_argument("tipo_sup_marciapiede", ""): tipi_sup.append("MARCIAPIEDE")
        if self.get_argument("tipo_sup_carreggiata", ""): tipi_sup.append("CARREGGIATA")
        if self.get_argument("tipo_sup_stalli", ""):      tipi_sup.append("STALLI")
        if self.get_argument("tipo_sup_verde", ""):       tipi_sup.append("AREA_VERDE")
        tipo_superficie = tipi_sup[0] if tipi_sup else ga("tipo_superficie") or "MARCIAPIEDE"

        superficie_raw = ga("superficie_mq")
        data_inizio = ga("data_inizio")
        data_fine = ga("data_fine")
        ora_inizio = ga("ora_inizio")
        ora_fine = ga("ora_fine")
        scopo = ga("scopo")[:40]

        if not tipo_occ:      errori.append("Tipo occupazione obbligatorio")
        if not via:           errori.append("Via/Piazza obbligatoria")
        if not cap:           errori.append("CAP obbligatorio")
        if not riferimenti:   errori.append("Riferimenti localizzazione obbligatori")
        if not microzona_id:  errori.append("Microzona OMI obbligatoria per il calcolo COSAP")
        if not scopo:         errori.append("Oggetto dell'occupazione obbligatorio")

        superficie = None
        if not superficie_raw:
            errori.append("Superficie obbligatoria")
        else:
            try:
                superficie = float(superficie_raw)
                if superficie <= 0: errori.append("Superficie deve essere > 0")
            except ValueError:
                errori.append("Superficie non valida")

        if not data_inizio: errori.append("Data inizio obbligatoria")
        if not data_fine:   errori.append("Data fine obbligatoria")

        if data_inizio and data_fine and not errori:
            try:
                d1 = datetime.date.fromisoformat(data_inizio)
                d2 = datetime.date.fromisoformat(data_fine)
                oggi_d = datetime.date.today()
                if d1 < oggi_d:
                    errori.append("La data di inizio non può essere nel passato")
                if d2 < d1:
                    errori.append("La data di fine non può precedere quella di inizio")
                else:
                    giorni = (d2 - d1).days + 1
                    if giorni > MAX_GIORNI_OSP:
                        errori.append(
                            f"Durata massima OSP temporanea: {MAX_GIORNI_OSP} giorni. "
                            f"Hai selezionato {giorni} giorni."
                        )
            except ValueError:
                errori.append("Date non valide")

        if not self.get_argument("dichiarazioni_ok", ""):
            errori.append("Devi accettare le dichiarazioni per procedere")
        if not self.get_argument("prescrizioni_accettate", ""):
            errori.append("Devi accettare le prescrizioni standard OSP")

        if errori:
            microzone = self._get_microzone()
            oggi = datetime.date.today().isoformat()
            self.render("nuova_pratica.html",
                        utente=u, richiedente=rich,
                        tipi_occupazione=TIPI_OCCUPAZIONE, comandi=COMANDI_DECENTRATI,
                        microzone=microzone, max_giorni=MAX_GIORNI_OSP,
                        oggi=oggi, errori=errori, dati_form=self._get_form_data())
            return

        # ── Determina zona dal CAP (o dalla microzona) ──
        zona, _ = rileva_zona_da_cap(cap)

        # ── Raccolta completa di tutti i campi ──
        dati = {
            # Tipo
            "tipo_occupazione": tipo_occ,
            # Localizzazione
            "via": via,
            "civico": ga("civico") or None,
            "cap": cap,
            "nil": ga("nil") or None,
            "riferimenti": riferimenti,
            "microzona_id": microzona_id,
            "lat": None, "lng": None,
            # Superficie
            "tipo_superficie": tipo_superficie,
            "superficie_mq": superficie,
            "metri_x": float(ga("metri_x")) if ga("metri_x") else None,
            "metri_y": float(ga("metri_y")) if ga("metri_y") else None,
            "rientrante_stalli": bool(self.get_argument("rientrante_stalli", "")),
            "eccedente_stalli": bool(self.get_argument("eccedente_stalli", "")),
            "eccedente_dove": ga("eccedente_dove") or None,
            # Periodo
            "data_inizio": data_inizio,
            "data_fine": data_fine,
            "ora_inizio": ora_inizio or "07:00",
            "ora_fine": ora_fine or "19:00",
            # Descrizione
            "scopo": scopo,
            "descrizione": ga("descrizione") or None,
            # Mezzi speciali
            "ha_mezzi_speciali": bool(self.get_argument("ha_mezzi_speciali", "")),
            "mezzo_autogru": bool(self.get_argument("mezzo_autogru", "")),
            "mezzo_autoscala": bool(self.get_argument("mezzo_autoscala", "")),
            "mezzo_autoelevatore": bool(self.get_argument("mezzo_autoelevatore", "")),
            "mezzo_piattaforma": bool(self.get_argument("mezzo_piattaforma", "")),
            "mezzo_altro": bool(self.get_argument("mezzo_altro", "")),
            "mezzo_altro_desc": ga("mezzo_altro_desc") or None,
            "mezzo_targa": ga("mezzo_targa").upper() or None,
            "mezzo_marca": ga("mezzo_marca") or None,
            "mezzo_modello": ga("mezzo_modello") or None,
            "mezzo_proprietario": ga("mezzo_proprietario") or None,
            # Accessi limitati
            "ha_accesso_limitato": bool(self.get_argument("ha_accesso_limitato", "")),
            "accesso_corsia_mezzi": bool(self.get_argument("accesso_corsia_mezzi", "")),
            "accesso_ztl": bool(self.get_argument("accesso_ztl", "")),
            "accesso_area_pedonale": bool(self.get_argument("accesso_area_pedonale", "")),
            "accesso_altro": bool(self.get_argument("accesso_altro", "")),
            "accesso_altro_desc": ga("accesso_altro_desc") or None,
            "accesso_localita": ga("accesso_localita") or None,
            "accesso_veicolo_marca": ga("accesso_veicolo_marca") or None,
            "accesso_veicolo_modello": ga("accesso_veicolo_modello") or None,
            "accesso_veicolo_targa": ga("accesso_veicolo_targa").upper() or None,
            "accesso_veicolo_proprietario": ga("accesso_veicolo_proprietario") or None,
            # Fase 2
            "ha_fase_successiva": bool(self.get_argument("ha_fase_successiva", "")),
            "osp2_via": ga("osp2_via") or None,
            "osp2_civico": ga("osp2_civico") or None,
            "osp2_riferimenti": ga("osp2_riferimenti") or None,
            "osp2_superficie_mq": float(ga("osp2_superficie_mq")) if ga("osp2_superficie_mq") else None,
            "osp2_metri_x": float(ga("osp2_metri_x")) if ga("osp2_metri_x") else None,
            "osp2_metri_y": float(ga("osp2_metri_y")) if ga("osp2_metri_y") else None,
            "osp2_tipo_superficie": ga("osp2_tipo_superficie") or None,
            "osp2_rientrante_stalli": bool(self.get_argument("osp2_rientrante_stalli", "")),
            "osp2_eccedente_stalli": bool(self.get_argument("osp2_eccedente_stalli", "")),
            "osp2_eccedente_dove": ga("osp2_eccedente_dove") or None,
            "osp2_data_inizio": ga("osp2_data_inizio") or None,
            "osp2_data_fine": ga("osp2_data_fine") or None,
            "osp2_ora_inizio": ga("osp2_ora_inizio") or None,
            "osp2_ora_fine": ga("osp2_ora_fine") or None,
            "osp2_scopo": ga("osp2_scopo")[:40] if ga("osp2_scopo") else None,
            "osp2_ha_mezzi_speciali": bool(self.get_argument("osp2_ha_mezzi_speciali", "")),
            # Modulo B
            "attivita_commerciale": bool(self.get_argument("attivita_commerciale", "")),
            "attivita_pubblicita": bool(self.get_argument("attivita_pubblicita", "")),
            "attivita_spettacolo": bool(self.get_argument("attivita_spettacolo", "")),
            "dettagli_attivita": ga("dettagli_attivita") or None,
            # Consensi
            "dichiarazioni_ok": True,
            "prescrizioni_accettate": bool(self.get_argument("prescrizioni_accettate", "")),
        }

        pratica_id, numero, cosap_info = crea_pratica(rich["id"], zona, dati)

        # Gestione allegati
        for field in ["allegato_planimetria", "allegato_documento", "allegato_extra"]:
            for finfo in self.request.files.get(field, []):
                if finfo["filename"] and finfo["body"]:
                    self._salva_allegato(pratica_id, finfo, field)

        self.redirect(f"/pratica/{pratica_id}/riepilogo")

    def _salva_allegato(self, pratica_id, finfo, tipo):
        try:
            import os
            ext = os.path.splitext(finfo["filename"])[1].lower()
            fname = gen_id() + ext
            fpath = os.path.join(UPLOAD_DIR, pratica_id, fname)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "wb") as f:
                f.write(finfo["body"])
            conn = get_conn()
            conn.execute(
                "INSERT INTO allegati (id,pratica_id,tipo,nome_file,percorso,dimensione) VALUES (?,?,?,?,?,?)",
                (gen_id(), pratica_id, tipo, finfo["filename"], fpath, len(finfo["body"]))
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _get_form_data(self):
        data = {}
        for k in self.request.arguments:
            data[k] = self.get_argument(k, "")
        return data

class PraticaRiepilogoHandler(BaseHandler):
    def get(self, pratica_id):
        if not self.require_login(): return
        p = get_pratica(pratica_id)
        if not p:
            self.render_error(404, "Pratica non trovata")
            return
        zona_info = get_info_zona(p["zona"])
        self.render("pratica_riepilogo.html", utente=self.current_user,
                    pratica=p, zona_info=zona_info,
                    tipi=TIPI_OCCUPAZIONE, stati=STATI_PRATICA)

class PraticaPagaHandler(BaseHandler):
    def get(self, pratica_id):
        if not self.require_login(): return
        p = get_pratica(pratica_id)
        if not p:
            self.render_error(404, "Pratica non trovata")
            return
        self.render("pagamento.html", utente=self.current_user, pratica=p,
                    zona_info=get_info_zona(p["zona"]), tipi=TIPI_OCCUPAZIONE)

    def post(self, pratica_id):
        if not self.require_login(): return
        canale = self.get_argument("canale", "MOCK_PAGOPA")
        conferma_pagamento(pratica_id, canale)
        self.redirect(f"/pratica/{pratica_id}/riepilogo?pagato=1")

class PraticaDettaglioHandler(BaseHandler):
    def get(self, pratica_id):
        if not self.require_login(): return
        p = get_pratica(pratica_id)
        if not p:
            self.render_error(404, "Pratica non trovata")
            return
        allegati = get_allegati(pratica_id)
        eventi = get_eventi(pratica_id)
        self.render("pratica_dettaglio_pubblico.html",
                    utente=self.current_user, pratica=p,
                    allegati=allegati, eventi=eventi,
                    zona_info=get_info_zona(p["zona"]),
                    tipi=TIPI_OCCUPAZIONE, stati=STATI_PRATICA)

class DownloadConcessioneHandler(BaseHandler):
    def get(self, pratica_id):
        p = get_pratica(pratica_id)
        if not p or p["stato"] != "APPROVATA":
            self.render_error(404, "Concessione non disponibile")
            return
        path = p.get("concessione_path")
        if not path or not os.path.exists(path):
            path = genera_pdf_concessione(pratica_id)
        if not path:
            self.render_error(500, "Errore generazione PDF")
            return
        self.set_header("Content-Type", "application/pdf")
        self.set_header("Content-Disposition",
                        f'attachment; filename="concessione_{p["numero_pratica"]}.pdf"')
        with open(path, "rb") as f:
            self.write(f.read())

class DownloadModuloUfficialeHandler(BaseHandler):
    """Genera e scarica il Modulo A ufficiale compilato con i dati della pratica."""
    def get(self, pratica_id):
        p = get_pratica(pratica_id)
        if not p:
            self.render_error(404, "Pratica non trovata")
            return
        path = genera_pdf_modulo_ufficiale(pratica_id)
        if not path:
            self.render_error(500, "Errore generazione modulo ufficiale")
            return
        self.set_header("Content-Type", "application/pdf")
        self.set_header("Content-Disposition",
                        f'attachment; filename="moduloA_{p["numero_pratica"]}.pdf"')
        with open(path, "rb") as f:
            self.write(f.read())

class AllegatoUploadHandler(BaseHandler):
    def post(self, pratica_id):
        if not self.require_login(): return
        tipo = self.get_argument("tipo", "ALTRO")
        if "file" not in self.request.files or not self.request.files["file"]:
            self.json_out({"ok": False, "errore": "Nessun file"}, 400)
            return
        fileinfo = self.request.files["file"][0]
        fname = fileinfo["filename"]
        ext = os.path.splitext(fname)[1].lower()
        allowed = {".pdf", ".jpg", ".jpeg", ".png", ".gif"}
        if ext not in allowed:
            self.json_out({"ok": False, "errore": f"Formato non supportato: {ext}"}, 400)
            return
        pratica_dir = os.path.join(UPLOAD_DIR, pratica_id)
        os.makedirs(pratica_dir, exist_ok=True)
        safe_name = f"{gen_id()}{ext}"
        path = os.path.join(pratica_dir, safe_name)
        with open(path, "wb") as f:
            f.write(fileinfo["body"])
        conn = get_conn()
        all_id = gen_id()
        conn.execute("""
            INSERT INTO allegati (id, pratica_id, tipo, nome_file, percorso, mime_type, dimensione)
            VALUES (?,?,?,?,?,?,?)
        """, (all_id, pratica_id, tipo, fname, path,
              mimetypes.guess_type(fname)[0] or "application/octet-stream",
              len(fileinfo["body"])))
        conn.commit()
        conn.close()
        self.json_out({"ok": True, "allegato_id": all_id, "nome": fname})


# ─────────────────────────────────────────────────────────────
# PORTALE OPERATORI POLIZIA LOCALE
# ─────────────────────────────────────────────────────────────

class OperatoreDashboardHandler(BaseHandler):
    def get(self, zona):
        if not self.require_operatore(): return
        zona = int(zona)
        u = self.current_user
        # Verifica che l'operatore sia della zona giusta (o admin)
        if u["tipo"] != "ADMIN" and u.get("zona") != zona:
            self.render_error(403, "Non autorizzato per questa zona")
            return
        kpi = get_kpi_zona(zona)
        pratiche_urgenti = get_pratiche_zona(zona, stato="PAGATA", limit=20)
        pratiche_recenti = get_pratiche_zona(zona, limit=30)
        zona_info = get_info_zona(zona)
        self.render("operatore_dashboard.html",
                    utente=u, zona=zona, zona_info=zona_info,
                    kpi=kpi, pratiche_urgenti=pratiche_urgenti,
                    pratiche_recenti=pratiche_recenti,
                    tipi=TIPI_OCCUPAZIONE, stati=STATI_PRATICA)

class OperatorePraticheHandler(BaseHandler):
    def get(self, zona):
        if not self.require_operatore(): return
        zona = int(zona)
        stato = self.get_argument("stato", "")
        pratiche = get_pratiche_zona(zona, stato=stato or None)
        zona_info = get_info_zona(zona)
        self.render("operatore_pratiche.html",
                    utente=self.current_user, zona=zona, zona_info=zona_info,
                    pratiche=pratiche, stato_filtro=stato,
                    tipi=TIPI_OCCUPAZIONE, stati=STATI_PRATICA)

class OperatorePraticaDettaglioHandler(BaseHandler):
    def get(self, pratica_id):
        if not self.require_operatore(): return
        p = get_pratica(pratica_id)
        if not p:
            self.render_error(404, "Pratica non trovata")
            return
        allegati = get_allegati(pratica_id)
        eventi = get_eventi(pratica_id)
        zona_info = get_info_zona(p["zona"])
        self.render("operatore_pratica_dettaglio.html",
                    utente=self.current_user, pratica=p,
                    allegati=allegati, eventi=eventi,
                    zona_info=zona_info, tipi=TIPI_OCCUPAZIONE, stati=STATI_PRATICA,
                    errore=None)

    def post(self, pratica_id):
        if not self.require_operatore(): return
        azione = self.get_argument("azione", "")
        u = self.current_user
        note = self.get_argument("note_operatore", "")
        motivo = self.get_argument("motivo_rifiuto", "")

        if azione == "approva":
            aggiorna_stato_pratica(pratica_id, "APPROVATA", u["id"], note)
            # Genera PDF concessione
            genera_pdf_concessione(pratica_id)
        elif azione == "rifiuta":
            if not motivo:
                p = get_pratica(pratica_id)
                self.render("operatore_pratica_dettaglio.html",
                            utente=u, pratica=p,
                            allegati=get_allegati(pratica_id),
                            eventi=get_eventi(pratica_id),
                            zona_info=get_info_zona(p["zona"]),
                            tipi=TIPI_OCCUPAZIONE, stati=STATI_PRATICA,
                            errore="Inserisci la motivazione del rifiuto")
                return
            aggiorna_stato_pratica(pratica_id, "RIFIUTATA", u["id"], note, motivo)
        elif azione == "integrazioni":
            aggiorna_stato_pratica(pratica_id, "INTEGRAZIONI", u["id"], note)
        elif azione == "in_revisione":
            aggiorna_stato_pratica(pratica_id, "PAGATA", u["id"], note)

        self.redirect(f"/operatore/pratiche/{pratica_id}")

class OperatoreCentraleHandler(BaseHandler):
    def get(self):
        if not self.require_operatore(): return
        u = self.current_user
        if u["tipo"] != "ADMIN":
            zona = u.get("zona", 1)
            self.redirect(f"/operatore/zona/{zona}")
            return
        kpi = get_kpi_globali()
        self.render("operatore_centrale.html",
                    utente=u, kpi=kpi,
                    comandi=COMANDI_DECENTRATI, stati=STATI_PRATICA)

class OperatoreDownloadModuloHandler(BaseHandler):
    """Scarica il Modulo A ufficiale compilato — visibile agli operatori."""
    def get(self, pratica_id):
        if not self.require_operatore(): return
        p = get_pratica(pratica_id)
        if not p:
            self.render_error(404, "Pratica non trovata")
            return
        path = genera_pdf_modulo_ufficiale(pratica_id)
        if not path:
            self.render_error(500, "Errore generazione modulo")
            return
        self.set_header("Content-Type", "application/pdf")
        self.set_header("Content-Disposition",
                        f'inline; filename="moduloA_{p["numero_pratica"]}.pdf"')
        with open(path, "rb") as f:
            self.write(f.read())

class OperatoreDownloadConcessioneHandler(BaseHandler):
    def get(self, pratica_id):
        if not self.require_operatore(): return
        p = get_pratica(pratica_id)
        if not p or p["stato"] != "APPROVATA":
            self.render_error(404, "Concessione non disponibile")
            return
        path = p.get("concessione_path")
        if not path or not os.path.exists(path):
            path = genera_pdf_concessione(pratica_id)
        self.set_header("Content-Type", "application/pdf")
        self.set_header("Content-Disposition",
                        f'inline; filename="concessione_{p["numero_pratica"]}.pdf"')
        with open(path, "rb") as f:
            self.write(f.read())


# ─────────────────────────────────────────────────────────────
# API JSON
# ─────────────────────────────────────────────────────────────

class ApiCalcolaCosapHandler(BaseHandler):
    def get(self):
        """GET /api/cosap/calcola?superficie_mq=10&data_inizio=...&data_fine=...&microzona_id=&tipo_occupazione="""
        try:
            sup = float(self.get_argument("superficie_mq", "0") or 0)
            d1 = self.get_argument("data_inizio", "")
            d2 = self.get_argument("data_fine", "")
            microzona_id = self.get_argument("microzona_id", "") or None
            tipo = self.get_argument("tipo_occupazione", "ALTRO")
            giorni = calcola_giorni(d1, d2) if d1 and d2 else 1
            if giorni > MAX_GIORNI_OSP:
                self.json_out({"errore": f"Durata massima: {MAX_GIORNI_OSP} giorni", "giorni": giorni}, 400)
                return
            coeff_mz, cat = get_coeff_microzona(microzona_id)
            result = calcola_cosap(sup, giorni, cat, tipo, coeff_microzona=coeff_mz, microzona_id=microzona_id)
            result["giorni"] = giorni
            self.json_out(result)
        except Exception as e:
            self.json_out({"errore": str(e)}, 400)

    def post(self):
        """POST JSON body"""
        try:
            data = json.loads(self.request.body)
            sup = float(data.get("superficie_mq", 0))
            d1 = data.get("data_inizio", "")
            d2 = data.get("data_fine", "")
            microzona_id = data.get("microzona_id") or None
            tipo = data.get("tipo_occupazione", "ALTRO")
            giorni = calcola_giorni(d1, d2) if d1 and d2 else int(data.get("giorni", 1))
            if giorni > MAX_GIORNI_OSP:
                self.json_out({"errore": f"Durata massima: {MAX_GIORNI_OSP} giorni", "giorni": giorni}, 400)
                return
            coeff_mz, cat = get_coeff_microzona(microzona_id, data.get("zona"))
            result = calcola_cosap(sup, giorni, cat, tipo, coeff_microzona=coeff_mz, microzona_id=microzona_id)
            result["giorni"] = giorni
            self.json_out(result)
        except Exception as e:
            self.json_out({"errore": str(e)}, 400)

class ApiRilevaZonaHandler(BaseHandler):
    def get(self):
        cap = self.get_argument("cap", "")
        zona, info = rileva_zona_da_cap(cap)
        self.json_out({
            "zona": zona,
            "nome": info["nome"],
            "email": info["email"],
            "categoria_prevalente": info["categoria_prevalente"],
        })

class ApiPraticaHandler(BaseHandler):
    def get(self, pratica_id):
        p = get_pratica(pratica_id)
        if not p:
            self.json_out({"errore": "Non trovata"}, 404)
            return
        self.json_out(p)


# ─────────────────────────────────────────────────────────────
# MODULO UFFICIALE PDF (overlay su template ufficiale o generato)
# ─────────────────────────────────────────────────────────────

def genera_pdf_modulo_ufficiale(pratica_id):
    """
    Genera il Modulo A ufficiale compilato con i dati della pratica,
    fedele al layout del modulo ufficiale del Comune di Milano.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.units import cm, mm
    from reportlab.pdfbase import pdfmetrics

    p = get_pratica(pratica_id)
    if not p: return None

    zona_info = get_info_zona(p["zona"])
    nome_richiedente = p.get("ragione_sociale") or f"{p.get('nome','')} {p.get('cognome','')}".strip()
    is_pg = p.get("tipo_soggetto") == "PERSONA_GIURIDICA"

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "uploads",
        f"moduloA_{p['numero_pratica'].replace('-','_')}.pdf"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Canvas-based drawing for faithful reproduction of official form
    W, H = A4  # 595.27, 841.89 points
    LM = 2.0 * cm   # left margin
    RM = W - 1.8*cm # right margin
    TW = RM - LM    # text width

    c = pdfcanvas.Canvas(output_path, pagesize=A4)

    def line_field(c, x, y, label, value, label_w=0, line_to=None, fs=9):
        """Draw a label followed by dotted underline with filled value."""
        if label:
            c.setFont("Helvetica", fs)
            c.drawString(x, y, label)
            x2 = x + c.stringWidth(label, "Helvetica", fs) + 2
        else:
            x2 = x
        end_x = line_to or (RM)
        # dotted underline
        c.setDash(1, 2)
        c.setLineWidth(0.3)
        c.line(x2, y - 1, end_x, y - 1)
        c.setDash()
        # filled value in blue
        if value:
            c.setFont("Helvetica-Bold", fs)
            c.setFillColorRGB(0, 0.24, 0.54)
            c.drawString(x2 + 2, y, str(value)[:80])
            c.setFillColorRGB(0, 0, 0)

    def checkbox(c, x, y, checked=False, label="", fs=9):
        """Draw a checkbox with optional label."""
        c.setLineWidth(0.5)
        c.rect(x, y - 1, 7, 7)
        if checked:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 1, y, "X")
        if label:
            c.setFont("Helvetica", fs)
            c.drawString(x + 10, y, label)

    # ═══════════ PAGE 1 ═══════════
    y = H - 1.5*cm

    # ── TOP RIGHT: "Domanda di occupazione" box ──
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(RM, y, "Domanda di occupazione")
    y -= 0.45*cm
    c.setFont("Helvetica", 7)
    bollo_lines = [
        "Imposta di Bollo",
        "da € 16,00",
        "assolta in modo virtuale",
        "DPR 642/72 - Art. 15",
        "Aut. 3/5511/2001",
    ]
    for bl in bollo_lines:
        c.drawRightString(RM, y, bl)
        y -= 0.32*cm

    # ── TOP LEFT: Comune di Milano logo/header ──
    c.setFont("Helvetica-Bold", 12)
    c.drawString(LM, H - 1.5*cm, "Comune di")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(LM, H - 2.1*cm, "Milano")

    # Separator line after header
    y = H - 3.3*cm
    c.setLineWidth(0.5)
    c.line(LM, y, RM, y)
    y -= 0.4*cm

    # ── TITLE ──
    c.setFont("Helvetica-Bold", 11)
    title = "DOMANDA DI OCCUPAZIONE TEMPORANEA DI SUOLO PUBBLICO"
    c.drawString(LM, y, title)
    y -= 0.7*cm

    # ── All'Unità Comando Decentrato ──
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(RM, y, f"All'Unità Comando Decentrato  {zona_info['nome']}")
    y -= 0.7*cm

    # ── RICHIEDENTE section ──
    nome = p.get("nome","") or ""
    cognome = p.get("cognome","") or ""
    luogo_nascita = p.get("luogo_nascita","") or ""
    data_nascita = p.get("data_nascita","") or ""
    residenza = p.get("richiedente_indirizzo","") or ""
    citta_res = p.get("citta","") or ""
    doc_id = p.get("documento_identita","") or ""
    tel = p.get("telefono","") or ""
    ragione_soc = p.get("ragione_sociale","") or ""
    sede = p.get("sede_legale","") or ""
    via_az = ""
    tel_az = p.get("telefono","") or ""
    cf_piva = p.get("codice_fiscale","") or p.get("partita_iva","") or ""

    # "Il/La sottoscritto/a ... nato/a ... il ..."
    c.setFont("Helvetica", 9)
    line_field(c, LM, y, "Il/La sottoscritto/a ", f"{nome} {cognome}".strip(),
               line_to=LM + 8*cm)
    mid = LM + 8.5*cm
    line_field(c, mid, y, "nato/a ", luogo_nascita, line_to=mid + 4.5*cm)
    right_part = mid + 5*cm
    line_field(c, right_part, y, "il ", data_nascita, line_to=RM)
    y -= 0.6*cm

    # "residente a ... in ..."
    line_field(c, LM, y, "residente a ", residenza, line_to=LM + 9*cm)
    line_field(c, LM + 9.5*cm, y, "in ", citta_res, line_to=RM)
    y -= 0.6*cm

    # "Doc. Id. n° ... tel. ..."
    line_field(c, LM, y, "Doc. Id. n°  ", doc_id, line_to=LM + 9*cm)
    line_field(c, LM + 9.5*cm, y, "tel. ", tel, line_to=RM)
    y -= 0.6*cm

    # "per conto di ... con sede a ..."
    line_field(c, LM, y, "per conto di ", ragione_soc or "—", line_to=LM + 9*cm)
    line_field(c, LM + 9.5*cm, y, "con sede a ", sede, line_to=RM)
    y -= 0.6*cm

    # "in via/piazza ... tel. ..."
    line_field(c, LM, y, "in via/piazza ", via_az, line_to=LM + 10*cm)
    line_field(c, LM + 10.5*cm, y, "tel. ", tel_az, line_to=RM)
    y -= 0.6*cm

    # "Doc. Id./C.F./P.I. ..."
    line_field(c, LM, y, "Doc. Id./C.F./P.I. ", cf_piva, line_to=RM)
    y -= 0.8*cm

    # ── BOLD TITLE: CHIEDE IL RILASCIO... ──
    c.setFont("Helvetica-Bold", 9)
    c.drawString(LM, y,
        "CHIEDE IL RILASCIO DELL\u2019AUTORIZZAZIONE PER L\u2019OCCUPAZIONE TEMPORANEA DI SUOLO PUBBLICO")
    y -= 0.7*cm

    # ── LOCATION ──
    via_str = f"{p.get('via','')} n. {p.get('civico','')}"
    line_field(c, LM, y, "in Milano, via/piazza ", via_str, line_to=RM)
    y -= 0.4*cm
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(LM, y,
        "(la localit\xe0 deve essere indicata con precisione \u2013 numero civico, palo luce e qualsiasi altro riferimento utile)")
    y -= 0.5*cm

    # "di mq ... pari a mt x mt ..."
    sup = str(p.get("superficie_mq",""))
    dim = p.get("dimensioni","") or ""
    c.setFont("Helvetica", 9)
    line_field(c, LM, y, "di mq ", sup, line_to=LM + 3*cm)
    line_field(c, LM + 3.3*cm, y, "pari a mt x mt ", dim, line_to=LM + 7.5*cm)

    # Surface type checkboxes
    surf = (p.get("tipo_superficie") or "").upper()
    cx = LM + 8*cm
    checkbox(c, cx, y, checked=(surf=="MARCIAPIEDE"), label="Sul marciapiede")
    cx += 3.5*cm
    checkbox(c, cx, y, checked=(surf=="CARREGGIATA"), label="In carreggiata")
    cx += 3.3*cm
    checkbox(c, cx, y, checked=(surf=="AREA_VERDE"), label="Su sterrato/Area Verde")
    y -= 0.55*cm

    # Stalli di sosta
    checkbox(c, LM, y, checked=False, label="Rientrante negli stalli di sosta")
    y -= 0.5*cm
    checkbox(c, LM, y, checked=False, label="Eccedente gli stalli di sosta")
    cx2 = LM + 5.5*cm
    checkbox(c, cx2, y, checked=(surf=="MARCIAPIEDE"), label="Sul marciapiede")
    cx2 += 3.5*cm
    checkbox(c, cx2, y, checked=(surf=="CARREGGIATA"), label="In carreggiata")
    cx2 += 3.3*cm
    checkbox(c, cx2, y, checked=(surf=="AREA_VERDE"), label="Su sterrato/Area Verde")
    y -= 0.6*cm

    # "per il/i giorno/i ... dalle ore ... alle ore ..."
    date_str = f"dal {p.get('data_inizio','')} al {p.get('data_fine','')}"
    orario_i = p.get("orario_inizio","") or ""
    orario_f = p.get("orario_fine","") or ""
    line_field(c, LM, y, "per il/i giorno/i ", date_str, line_to=LM + 9*cm)
    line_field(c, LM + 9.3*cm, y, "dalle ore ", orario_i, line_to=LM + 12.5*cm)
    line_field(c, LM + 12.8*cm, y, "alle ore ", orario_f, line_to=RM)
    y -= 0.6*cm

    # "per lo svolgimento di ..."
    tipo_str = TIPI_OCCUPAZIONE.get(p.get("tipo_occupazione",""), p.get("tipo_occupazione",""))
    desc = p.get("descrizione","") or tipo_str
    line_field(c, LM, y, "per lo svolgimento di ", desc[:70], line_to=RM)
    y -= 0.7*cm

    # ── SPECIAL VEHICLES ──
    ha_autogru = p.get("tipo_occupazione") == "AUTOGRU"
    c.setFont("Helvetica", 9)
    c.drawString(LM, y, "Sono utilizzati mezzi operativi speciali:")
    checkbox(c, LM + 8.5*cm, y, checked=ha_autogru, label="SI")
    checkbox(c, LM + 9.5*cm, y, checked=(not ha_autogru), label="NO")
    y -= 0.5*cm
    checkbox(c, LM, y, checked=ha_autogru, label="Autogru")
    checkbox(c, LM + 2.5*cm, y, checked=False, label="Autoscala")
    checkbox(c, LM + 5*cm, y, checked=False, label="Autoelevatore")
    checkbox(c, LM + 8*cm, y, checked=False, label="Piattaforma Mobile")
    checkbox(c, LM + 11.5*cm, y, checked=False, label="Altro")
    line_field(c, LM + 12.3*cm, y, "", "", line_to=RM)
    y -= 0.7*cm

    # ── ZTL section ──
    c.setFont("Helvetica", 8)
    c.drawString(LM, y, "Da compilare soltanto in caso di accesso in:")
    y -= 0.5*cm
    checkbox(c, LM, y, checked=False, label="Corsia riservata ai mezzi pubblici")
    checkbox(c, LM + 5.5*cm, y, checked=False, label="ZTL")
    checkbox(c, LM + 7.5*cm, y, checked=False, label="Area Pedonale")
    checkbox(c, LM + 10*cm, y, checked=False, label="Altro")
    line_field(c, LM + 11.5*cm, y, "", "", line_to=RM)
    y -= 0.5*cm

    targa = p.get("targhe_mezzi","") or ""
    line_field(c, LM, y, "nella/e seguente/i localit\xe0 ", "", line_to=RM)
    y -= 0.5*cm
    line_field(c, LM, y, "con il veicolo Marca ", "", line_to=LM + 6*cm)
    line_field(c, LM + 6.3*cm, y, "Modello ", "", line_to=LM + 11*cm)
    line_field(c, LM + 11.3*cm, y, "Targa ", targa, line_to=RM)
    y -= 0.5*cm
    line_field(c, LM, y, "di propriet\xe0 di ", nome_richiedente, line_to=RM)
    y -= 0.9*cm

    # ── PHASE 2 (optional - always shown as unchecked) ──
    c.setLineWidth(0.5)
    c.rect(LM, y - 1, 8, 8)  # empty checkbox for phase 2
    c.setFont("Helvetica-Bold", 8)
    c.drawString(LM + 12, y,
        "CHIEDE INOLTRE IL RILASCIO DELL\u2019AUTORIZZAZIONE PER L\u2019OCCUPAZIONE TEMPORANEA DI SUOLO PUBBLICO")
    y -= 0.4*cm
    c.drawString(LM + 12, y, "PER LO SVOLGIMENTO DELLA FASE SUCCESSIVA DELLA PREDETTA ATTIVIT\xc0:")
    y -= 0.6*cm
    c.setFont("Helvetica", 9)
    line_field(c, LM, y, "in Milano, via/piazza ", "", line_to=RM - 4*cm)
    line_field(c, RM - 3.8*cm, y, "(Unit\xe0 Comando Decentrato ", str(p.get("zona","")),
               line_to=RM - 0.3*cm)
    c.drawString(RM - 0.2*cm, y, ")")
    y -= 0.5*cm
    line_field(c, LM, y, "di mq ", "", line_to=LM + 3*cm)
    line_field(c, LM + 3.3*cm, y, "pari a mt x mt ", "", line_to=LM + 8*cm)
    checkbox(c, LM + 8.3*cm, y, checked=False, label="Sul marciapiede")
    checkbox(c, LM + 11.8*cm, y, checked=False, label="In carreggiata")
    y -= 0.5*cm
    checkbox(c, LM, y, checked=False, label="Rientrante negli stalli di sosta")
    y -= 0.5*cm
    checkbox(c, LM, y, checked=False, label="Eccedente gli stalli di sosta")
    checkbox(c, LM + 5.5*cm, y, checked=False, label="Sul marciapiede")
    checkbox(c, LM + 9*cm, y, checked=False, label="In carreggiata")
    y -= 0.6*cm
    line_field(c, LM, y, "per il/i giorno/i ", "", line_to=LM + 9*cm)
    line_field(c, LM + 9.3*cm, y, "dalle ore ", "", line_to=LM + 12.5*cm)
    line_field(c, LM + 12.8*cm, y, "alle ore ", "", line_to=RM)
    y -= 0.8*cm

    # ── PRIVACY FOOTER ──
    c.setFont("Helvetica-Oblique", 6.5)
    privacy_lines = [
        "Informativa sul trattamento dei dati personali ai sensi dell\u2019articolo 13 del Regolamento (UE) 2016/679",
        "I dati personali qui obbligatoriamente forniti dal richiedente sono oggetto del trattamento al solo fine istruttorio della presente richiesta di accesso.",
        "Il titolare del trattamento \xe8 il Comune di Milano. Per ulteriori informazioni si rinvia a www.comune.milano.it",
    ]
    for pl in privacy_lines:
        c.drawString(LM, y, pl)
        y -= 0.3*cm

    c.showPage()

    # ═══════════ PAGE 2 ═══════════
    y = H - 1.8*cm
    c.setFont("Helvetica", 9)
    c.drawRightString(RM, y, "Domanda di occupazione")
    y -= 1.0*cm

    # ── ALLEGATI ──
    c.setFont("Helvetica", 9)
    c.drawString(LM, y, "Allegati:")
    y -= 0.6*cm
    checkbox(c, LM, y, checked=True,
             label="Dichiarazione di presa visione delle prescrizioni generali e di assunzione di responsabilit\xe0;")
    y -= 0.6*cm
    checkbox(c, LM, y, checked=False,
             label="Oppure estremi della stessa, firmata il")
    line_field(c, LM + 7.8*cm, y, "", "", line_to=LM + 12*cm)
    c.drawString(LM + 12.2*cm, y, "presso l'Unit\xe0 Comando Decentrato")
    line_field(c, LM + 16.5*cm, y, "", "", line_to=RM)
    y -= 1.2*cm

    # ── DATA / FIRMA ──
    c.drawString(LM, y, "Data")
    line_field(c, LM + 1*cm, y, "", datetime.datetime.now().strftime("%d/%m/%Y"),
               line_to=LM + 6*cm)
    c.drawString(LM + 9*cm, y, "Il/La richiedente")
    line_field(c, LM + 12*cm, y, "", "", line_to=RM)
    y -= 2.5*cm

    # ── PARTE RISERVATA ALL'UFFICIO ──
    c.setLineWidth(0.5)
    c.line(LM, y + 0.5*cm, RM, y + 0.5*cm)
    c.setFont("Helvetica-Bold", 10)
    title_w = c.stringWidth("PARTE RISERVATA ALL\u2019UFFICIO", "Helvetica-Bold", 10)
    c.drawString((W - title_w) / 2, y, "PARTE RISERVATA ALL\u2019UFFICIO")
    y -= 0.5*cm
    c.setFont("Helvetica-Bold", 9)
    timbro_w = c.stringWidth("Timbro", "Helvetica-Bold", 9)
    c.drawString((W - timbro_w) / 2, y, "Timbro")
    y -= 2.5*cm  # space for stamp

    # Aut./Ricevuta lines
    c.setFont("Helvetica", 9)
    # First line - filled with actual data
    aut_str = p.get("numero_pratica","") or ""
    stato_str = STATI_PRATICA.get(p.get("stato",""), ("—",""))[0]
    line_field(c, LM, y, "Data di Ricevimento ", p.get("created_at","")[:10] if p.get("created_at") else "",
               line_to=LM + 6*cm)
    line_field(c, LM + 6.3*cm, y, "Aut./Ricevuta n\xb0 ", aut_str, line_to=LM + 13.5*cm)
    line_field(c, LM + 13.8*cm, y, "Unit\xe0 Comando Decentrato ", str(p.get("zona","")), line_to=RM)
    y -= 1.2*cm

    # Second line (for concessione)
    conc_str = p.get("numero_concessione","") or ""
    conc_date = p.get("data_concessione","")[:10] if p.get("data_concessione") else ""
    line_field(c, LM, y, "Data di Ricevimento ", conc_date, line_to=LM + 6*cm)
    line_field(c, LM + 6.3*cm, y, "Aut./Ricevuta n\xb0 ", conc_str, line_to=LM + 13.5*cm)
    line_field(c, LM + 13.8*cm, y, "Unit\xe0 Comando Decentrato ", str(p.get("zona","")), line_to=RM)
    y -= 1.8*cm

    # ── L'occupazione comporta ──
    c.setFont("Helvetica", 9)
    c.drawString(LM, y, "L\u2019occupazione comporta:")
    y -= 0.6*cm

    imp_traffico = (p.get("impatto_traffico","") or "").upper()
    occ_items = [
        ("Provvedimenti di divieto di sosta con rimozione coatta",
         imp_traffico in ("DIVIETO_SOSTA","DIVIETO_SOSTA_RIMOZIONE")),
        ("La chiusura al transito veicolare della/e strada/e interessata/e",
         imp_traffico == "CHIUSURA_STRADA"),
        ("L\u2019istituzione di un senso unico alternato",
         imp_traffico == "SENSO_UNICO_ALTERNATO"),
        ("La presenza di personale di PL per ausilio viabilistico",
         imp_traffico == "PRESENZA_PL"),
        ("L\u2019autorizzazione per lavori notturni (Art. 101 R.P.U.)",
         False),
    ]
    for label, checked in occ_items:
        checkbox(c, LM, y, checked=checked, label=label)
        y -= 0.55*cm

    # ── NOTE OPERATORE (extra section for police) ──
    if p.get("stato") == "APPROVATA" and p.get("numero_concessione"):
        y -= 0.5*cm
        c.setLineWidth(0.5)
        c.line(LM, y + 0.3*cm, RM, y + 0.3*cm)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(LM, y, f"\u2192 PRATICA APPROVATA — Concessione N. {p['numero_concessione']}")
        y -= 0.35*cm
        c.setFont("Helvetica", 8)
        note_op = p.get("note_operatore","") or "—"
        c.drawString(LM, y, f"Note operatore: {note_op[:100]}")
        y -= 0.35*cm
        c.drawString(LM, y,
            f"Pratica: {p['numero_pratica']}  |  Stato: {stato_str}  |  "
            f"Generato il: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # ── FOOTER ──
    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    footer_txt = (f"Documento generato automaticamente dal Sistema OSP Comune di Milano  |  "
                  f"Pratica {p['numero_pratica']}  |  {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.drawCentredString(W / 2, 1.2*cm, footer_txt)
    c.setFillColorRGB(0, 0, 0)

    c.save()
    return output_path


# ─────────────────────────────────────────────────────────────
# REGISTRAZIONE / PROFILO
# ─────────────────────────────────────────────────────────────

class RegisterHandler(BaseHandler):
    def get(self):
        self.render("register.html", utente=self.current_user, errore=None)

    def post(self):
        username = self.get_argument("username","").strip()
        password = self.get_argument("password","").strip()
        password2 = self.get_argument("password2","").strip()
        nome = self.get_argument("nome","").strip()
        cognome = self.get_argument("cognome","").strip()
        email = self.get_argument("email","").strip()

        if not all([username, password, nome, cognome, email]):
            self.render("register.html", utente=None, errore="Tutti i campi sono obbligatori")
            return
        if password != password2:
            self.render("register.html", utente=None, errore="Le password non coincidono")
            return
        if len(password) < 8:
            self.render("register.html", utente=None, errore="Password minimo 8 caratteri")
            return

        conn = get_conn()
        existing = conn.execute("SELECT id FROM utenti WHERE username=?", (username,)).fetchone()
        if existing:
            conn.close()
            self.render("register.html", utente=None, errore="Username già in uso")
            return

        uid = gen_id()
        conn.execute("""
            INSERT INTO utenti (id, tipo, username, password_hash, nome, cognome, email)
            VALUES (?,?,?,?,?,?,?)
        """, (uid, "RICHIEDENTE", username, hash_password(password), nome, cognome, email))
        conn.commit()
        conn.close()
        self.redirect("/login?registrato=1")


# ─────────────────────────────────────────────────────────────
# ROUTING E APP
# ─────────────────────────────────────────────────────────────

def make_app():
    base = os.path.dirname(os.path.abspath(__file__))
    settings = {
        "template_path": os.path.join(base, "templates"),
        "static_path": os.path.join(base, "static"),
        "cookie_secret": SECRET_KEY,
        "debug": DEBUG,
        "xsrf_cookies": False,
    }
    return tornado.web.Application([
        # Pubblico
        (r"/", HomeHandler),
        (r"/login", LoginHandler),
        (r"/logout", LogoutHandler),
        (r"/register", RegisterHandler),
        (r"/verifica/(.+)", VerificaConcessioneHandler),

        # Portale richiedente
        (r"/portale", PortaleHandler),
        (r"/nuova-pratica", NuovaPraticaHandler),
        (r"/pratica/([^/]+)/riepilogo", PraticaRiepilogoHandler),
        (r"/pratica/([^/]+)/paga", PraticaPagaHandler),
        (r"/pratica/([^/]+)/dettaglio", PraticaDettaglioHandler),
        (r"/pratica/([^/]+)/concessione", DownloadConcessioneHandler),
        (r"/pratica/([^/]+)/modulo-ufficiale", DownloadModuloUfficialeHandler),
        (r"/pratica/([^/]+)/upload", AllegatoUploadHandler),

        # Portale operatori
        (r"/operatore/centrale", OperatoreCentraleHandler),
        (r"/operatore/zona/(\d+)", OperatoreDashboardHandler),
        (r"/operatore/zona/(\d+)/pratiche", OperatorePraticheHandler),
        (r"/operatore/pratiche/([^/]+)", OperatorePraticaDettaglioHandler),
        (r"/operatore/pratiche/([^/]+)/modulo-ufficiale", OperatoreDownloadModuloHandler),
        (r"/operatore/pratiche/([^/]+)/concessione", OperatoreDownloadConcessioneHandler),

        # API
        (r"/api/cosap/calcola", ApiCalcolaCosapHandler),
        (r"/api/zone/rileva", ApiRilevaZonaHandler),
        (r"/api/pratica/([^/]+)", ApiPraticaHandler),

        # Static
        (r"/static/(.*)", tornado.web.StaticFileHandler,
         {"path": os.path.join(base, "static")}),
        (r"/uploads/(.*)", tornado.web.StaticFileHandler,
         {"path": UPLOAD_DIR}),
    ], **settings)


if __name__ == "__main__":
    print("=" * 60)
    print("  OSP MILANO — Portale Suolo Pubblico Temporaneo")
    print("=" * 60)
    init_db()
    app = make_app()
    app.listen(PORT)
    print(f"\n✅ Server avviato su http://localhost:{PORT}")
    print(f"   Portale richiedenti : http://localhost:{PORT}/portale")
    print(f"   Portale operatori   : http://localhost:{PORT}/operatore/centrale")
    print(f"   Login operatori     : admin / admin123")
    print(f"\n   Ctrl+C per fermare\n")
    tornado.ioloop.IOLoop.current().start()
