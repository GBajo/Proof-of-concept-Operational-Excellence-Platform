// SQDCP screen — Safety, Quality, Delivery, Cost, People
// Concentric rings (daily/weekly/monthly) per pillar.

const { useEffect: useEffectSQ, useRef: useRefSQ } = React;

function SQDCPRing({ pillar }) {
  const ref = useRefSQ(null);

  useEffectSQ(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, null, { renderer: 'svg' });
    const col = pillar.color;

    // Three concentric ring "gauges" — pie series with one filled segment
    function ringSeries(value, radiusOuter, radiusInner) {
      return {
        type: 'pie',
        radius: [radiusInner, radiusOuter],
        center: ['50%', '50%'],
        startAngle: 90,
        silent: true,
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data: [
          { value, itemStyle: { color: col, borderRadius: 4 } },
          { value: 100 - value, itemStyle: { color: 'rgba(255,255,255,0.05)', borderRadius: 4 } },
        ],
      };
    }

    c.setOption({
      backgroundColor: 'transparent',
      tooltip: { show: false },
      // outer = monthly, mid = weekly, inner = daily
      series: [
        ringSeries(pillar.rings.monthly, '92%', '78%'),
        ringSeries(pillar.rings.weekly,  '74%', '60%'),
        ringSeries(pillar.rings.daily,   '56%', '42%'),
      ],
      graphic: [
        // center letter
        { type: 'text', left: 'center', top: 'center',
          style: {
            text: pillar.key,
            fill: col,
            font: '800 38px "Ringside Wide", "Ringside", sans-serif',
            textAlign: 'center', textVerticalAlign: 'middle',
          } },
      ],
    });
    const onR = () => c.resize();
    window.addEventListener('resize', onR);
    return () => { window.removeEventListener('resize', onR); c.dispose(); };
  }, [pillar]);

  return <div ref={ref} className="sqdcp-ring__chart" />;
}

