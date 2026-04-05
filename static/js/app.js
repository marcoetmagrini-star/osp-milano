/* ════════════════════════════════════════════════════════
   OSP Milano — Frontend JS
   ════════════════════════════════════════════════════════ */

// ── FORM STEPPER ──
const FormStepper = {
  current: 0,
  total: 0,

  init() {
    this.total = document.querySelectorAll('.form-section').length;
    this.updateUI();
    // Next/Prev buttons
    document.querySelectorAll('[data-next]').forEach(btn =>
      btn.addEventListener('click', () => this.next(btn)));
    document.querySelectorAll('[data-prev]').forEach(btn =>
      btn.addEventListener('click', () => this.prev()));
    // Step click
    document.querySelectorAll('.step[data-step]').forEach(s =>
      s.addEventListener('click', () => {
        const idx = parseInt(s.dataset.step);
        if (idx < this.current) this.goTo(idx);
      }));
  },

  validate(section) {
    let ok = true;
    section.querySelectorAll('[required]').forEach(el => {
      el.classList.remove('field-error');
      if (!el.value.trim()) {
        el.classList.add('field-error');
        ok = false;
      }
    });
    // Data fine ≤ inizio + 14
    const di = section.querySelector('#data_inizio');
    const df = section.querySelector('#data_fine');
    if (di && df && di.value && df.value) {
      const d1 = new Date(di.value), d2 = new Date(df.value);
      const diff = Math.round((d2 - d1) / 86400000) + 1;
      if (diff > 14) {
        showToast(`⚠️ Durata massima 14 giorni (selezionati: ${diff})`, 'error');
        df.classList.add('field-error');
        ok = false;
      }
      if (diff < 1) {
        showToast('La data fine non può precedere la data inizio', 'error');
        ok = false;
      }
    }
    if (!ok) showToast('Compila tutti i campi obbligatori', 'error');
    return ok;
  },

  next(btn) {
    const section = document.querySelectorAll('.form-section')[this.current];
    if (!this.validate(section)) return;
    if (this.current < this.total - 1) {
      this.current++;
      this.updateUI();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  },

  prev() {
    if (this.current > 0) {
      this.current--;
      this.updateUI();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  },

  goTo(idx) {
    this.current = idx;
    this.updateUI();
  },

  updateUI() {
    document.querySelectorAll('.form-section').forEach((s, i) => {
      s.classList.toggle('active', i === this.current);
    });
    document.querySelectorAll('.step[data-step]').forEach((s, i) => {
      s.classList.remove('active', 'done');
      if (i === this.current) s.classList.add('active');
      if (i < this.current) s.classList.add('done');
      s.querySelector('.step-circle').textContent = i < this.current ? '✓' : i + 1;
    });
    // Progress bar
    const pct = ((this.current + 1) / this.total) * 100;
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = pct + '%';
  }
};

// ── COSAP CALCULATOR ──
const CosapCalc = {
  timer: null,

  init() {
    const fields = ['superficie_mq', 'data_inizio', 'data_fine', 'tipo_occupazione', 'cap'];
    fields.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', () => this.debounce());
    });
    // CAP → zona
    const cap = document.getElementById('cap');
    if (cap) cap.addEventListener('change', () => this.detectZona(cap.value));
  },

  debounce() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.calc(), 600);
  },

  async calc() {
    const sup = document.getElementById('superficie_mq')?.value;
    const d1  = document.getElementById('data_inizio')?.value;
    const d2  = document.getElementById('data_fine')?.value;
    const tipo = document.getElementById('tipo_occupazione')?.value;
    const cat  = document.getElementById('categoria_strada')?.value || 'C';

    if (!sup || !d1 || !d2 || !tipo) return;

    try {
      const res = await fetch('/api/cosap/calcola', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ superficie_mq: sup, data_inizio: d1, data_fine: d2,
                               tipo_occupazione: tipo, categoria_strada: cat })
      });
      const data = await res.json();
      if (data.errore) {
        document.getElementById('cosap-errore').textContent = data.errore;
        document.getElementById('cosap-panel').style.display = 'none';
        return;
      }
      document.getElementById('cosap-errore').textContent = '';
      document.getElementById('cosap-panel').style.display = 'block';
      document.getElementById('cosap-val').textContent  = '€ ' + data.cosap.toFixed(2);
      document.getElementById('bollo-val').textContent  = '€ ' + data.bollo.toFixed(2);
      document.getElementById('totale-val').textContent = '€ ' + data.totale.toFixed(2);
      document.getElementById('cosap-det').textContent  = data.dettaglio;
      document.getElementById('giorni-calc').textContent = data.giorni + ' giorni';
      // Hidden fields
      const hGiorni = document.getElementById('h_giorni_effettivi');
      if (hGiorni) hGiorni.value = data.giorni;
    } catch (e) {
      console.error('COSAP calc error:', e);
    }
  },

  async detectZona(cap) {
    if (!cap || cap.length < 5) return;
    try {
      const res = await fetch('/api/zone/rileva?cap=' + cap);
      const data = await res.json();
      const el = document.getElementById('zona-detected');
      const cat = document.getElementById('categoria_strada');
      if (el) el.innerHTML = `📍 Zona ${data.zona} — ${data.nome} <br><small>${data.email}</small>`;
      if (cat) cat.value = data.categoria_prevalente;
      this.calc();
    } catch(e) {}
  }
};

