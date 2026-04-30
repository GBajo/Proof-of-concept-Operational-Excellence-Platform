// VSM screen — Value Stream Map (replicated from OpEx codebase)
const { useState: useStateVSM, useEffect: useEffectVSM, useRef: useRefVSM } = React;

const VSM_COLOR_MAP = {
  green:  { fill:'#1c3a2a', stroke:'#2ecc71', text:'#7be3a4' },
  yellow: { fill:'#3a2f12', stroke:'#f5a623', text:'#f5c97a' },
  red:    { fill:'#3a1a1f', stroke:'#ff5466', text:'#ffa3ae' },
  blue:   { fill:'#152a3d', stroke:'#3fb6ff', text:'#8fd3ff' },
  gray:   { fill:'#1f2a38', stroke:'#5e7186', text:'#a4b3c4' },
};
const VSM_STATUS_COLOR = { running:'#2ecc71', stopped:'#ff5466', changeover:'#3fb6ff', waiting:'#5e7186' };
const VSM_STATUS_LABEL = { running:'▶ RUN', stopped:'■ STOP', changeover:'⟳ C/O', waiting:'◌ WAIT' };

function fmtCT(s) {
  if (s == null) return '—';
  return s >= 60 ? `${Math.round(s/60)}m${Math.round(s%60)}s` : `${(+s).toFixed(1)}s`;
}

