// Mock data for the OpEx dashboard
window.SITES = [
  { id: 'global',       flag: '🌍', name: 'Global',       short: 'GLOBAL' },
  { id: 'indianapolis', flag: '🇺🇸', name: 'Indianapolis', short: 'IND' },
  { id: 'alcobendas',   flag: '🇪🇸', name: 'Alcobendas',   short: 'ALB' },
  { id: 'fegersheim',   flag: '🇫🇷', name: 'Fegersheim',   short: 'FEG' },
  { id: 'sesto',        flag: '🇮🇹', name: 'Sesto',        short: 'SES' },
  { id: 'seishin',      flag: '🇯🇵', name: 'Seishin',      short: 'SEI' },
];

// ── Spark generator ─────────────────────────────────────────────
function spark(n, base, jitter, trend = 0) {
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(+(base + (Math.random() - 0.5) * jitter + trend * i).toFixed(1));
  }
  return out;
}

window.KPIS = [
  { key: 'oee',    label: 'OEE Global',    value: 84.7, unit: '%',   target: 85,    delta: +1.4, status: 'warn',
    spark: spark(20, 82, 4, 0.1) },
  { key: 'units',  label: 'Unidades',      value: 47820, unit: 'uds', target: 52000, delta: +3.2, status: 'good',
    spark: spark(20, 45000, 3000) },
  { key: 'avail',  label: 'Disponibilidad',value: 92.3, unit: '%',   target: 95,    delta: -0.8, status: 'warn',
    spark: spark(20, 91, 3) },
  { key: 'reject', label: 'Reject Rate',   value: 1.42, unit: '%',   target: 2.0,   delta: -0.3, status: 'good',
    spark: spark(20, 1.5, 0.5) },
  { key: 'down',   label: 'Downtime',      value: 38,   unit: 'min', target: 30,    delta: +6,   status: 'bad',
    spark: spark(20, 36, 12) },
  { key: 'rft',    label: 'Right First Time', value: 98.6, unit: '%', target: 99.0, delta: +0.2, status: 'info',
    spark: spark(20, 98.4, 0.6) },
];

window.LINES = [
  { id: 'L1', site: 'IND', op: 'Emily Johnson',     product: 'Autoinjectors', status: 'running', oee: 89.2, units: 11240, reject: 0.9 },
  { id: 'L2', site: 'IND', op: 'Sarah Wilson',      product: 'Insulin pens',  status: 'running', oee: 87.5, units: 10980, reject: 1.1 },
  { id: 'L3', site: 'IND', op: 'Christopher Lee',   product: 'Vials 10mL',    status: 'warn',    oee: 76.4, units: 8120,  reject: 2.4 },
  { id: 'L4', site: 'ALB', op: 'Pedro García',      product: 'Blísteres',     status: 'down',    oee: 0,    units: 6400,  reject: 1.8 },
  { id: 'L5', site: 'FEG', op: 'Pierre Dupont',     product: 'Comprimidos',   status: 'running', oee: 81.3, units: 9080,  reject: 0.7 },
  { id: 'L6', site: 'SEI', op: 'Tanaka Hiroshi',    product: 'Lyo vials',     status: 'running', oee: 92.8, units: 12100, reject: 0.4 },
];

window.ALERTS = [
  { sev: 'bad',  line: 'L4 · ALB', title: 'Atasco etiquetadora — parada activa 14 min', time: '14:32' },
  { sev: 'bad',  line: 'L3 · IND', title: 'Reject rate >2% último 60 min', time: '14:18' },
  { sev: 'warn', line: 'L2 · IND', title: 'OEE <85% durante 3 turnos consecutivos', time: '13:55' },
  { sev: 'warn', line: 'L5 · FEG', title: 'Cambio de formato excede objetivo (52 min)', time: '12:40' },
  { sev: 'info', line: 'L6 · SEI', title: 'TPM check pendiente — siguiente turno', time: '11:20' },
];

// ── OEE trend (14 shifts) ──
window.OEE_TREND = (() => {
  const shifts = [];
  const vals = [];
  const now = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 8 * 3600000);
    shifts.push(`${d.getMonth()+1}/${d.getDate()}\n${String(d.getHours()).padStart(2,'0')}:00`);
    vals.push(+(75 + Math.sin(i/2) * 6 + Math.random() * 8).toFixed(1));
  }
  return { shifts, vals };
})();

// ── Production vs target per line ──
window.PROD_VS_TARGET = [
  { line: 'L6 SEI', target: 12500, actual: 12100 },
  { line: 'L1 IND', target: 12000, actual: 11240 },
  { line: 'L2 IND', target: 12000, actual: 10980 },
  { line: 'L5 FEG', target: 10000, actual: 9080  },
  { line: 'L3 IND', target: 11000, actual: 8120  },
  { line: 'L4 ALB', target: 9600,  actual: 6400  },
];

// ── Stop categories ──
window.STOP_CAT = [
  { name: 'Mecánica',       value: 134 },
  { name: 'Cambio formato', value:  88 },
  { name: 'Eléctrica',      value:  62 },
  { name: 'Limpieza',       value:  45 },
  { name: 'Falta material', value:  28 },
  { name: 'Otras',          value:  16 },
];

// ── Site comparison (radial/bar) ──
window.SITE_OEE = [
  { site: 'Indianapolis', oee: 88.2, target: 85 },
  { site: 'Seishin',      oee: 91.4, target: 85 },
  { site: 'Sesto',        oee: 84.6, target: 85 },
  { site: 'Alcobendas',   oee: 79.8, target: 85 },
  { site: 'Fegersheim',   oee: 76.1, target: 85 },
];

// ── Heatmap data ──
window.HEATMAP = (() => {
  const days = ['Dom','Sáb','Vie','Jue','Mié','Mar','Lun'];
  const data = [];
  for (let d = 0; d < 7; d++) {
    for (let h = 0; h < 24; h++) {
      let base = 4;
      if (h >= 6 && h <= 7) base = 22;
      if (h >= 14 && h <= 15) base = 26;
      if (h >= 22 || h <= 1) base = 30;
      if (d === 0 || d === 6) base += 8;
      data.push([h, d, Math.max(0, Math.round(base + (Math.random() * 14 - 6)))]);
    }
  }
  return { days, hours: Array.from({length:24}, (_,i)=> String(i).padStart(2,'0')+':00'), data };
})();
