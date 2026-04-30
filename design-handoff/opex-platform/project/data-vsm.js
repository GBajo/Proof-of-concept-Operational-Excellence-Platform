// VSM data — packaging line steps (replicated from OpEx codebase)
window.VSM_LINES = [
  { id: 1, label: 'L1 · Autoinjectors' },
  { id: 2, label: 'L2 · Insulin pens' },
  { id: 3, label: 'L3 · Vials 10mL' },
  { id: 4, label: 'L4 · Blísteres' },
];

window.VSM_PHARMA_STEPS = [
  { order:1,  name:'Recepción granel', type:'non-value-add', nom_ct:45.0, nom_co:15 },
  { order:2,  name:'Alimentación',     type:'value-add',     nom_ct:8.0,  nom_co:20 },
  { order:3,  name:'Llenado',          type:'value-add',     nom_ct:6.0,  nom_co:45 },
  { order:4,  name:'Pesaje',           type:'value-add',     nom_ct:4.0,  nom_co:15 },
  { order:5,  name:'Cierre',           type:'value-add',     nom_ct:5.0,  nom_co:30 },
  { order:6,  name:'Etiquetado',       type:'value-add',     nom_ct:4.5,  nom_co:25 },
  { order:7,  name:'Serialización',    type:'value-add',     nom_ct:3.0,  nom_co:20 },
  { order:8,  name:'Estuchado',        type:'value-add',     nom_ct:6.5,  nom_co:35 },
  { order:9,  name:'Encajado',         type:'value-add',     nom_ct:12.0, nom_co:20 },
  { order:10, name:'Paletizado',       type:'non-value-add', nom_ct:18.0, nom_co:10 },
];

// deterministic per-line jitter
function _seed(s){ let x=s; return ()=> (x = (x*9301+49297) % 233280) / 233280; }

function _stepColor(status, ratio){
  if (status === 'stopped') return 'red';
  if (status === 'changeover') return 'blue';
  if (status === 'waiting') return 'gray';
  if (ratio > 1.25) return 'red';
  if (ratio > 1.10) return 'yellow';
  return 'green';
}

window.VSM_LINE_DATA = (() => {
  const out = {};
  const STATUSES = ['running','running','running','running','stopped','changeover','waiting'];
  window.VSM_LINES.forEach(line => {
    const rng = _seed(line.id * 137);
    const steps = window.VSM_PHARMA_STEPS.map((s, i) => {
      // a couple of bottlenecks per line — heavier jitter
      const isHeavy = (line.id + i) % 5 === 0;
      const jitter = 0.85 + rng() * (isHeavy ? 0.55 : 0.30);
      const actual = +(s.nom_ct * jitter).toFixed(2);
      const ratio = +(actual / s.nom_ct).toFixed(3);
      const status = STATUSES[Math.floor(rng()*STATUSES.length)];
      const wip = Math.floor(rng() * 80);
      // history (20 readings)
      const history = Array.from({length: 20}, (_, k) => ({
        t: `${String(8 + Math.floor(k/4)).padStart(2,'0')}:${String((k%4)*15).padStart(2,'0')}`,
        ct: +(s.nom_ct * (0.85 + rng() * 0.5)).toFixed(2),
      }));
      return {
        step_id: line.id*100 + s.order,
        step_order: s.order,
        step_name: s.name,
        step_type: s.type,
        nom_ct: s.nom_ct,
        nom_co: s.nom_co,
        actual_cycle_time: actual,
        ratio,
        units_in_wip: wip,
        status,
        defect_count: rng() < 0.2 ? Math.floor(rng()*3) : 0,
        color: _stepColor(status, ratio),
        history,
      };
    });
    // metrics
    let total=0, va=0, totalWip=0, maxR=0, bn='', running=0, defects=0;
    steps.forEach(s => {
      total += s.actual_cycle_time;
      if (s.step_type==='value-add') va += s.actual_cycle_time;
      totalWip += s.units_in_wip;
      defects += s.defect_count;
      if (s.ratio > maxR) { maxR = s.ratio; bn = s.step_name; }
      if (s.status==='running') running++;
    });
    const avail = (running / steps.length) * 100;
    const quality = Math.max(0, Math.min(100, (1 - defects / Math.max(totalWip,1)) * 100));
    out[line.id] = {
      steps,
      metrics: {
        lead_time_s: +total.toFixed(1),
        va_time_s: +va.toFixed(1),
        va_ratio_pct: +(va/total*100).toFixed(1),
        bottleneck: bn,
        total_wip: totalWip,
        oee_pct: +(avail*quality/100).toFixed(1),
      },
    };
  });
  return out;
})();

// multi-site comparison data
window.VSM_SITES = [
  { id:'ind', name:'Indianapolis', flag:'🇺🇸', factor: 1.00 },
  { id:'alb', name:'Alcobendas',   flag:'🇪🇸', factor: 1.18 },
  { id:'feg', name:'Fegersheim',   flag:'🇫🇷', factor: 1.07 },
  { id:'sei', name:'Seishin',      flag:'🇯🇵', factor: 0.92 },
];
window.VSM_COMPARE = (lineId) => {
  const baseLine = window.VSM_LINE_DATA[lineId];
  if (!baseLine) return { steps:[], sites:[] };
  const stepNames = baseLine.steps.map(s => s.step_name);
  const sites = window.VSM_SITES.map((site, idx) => {
    const rng = _seed(site.id.charCodeAt(0)*31 + lineId);
    const data = baseLine.steps.map(s => {
      const j = site.factor * (0.92 + rng() * 0.18);
      const actual = +(s.nom_ct * j).toFixed(2);
      const ratio = +(actual / s.nom_ct).toFixed(3);
      return { step_name: s.step_name, nom_ct: s.nom_ct, actual_cycle_time: actual, ratio };
    });
    let total=0, va=0;
    data.forEach((s,i) => {
      total += s.actual_cycle_time;
      if (baseLine.steps[i].step_type==='value-add') va += s.actual_cycle_time;
    });
    let maxR=0, bn='';
    data.forEach(s => { if (s.ratio>maxR) { maxR=s.ratio; bn=s.step_name; } });
    return {
      site_id: site.id, site_name: site.name, flag: site.flag, line: lineId, data,
      metrics: {
        lead_time_s: +total.toFixed(1),
        va_time_s:   +va.toFixed(1),
        va_ratio_pct:+(va/total*100).toFixed(1),
        bottleneck:  bn,
        oee_pct:     +(70 + rng()*25).toFixed(1),
      },
    };
  });
  return { steps: stepNames, sites };
};