// ── UPLOAD AREA ──
const Uploader = {
  init(praticaId) {
    document.querySelectorAll('.upload-area').forEach(area => {
      const input = area.querySelector('input[type=file]');
      const tipo  = area.dataset.tipo || 'ALTRO';

      area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('drag-over'); });
      area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
      area.addEventListener('drop', e => {
        e.preventDefault(); area.classList.remove('drag-over');
        this.uploadFiles(e.dataTransfer.files, tipo, praticaId, area);
      });
      area.addEventListener('click', () => input?.click());
      if (input) input.addEventListener('change', e => {
        this.uploadFiles(e.target.files, tipo, praticaId, area);
      });
    });
  },

  async uploadFiles(files, tipo, praticaId, area) {
    for (const file of files) {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('tipo', tipo);
      try {
        const res = await fetch(`/pratica/${praticaId}/upload`, { method: 'POST', body: fd });
        const data = await res.json();
        if (data.ok) {
          this.addFileItem(area, file.name, file.size, data.allegato_id);
          showToast(`✅ ${file.name} caricato`, 'success');
        } else {
          showToast('❌ ' + data.errore, 'error');
        }
      } catch(e) {
        showToast('Errore upload', 'error');
      }
    }
  },

  addFileItem(area, name, size, id) {
    let list = area.nextElementSibling;
    if (!list || !list.classList.contains('file-list')) {
      list = document.createElement('div');
      list.className = 'file-list';
      area.parentNode.insertBefore(list, area.nextSibling);
    }
    const item = document.createElement('div');
    item.className = 'file-item';
    item.innerHTML = `<span class="file-icon">📄</span>
      <span class="file-name">${name}</span>
      <span class="file-size">${(size/1024).toFixed(0)} KB</span>
      <span class="file-remove" data-id="${id}" title="Rimuovi">✕</span>`;
    item.querySelector('.file-remove').addEventListener('click', () => item.remove());
    list.appendChild(item);
  }
};

// ── PAYMENT METHODS ──
function initPayment() {
  document.querySelectorAll('.payment-method').forEach(m => {
    m.addEventListener('click', () => {
      document.querySelectorAll('.payment-method').forEach(x => x.classList.remove('selected'));
      m.classList.add('selected');
      m.querySelector('input[type=radio]').checked = true;
    });
  });
  // Auto-select first
  const first = document.querySelector('.payment-method');
  if (first) first.click();
}

// ── TOAST ──
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ── MODULO B TOGGLE ──
function initModuloB() {
  const sel = document.getElementById('tipo_occupazione');
  const secB = document.getElementById('sezione-modulo-b');
  if (!sel || !secB) return;
  const tipiB = ['EVENTO_COMMERCIALE', 'MERCATINO'];
  sel.addEventListener('change', () => {
    secB.style.display = tipiB.includes(sel.value) ? 'block' : 'none';
  });
  secB.style.display = tipiB.includes(sel.value) ? 'block' : 'none';
}

// ── DATE VALIDATION ──
function initDateValidation() {
  const di = document.getElementById('data_inizio');
  const df = document.getElementById('data_fine');
  if (!di || !df) return;

  // Set min date = today
  const oggi = new Date().toISOString().split('T')[0];
  di.min = oggi;

  di.addEventListener('change', () => {
    df.min = di.value;
    if (df.value && df.value < di.value) df.value = di.value;
    checkDuration();
  });
  df.addEventListener('change', checkDuration);

  function checkDuration() {
    const warnEl = document.getElementById('duration-warning');
    if (!di.value || !df.value || !warnEl) return;
    const d1 = new Date(di.value), d2 = new Date(df.value);
    const giorni = Math.round((d2 - d1) / 86400000) + 1;
    if (giorni > 14) {
      warnEl.innerHTML = `⚠️ <strong>Attenzione:</strong> Hai selezionato ${giorni} giorni.
        La durata massima per OMP temporanea è <strong>14 giorni</strong>.
        Per occupazioni più lunghe contatta l'<a href="mailto:occupazioni@comune.milano.it">Ufficio Suolo Pubblico</a>.`;
      warnEl.style.display = 'flex';
      df.classList.add('field-error');
    } else {
      warnEl.style.display = 'none';
      df.classList.remove('field-error');
    }
  }
}

// ── CONFIRM DIALOGS ──
function confirmAction(form, msg) {
  if (confirm(msg)) form.submit();
  return false;
}

// ── AUTO-PRINT ──
function printPage() { window.print(); }

// ── INIT ──
document.addEventListener('DOMContentLoaded', () => {
  // Form stepper
  if (document.querySelector('.form-section')) FormStepper.init();

  // COSAP calc
  if (document.getElementById('superficie_mq')) {
    CosapCalc.init();
    initModuloB();
    initDateValidation();
  }

  // Payment
  if (document.querySelector('.payment-method')) initPayment();

  // Active nav link
  document.querySelectorAll('.navbar-links a').forEach(a => {
    if (a.href === location.href || location.pathname.startsWith(a.pathname)) {
      a.classList.add('active');
    }
  });

  // Field error style
  document.querySelectorAll('.form-control.field-error').forEach(el => {
    el.style.borderColor = '#C0392B';
  });
});