function VSMSvg({ steps, onStepClick }) {
  const ref = useRefVSM(null);
  useEffectVSM(() => {
    const svg = ref.current;
    if (!svg) return;
    const STEP_W = 130, STEP_H = 96, STEP_GAP = 70;
    const SVG_TOP = 60, STEP_Y = SVG_TOP + 20, TL_Y = STEP_Y + STEP_H + 30;
    const SVG_H = TL_Y + 70;
    const n = steps.length;
    const startX = 80;
    const lastX = startX + (n-1) * (STEP_W + STEP_GAP);
    const totalW = lastX + STEP_W + 80;
    svg.setAttribute('width', Math.max(totalW, 900));
    svg.setAttribute('height', SVG_H);
    svg.setAttribute('viewBox', `0 0 ${Math.max(totalW,900)} ${SVG_H}`);
    svg.innerHTML = '';
    const NS = 'http://www.w3.org/2000/svg';
    const el = (t, a={}) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
    const txt = (s, x, y, a={}) => { const e = el('text', { x, y, 'text-anchor':'middle', ...a }); e.textContent = s; return e; };

    // bg
    svg.appendChild(el('rect', { x:0, y:0, width: Math.max(totalW,900), height: SVG_H, fill:'#0e151f', rx:8 }));

    // supplier / customer
    const actor = (x, y, label, icon) => {
      const g = el('g');
      g.appendChild(el('rect', { x, y, width:46, height:46, fill:'#16202d', stroke:'#3a4d63', 'stroke-width':1.5, rx:4 }));
      const t = el('text', { x: x+23, y: y+30, 'text-anchor':'middle', 'font-size':22 }); t.textContent = icon; g.appendChild(t);
      g.appendChild(txt(label, x+23, y+62, { 'font-size':10, fill:'#8a9bb0', 'font-weight':600 }));
      svg.appendChild(g);
    };
    actor(10, STEP_Y, 'Proveedor', '📦');
    actor(lastX + STEP_W + 18, STEP_Y, 'Cliente', '🏭');

    // timeline base
    svg.appendChild(el('line', { x1:startX, y1:TL_Y+10, x2:lastX+STEP_W, y2:TL_Y+10, stroke:'#3a4d63', 'stroke-width':2 }));

    let tlX = startX;
    steps.forEach((step, i) => {
      const boxX = startX + i * (STEP_W + STEP_GAP);
      const c = VSM_COLOR_MAP[step.color] || VSM_COLOR_MAP.gray;
      // process box
      const g = el('g', { 'data-step-id': step.step_id, style:'cursor:pointer' });
      g.appendChild(el('rect', { x:boxX, y:STEP_Y, width:STEP_W, height:STEP_H, fill:c.fill, stroke:c.stroke, 'stroke-width':2, rx:6 }));
      // status bar bottom
      const bar = VSM_STATUS_COLOR[step.status] || '#5e7186';
      g.appendChild(el('rect', { x:boxX, y:STEP_Y+STEP_H-16, width:STEP_W, height:16, fill:bar, rx:4 }));
      // name
      g.appendChild(txt(step.step_name, boxX+STEP_W/2, STEP_Y+20, { 'font-size':11, 'font-weight':700, fill:c.text, 'font-family':'Ringside, sans-serif' }));
      // metrics
      const ctV = fmtCT(step.actual_cycle_time);
      const coV = step.nom_co ? `${step.nom_co}m` : '—';
      const wipV = step.units_in_wip != null ? step.units_in_wip : '—';
      [`C/T: ${ctV}`, `C/O: ${coV}`, `WIP: ${wipV}`].forEach((line, idx) => {
        g.appendChild(txt(line, boxX+STEP_W/2, STEP_Y+42+idx*13, { 'font-size':10, fill:c.text, 'font-family':'JetBrains Mono, monospace' }));
      });
      // status label
      g.appendChild(txt(VSM_STATUS_LABEL[step.status] || '◌ WAIT', boxX+STEP_W/2, STEP_Y+STEP_H-4, { 'font-size':9, fill:'#fff', 'font-weight':700, 'letter-spacing':'0.05em' }));
      g.addEventListener('click', () => onStepClick(step));
      svg.appendChild(g);

      // timeline cell
      const ctSec = step.actual_cycle_time || step.nom_ct;
      const isVA = step.step_type === 'value-add';
      const tlW = Math.max(10, Math.min(STEP_W, ctSec * 2.5));
      svg.appendChild(el('rect', { x:tlX, y:TL_Y, width:tlW, height:20, fill: isVA ? '#1c3a2a':'#3a1a1f', rx:3, stroke: isVA?'#2ecc71':'#ff5466', 'stroke-width':1 }));
      svg.appendChild(txt(fmtCT(ctSec), tlX+tlW/2, TL_Y+14, { 'font-size':9, fill: isVA?'#7be3a4':'#ffa3ae', 'font-weight':600 }));
      tlX += tlW + Math.max(0, STEP_GAP - tlW);

      // arrow + WIP triangle
      if (i < n-1) {
        const ax = boxX + STEP_W;
        const am = ax + STEP_GAP/2;
        const ay = STEP_Y + STEP_H/2;
        const len = STEP_GAP - 8;
        const ah = 10, sh = 8;
        const pts = `${ax+4},${ay-sh/2} ${ax+4+len-ah},${ay-sh/2} ${ax+4+len-ah},${ay-sh} ${ax+4+len},${ay} ${ax+4+len-ah},${ay+sh} ${ax+4+len-ah},${ay+sh/2} ${ax+4},${ay+sh/2}`;
        svg.appendChild(el('polygon', { points:pts, fill:'#5e7186' }));
        // WIP triangle
        const tri = el('g');
        const tx = am, ty = STEP_Y - 8, sz = 18;
        tri.appendChild(el('polygon', { points:`${tx},${ty-sz} ${tx-sz},${ty+4} ${tx+sz},${ty+4}`, fill:'#3a2f12', stroke:'#f5a623', 'stroke-width':1.5 }));
        tri.appendChild(txt(step.units_in_wip, tx, ty+1, { 'font-size':9, fill:'#f5c97a', 'font-weight':700 }));
        svg.appendChild(tri);
      }
    });

    // VA/NVA legend
    svg.appendChild(txt('← VA / NVA →', (startX + lastX+STEP_W)/2, TL_Y+44, { 'font-size':10, fill:'#8a9bb0', 'font-style':'italic' }));
  }, [steps]);
  return <svg ref={ref} style={{ display:'block', minWidth:'100%' }} />;
}