function SQDCPCard({ pillar }) {
  const overall = Math.round((pillar.rings.daily + pillar.rings.weekly + pillar.rings.monthly) / 3);
  const status = overall >= 95 ? 'good' : overall >= 85 ? 'warn' : 'bad';
  return (
    <div className={`sqdcp-card sqdcp-card--${status}`} style={{ '--pillar': pillar.color }}>
      <div className="sqdcp-card__head">
        <div className="sqdcp-card__icon" style={{ background: pillar.color + '22', color: pillar.color }}>
          {pillar.icon}
        </div>
        <div className="sqdcp-card__head-text">
          <div className="sqdcp-card__label">{pillar.label}</div>
          <div className="sqdcp-card__desc">{pillar.desc}</div>
        </div>
      </div>

      <div className="sqdcp-ring">
        <SQDCPRing pillar={pillar} />
        <div className="sqdcp-ring__legend">
          <div className="sqdcp-ring__legend-row">
            <span className="sqdcp-ring__sw" style={{ background: pillar.color, opacity: 0.45 }} />
            <span className="l">Mensual</span>
            <span className="v">{pillar.rings.monthly}%</span>
          </div>
          <div className="sqdcp-ring__legend-row">
            <span className="sqdcp-ring__sw" style={{ background: pillar.color, opacity: 0.7 }} />
            <span className="l">Semanal</span>
            <span className="v">{pillar.rings.weekly}%</span>
          </div>
          <div className="sqdcp-ring__legend-row">
            <span className="sqdcp-ring__sw" style={{ background: pillar.color }} />
            <span className="l">Diario</span>
            <span className="v">{pillar.rings.daily}%</span>
          </div>
        </div>
      </div>

      <div className="sqdcp-card__primary">
        <span className="t-eyebrow">{pillar.metric.name}</span>
        <div className="sqdcp-card__primary-row">
          <span className="sqdcp-card__primary-v t-num">{pillar.metric.value}</span>
          <span className="sqdcp-card__primary-u">{pillar.metric.unit}</span>
          <span className="sqdcp-card__primary-t">meta {pillar.metric.target}</span>
        </div>
      </div>

      <div className="sqdcp-card__sub">
        {pillar.sub.map((s, i) => (
          <div key={i} className="sqdcp-card__sub-row">
            <span className="sqdcp-card__sub-l">{s.l}</span>
            <span className="sqdcp-card__sub-v t-num">{s.v}</span>
            {s.delta && <span className="sqdcp-card__sub-d">{s.delta}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function SQDCPTrend() {
  const ref = useRefSQ(null);
  useEffectSQ(() => {
    const c = echarts.init(ref.current, null, { renderer: 'svg' });
    const t = window.SQDCP_TREND;
    const series = window.SQDCP.map(p => ({
      name: p.label, type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
      data: t[p.key], lineStyle: { color: p.color, width: 2 },
      itemStyle: { color: p.color },
    }));
    c.setOption({
      backgroundColor: 'transparent',
      grid: { top: 28, right: 16, bottom: 28, left: 38 },
      tooltip: { trigger: 'axis',
        backgroundColor: getCss('--bg-card'), borderColor: getCss('--line-mid'),
        textStyle: { color: getCss('--text'), fontSize: 12 },
        extraCssText: 'box-shadow: var(--shadow-pop); border-radius: 6px;' },
      legend: { data: window.SQDCP.map(p => p.label),
        textStyle: { color: getCss('--text-dim'), fontSize: 11 },
        icon: 'circle', itemWidth: 8, itemHeight: 8, top: 0, right: 0 },
      xAxis: { type: 'category', data: t.weeks,
        axisLine: { lineStyle: { color: getCss('--line-mid') } },
        axisLabel: { color: getCss('--text-faint'), fontSize: 10 },
        axisTick: { show: false } },
      yAxis: { type: 'value', min: 70, max: 100,
        axisLine: { show: false },
        axisLabel: { color: getCss('--text-faint'), fontSize: 10, formatter: '{value}%' },
        splitLine: { lineStyle: { color: getCss('--line-mid'), type: 'dashed', opacity: 0.4 } } },
      series,
    });
    const onR = () => c.resize();
    window.addEventListener('resize', onR);
    return () => { window.removeEventListener('resize', onR); c.dispose(); };
  }, []);
  return <div ref={ref} style={{ width: '100%', height: 280 }} />;
}

function SQDCPPage() {
  const overallDaily = Math.round(window.SQDCP.reduce((s,p)=>s+p.rings.daily, 0) / window.SQDCP.length);
  const overallStatus = overallDaily >= 95 ? 'good' : overallDaily >= 85 ? 'warn' : 'bad';
  return (
    <>
      <div className="page-head">
        <div>
          <h1>SQDCP — Tablero diario</h1>
          <p className="page-head__sub">
            Seguridad · Calidad · Entrega · Coste · Personas — turno actual <strong>T2 · 14:00</strong>
          </p>
        </div>
        <div className="page-head__actions">
          <div className="seg">
            {['Diario','Semanal','Mensual'].map((r,i) => (
              <button key={r} className={i===0?'active':''}>{r}</button>
            ))}
          </div>
          <div className={`chip chip--${overallStatus}`}>
            Score global · {overallDaily}%
          </div>
          <button className="icon-btn" title="Exportar">⬇</button>
        </div>
      </div>

      <div className="page">
        <div className="sqdcp-grid">
          {window.SQDCP.map(p => <SQDCPCard key={p.key} pillar={p} />)}
        </div>

        <div className="panel">
          <div className="panel__head">
            <div>
              <span className="panel__title">Evolución 12 semanas</span>
              <span className="panel__sub">% cumplimiento por pilar</span>
            </div>
            <span className="chip chip--ghost">Semanal</span>
          </div>
          <div className="panel__body"><SQDCPTrend /></div>
        </div>
      </div>
    </>
  );
}

window.SQDCPPage = SQDCPPage;
