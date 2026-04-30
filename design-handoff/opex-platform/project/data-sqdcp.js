// SQDCP — Safety, Quality, Delivery, Cost, People
// Each pillar has 3 concentric rings: daily / weekly / monthly performance vs target.
window.SQDCP = [
  {
    key: 'S', label: 'Safety', color: '#2ecc71',
    icon: '⛨',
    desc: 'Días sin incidente · Near-miss · TRIR',
    metric: { name: 'Días sin LTI', value: 247, unit: 'días', target: 365 },
    rings: { daily: 100, weekly: 96, monthly: 91 },
    sub: [
      { l: 'Near-miss',  v: '7',    delta: '−2 vs sem.' },
      { l: 'TRIR',       v: '0.42', delta: '−0.08' },
      { l: 'Auditorías', v: '12/12' },
    ],
  },
  {
    key: 'Q', label: 'Quality', color: '#3fb6ff',
    icon: '✓',
    desc: 'Right First Time · Desviaciones · CAPAs',
    metric: { name: 'RFT', value: 98.6, unit: '%', target: 99.0 },
    rings: { daily: 99, weekly: 97, monthly: 95 },
    sub: [
      { l: 'Desviaciones',   v: '4',  delta: '+1 vs sem.' },
      { l: 'CAPAs abiertas', v: '11', delta: '−3' },
      { l: 'Rechazo',        v: '1.42%' },
    ],
  },
  {
    key: 'D', label: 'Delivery', color: '#f5a623',
    icon: '◈',
    desc: 'OTIF · Cumplimiento de plan · Backlog',
    metric: { name: 'OTIF', value: 94.2, unit: '%', target: 97.0 },
    rings: { daily: 92, weekly: 88, monthly: 85 },
    sub: [
      { l: 'Plan compl.',   v: '88%', delta: '−4pp' },
      { l: 'Backlog',       v: '6 ord.' },
      { l: 'Lead time',     v: '4.2 d', delta: '+0.3' },
    ],
  },
  {
    key: 'C', label: 'Cost', color: '#9b6eff',
    icon: '€',
    desc: 'Coste por unidad · Scrap · Energía',
    metric: { name: '€/unidad', value: 2.84, unit: '€', target: 2.70 },
    rings: { daily: 88, weekly: 92, monthly: 90 },
    sub: [
      { l: 'Scrap',     v: '0.9%', delta: '−0.2pp' },
      { l: 'Energía',   v: '142k kWh' },
      { l: 'Materiales',v: '+3.1%', delta: 'vs std' },
    ],
  },
  {
    key: 'P', label: 'People', color: '#ff5466',
    icon: '◉',
    desc: 'Asistencia · Formación · Engagement',
    metric: { name: 'Asistencia', value: 96.4, unit: '%', target: 98.0 },
    rings: { daily: 96, weekly: 94, monthly: 93 },
    sub: [
      { l: 'Formación',   v: '82%', delta: '+5pp' },
      { l: 'Sugerencias', v: '34',  delta: '+12' },
      { l: 'Engagement',  v: '7.8/10' },
    ],
  },
];

// trend by week (last 12 weeks) per pillar — for the bottom row
window.SQDCP_TREND = (() => {
  const weeks = Array.from({length: 12}, (_, i) => `W${i+1}`);
  function gen(base, jitter) {
    return weeks.map((_, i) => +(base + Math.sin(i/2) * jitter + (Math.random() - 0.5) * jitter).toFixed(1));
  }
  return {
    weeks,
    S: gen(95, 4),
    Q: gen(96, 3),
    D: gen(88, 6),
    C: gen(90, 5),
    P: gen(94, 3),
  };
})();