function VSMDetail({ step, onClose }) {
  const ref = useRefVSM(null);
  useEffectVSM(() => {
    if (!step || !ref.current) return;
    const c = echarts.init(ref.current, null, { renderer:'svg' });
    c.setOption({
      backgroundColor:'transparent',
      grid:{ top:8, right:8, bottom:36, left:36 },
      tooltip:{ trigger:'axis', backgroundColor:'#1b2837', borderColor:'#3a4d63', textStyle:{ color:'#e6edf6', fontSize:11 } },
      legend:{ bottom:0, textStyle:{ color:'#8a9bb0', fontSize:10 }, data:['C/T real','Nominal'] },
      xAxis:{ type:'category', data: step.history.map(h=>h.t), axisLabel:{ color:'#5e7186', fontSize:9 }, axisLine:{ lineStyle:{ color:'#3a4d63' } } },
      yAxis:{ type:'value', name:'seg', nameTextStyle:{ color:'#8a9bb0', fontSize:9 }, axisLabel:{ color:'#5e7186', fontSize:9 }, splitLine:{ lineStyle:{ color:'#243447', type:'dashed' } } },
      series:[
        { name:'C/T real', type:'line', smooth:true, data: step.history.map(h=>h.ct), lineStyle:{ color:'#3fb6ff', width:2 }, itemStyle:{ color:'#3fb6ff' }, areaStyle:{ color:'rgba(63,182,255,0.15)' } },
        { name:'Nominal', type:'line', symbol:'none', data: step.history.map(()=>step.nom_ct), lineStyle:{ color:'#f5a623', type:'dashed', width:1.5 } },
      ],
    });
    return () => c.dispose();
  }, [step]);
  if (!step) return null;
  return (
    <div className="vsm-detail-overlay" onClick={(e)=>{ if(e.target.classList.contains('vsm-detail-overlay')) onClose(); }}>
      <div className="vsm-detail-panel">
        <div className="vsm-detail-header">
          <h3>{step.step_name}</h3>
          <button className="icon-btn" onClick={onClose} style={{ width:28, height:28 }}>×</button>
        </div>
        <div className="vsm-detail-kpis">
          <div className="vsm-kpi-chip"><span className="v t-num">{fmtCT(step.actual_cycle_time)}</span><span className="l">C/T actual</span></div>
          <div className="vsm-kpi-chip"><span className="v t-num">{step.units_in_wip}</span><span className="l">WIP</span></div>
          <div className="vsm-kpi-chip"><span className="v t-num">{step.defect_count}</span><span className="l">Defectos</span></div>
        </div>
        <div className="vsm-detail-section">
          <p className="vsm-detail-section-title">Historial C/T (últimas 20 lecturas)</p>
          <div ref={ref} style={{ width:'100%', height:180 }} />
        </div>
        <div className="vsm-detail-section">
          <p className="vsm-detail-section-title">Diagnóstico</p>
          <div className="vsm-ai-response">
            {step.ratio > 1.25
              ? `C/T ${(step.ratio*100-100).toFixed(0)}% sobre nominal. Posible cuello de botella; revisar cambio de formato y ajuste de máquina.`
              : step.ratio > 1.10
                ? `C/T ligeramente alto (×${step.ratio.toFixed(2)}). Monitorizar próximas lecturas.`
                : `Operación dentro de rango nominal.`}
          </div>
        </div>
      </div>
    </div>
  );
}

function VSMCompare({ lineId }) {
  const chartRef = useRefVSM(null);
  const data = React.useMemo(() => window.VSM_COMPARE(lineId), [lineId]);
  useEffectVSM(() => {
    if (!chartRef.current) return;
    const SITE_COLORS = ['#3fb6ff','#f5a623','#2ecc71','#ff5466'];
    const c = echarts.init(chartRef.current, null, { renderer:'svg' });
    const series = [
      { name:'Nominal', type:'bar', data: data.sites[0].data.map(s=>+s.nom_ct.toFixed(1)),
        itemStyle:{ color:'#3a4d63', borderRadius:[3,3,0,0] } },
      ...data.sites.map((site, i) => ({
        name: `${site.flag} ${site.site_name}`, type:'bar',
        data: site.data.map(s => {
          const col = s.ratio > 1.25 ? '#ff5466' : s.ratio > 1.10 ? '#f5a623' : SITE_COLORS[i];
          return { value:+s.actual_cycle_time.toFixed(1), itemStyle:{ color: col, borderRadius:[3,3,0,0] } };
        }),
      })),
    ];
    c.setOption({
      backgroundColor:'transparent',
      tooltip:{ trigger:'axis', axisPointer:{ type:'shadow' }, backgroundColor:'#1b2837', borderColor:'#3a4d63', textStyle:{ color:'#e6edf6', fontSize:11 } },
      legend:{ bottom:0, textStyle:{ color:'#8a9bb0', fontSize:10 } },
      grid:{ top:16, right:16, bottom:50, left:46 },
      xAxis:{ type:'category', data: data.steps, axisLabel:{ color:'#5e7186', fontSize:9, rotate:30, interval:0 }, axisLine:{ lineStyle:{ color:'#3a4d63' } } },
      yAxis:{ type:'value', name:'C/T (s)', nameTextStyle:{ color:'#8a9bb0', fontSize:9 }, axisLabel:{ color:'#5e7186', fontSize:9 }, splitLine:{ lineStyle:{ color:'#243447', type:'dashed' } } },
      series,
    });
    const onR = () => c.resize(); window.addEventListener('resize', onR);
    return () => { window.removeEventListener('resize', onR); c.dispose(); };
  }, [data]);
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="panel__head">
        <div>
          <span className="panel__title">Comparativa multi-planta</span>
          <span className="panel__sub">C/T por paso · línea L{lineId} · {data.sites.length} plantas</span>
        </div>
        <span className="chip chip--info">Multi-site</span>
      </div>
      <div className="panel__body">
        <div ref={chartRef} style={{ width:'100%', height:340 }} />
        <table className="vsm-compare-table">
          <thead>
            <tr><th>Planta</th><th>Lead time</th><th>VA time</th><th>VA ratio</th><th>Cuello botella</th><th>OEE</th></tr>
          </thead>
          <tbody>
            {data.sites.map(s => {
              const r = s.metrics.va_ratio_pct;
              const cls = r>=60?'good':r>=40?'warn':'bad';
              return (
                <tr key={s.site_id}>
                  <td><strong>{s.flag} {s.site_name}</strong></td>
                  <td className="t-num">{fmtCT(s.metrics.lead_time_s)}</td>
                  <td className="t-num">{fmtCT(s.metrics.va_time_s)}</td>
                  <td><span className={`chip chip--${cls}`}>{r}%</span></td>
                  <td><span className="chip chip--bad">{s.metrics.bottleneck}</span></td>
                  <td className="t-num"><strong>{s.metrics.oee_pct}%</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VSMPage() {
  const [lineId, setLineId] = useStateVSM(1);
  const [activeStep, setActiveStep] = useStateVSM(null);
  const [showCompare, setShowCompare] = useStateVSM(false);
  const lineData = window.VSM_LINE_DATA[lineId];
  const m = lineData.metrics;

  const kpis = [
    { ic:'⏱', val: fmtCT(m.lead_time_s), lbl:'Lead time',  status:'info' },
    { ic:'✓', val: fmtCT(m.va_time_s),   lbl:'VA time',     status:'good' },
    { ic:'%', val: m.va_ratio_pct+'%',   lbl:'VA ratio',    status: m.va_ratio_pct>=60?'good':m.va_ratio_pct>=40?'warn':'bad' },
    { ic:'⚠', val: m.bottleneck || '—',  lbl:'Cuello botella', status:'bad' },
    { ic:'▦', val: m.total_wip+' uds',   lbl:'WIP total',   status:'info' },
    { ic:'◐', val: m.oee_pct+'%',        lbl:'OEE',         status: m.oee_pct>=85?'good':m.oee_pct>=70?'warn':'bad' },
  ];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Value Stream Map <span className="chip chip--info" style={{ marginLeft:8, verticalAlign:'middle' }}>VSM</span></h1>
          <p className="page-head__sub">
            Mapa de flujo · empaquetado farmacéutico · 10 pasos · datos en vivo
          </p>
        </div>
        <div className="page-head__actions">
          <select value={lineId} onChange={e=>setLineId(+e.target.value)}
            style={{ background:'var(--bg-card)', border:'1px solid var(--line-mid)', color:'var(--text)',
              borderRadius:6, padding:'6px 10px', fontSize:12, fontFamily:'inherit' }}>
            {window.VSM_LINES.map(l => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
          <span className="live-pulse"><span className="live-pulse__dot" />Live</span>
          <button className="icon-btn" onClick={()=>setShowCompare(s=>!s)} title="Comparar plantas">
            {showCompare ? '▼' : '▶'}
          </button>
        </div>
      </div>

      <div className="page">
        <div className="panel">
          <div className="panel__head">
            <div>
              <span className="panel__title">Mapa de flujo · L{lineId}</span>
              <span className="panel__sub">click en cualquier paso para ver detalle</span>
            </div>
            <div style={{ display:'flex', gap:6 }}>
              <span className="chip chip--good">VA</span>
              <span className="chip chip--bad">NVA</span>
              <span className="chip chip--warn">WIP</span>
            </div>
          </div>
          <div className="panel__body" style={{ overflowX:'auto', background:'#0a1018', borderRadius:6, padding:12 }}>
            <VSMSvg steps={lineData.steps} onStepClick={setActiveStep} />
          </div>
        </div>

        <div className="vsm-kpi-row">
          {kpis.map((k,i) => (
            <div key={i} className={`kpi kpi--${k.status}`}>
              <div className="kpi__head">
                <span className="kpi__label">{k.lbl}</span>
                <span className="kpi__icon">{k.ic}</span>
              </div>
              <div className="kpi__value-row">
                <span className="kpi__value t-num" style={{ fontSize: k.lbl==='Cuello botella' ? 16 : 26 }}>{k.val}</span>
              </div>
            </div>
          ))}
        </div>

        {showCompare && <VSMCompare lineId={lineId} />}
      </div>

      {activeStep && <VSMDetail step={activeStep} onClose={()=>setActiveStep(null)} />}
    </>
  );
}

window.VSMPage = VSMPage;
