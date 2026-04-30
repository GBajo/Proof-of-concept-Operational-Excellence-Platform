// Charts module — ECharts options for the OpEx dashboard
const PALETTE = {
  primary:  getCSS('--accent') || '#3fb6ff',
  good:     getCSS('--good')   || '#2ecc71',
  warn:     getCSS('--warn')   || '#f5a623',
  bad:      getCSS('--bad')    || '#ff5466',
  info:     getCSS('--info')   || '#3fb6ff',
  text:     getCSS('--text')   || '#e6edf6',
  textDim:  getCSS('--text-dim')|| '#8a9bb0',
  textFaint:getCSS('--text-faint')|| '#5e7186',
  grid:     getCSS('--line-mid')|| '#2e3f52',
  bgCard:   getCSS('--bg-elev') || '#243447',
  bgPanel:  getCSS('--bg-card') || '#1b2837',
};
function getCSS(v) {
  try { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  catch { return null; }
}
function oeeColor(v) { if (v >= 85) return PALETTE.good; if (v >= 70) return PALETTE.warn; return PALETTE.bad; }

const COMMON = {
  backgroundColor: 'transparent',
  textStyle: { color: PALETTE.textDim, fontFamily: 'Ringside, Inter, system-ui, sans-serif' },
  tooltip: {
    backgroundColor: PALETTE.bgPanel,
    borderColor: PALETTE.grid,
    textStyle: { color: PALETTE.text, fontSize: 12 },
    extraCssText: 'box-shadow: 0 12px 40px rgba(0,0,0,0.5); border-radius: 6px;',
  },
};

window.ChartFactory = {
  // ── Sparkline (KPI cards) ──
  sparkline(el, data, color) {
    const c = echarts.init(el, null, { renderer: 'svg' });
    c.setOption({
      animation: false,
      grid: { top: 2, bottom: 2, left: 2, right: 2 },
      xAxis: { type: 'category', show: false, data: data.map((_,i)=>i) },
      yAxis: { type: 'value', show: false, scale: true },
      series: [{
        type: 'line', data, smooth: true, symbol: 'none',
        lineStyle: { color, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0,0,0,1,[
            { offset: 0, color: color + '55' },
            { offset: 1, color: color + '00' },
          ]),
        },
      }],
      tooltip: { show: false },
    });
    return c;
  },

  // ── OEE Trend (14 shifts) ──
  oeeTrend(el) {
    const c = echarts.init(el, null, { renderer: 'svg' });
    const { shifts, vals } = window.OEE_TREND;
    c.setOption({
      ...COMMON,
      grid: { top: 24, right: 16, bottom: 38, left: 36 },
      tooltip: { ...COMMON.tooltip, trigger: 'axis',
        formatter: p => `<div style="font-size:10px;color:${PALETTE.textFaint};letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;">Turno ${p[0].name.replace('\n',' ')}</div>OEE: <b style="color:${oeeColor(p[0].value)}">${p[0].value}%</b>` },
      xAxis: {
        type: 'category', data: shifts, boundaryGap: false,
        axisLine: { lineStyle: { color: PALETTE.grid } },
        axisLabel: { color: PALETTE.textFaint, fontSize: 9, lineHeight: 12, interval: 1 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value', min: 60, max: 100, interval: 10,
        axisLine: { show: false },
        axisLabel: { color: PALETTE.textFaint, fontSize: 10, formatter: '{value}%' },
        splitLine: { lineStyle: { color: PALETTE.grid, type: 'dashed', opacity: 0.4 } },
      },
      series: [{
        type: 'line', data: vals.map(v => ({ value: v, itemStyle: { color: oeeColor(v) } })),
        smooth: true, symbol: 'circle', symbolSize: 7,
        lineStyle: { color: PALETTE.primary, width: 2.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0,0,0,1,[
            { offset: 0, color: PALETTE.primary + '40' },
            { offset: 1, color: PALETTE.primary + '00' },
          ]),
        },
        markLine: {
          silent: true, symbol: 'none',
          data: [{ yAxis: 85, lineStyle: { color: PALETTE.good, type: 'dashed', width: 1 },
            label: { formatter: 'Meta 85%', color: PALETTE.good, fontSize: 9, position: 'insideEndTop' } }],
        },
      }],
    });
    return c;
  },

  // ── Production vs Target (horizontal bars) ──
  prodVsTarget(el) {
    const c = echarts.init(el, null, { renderer: 'svg' });
    const data = window.PROD_VS_TARGET;
    c.setOption({
      ...COMMON,
      grid: { top: 28, right: 70, bottom: 8, left: 60 },
      tooltip: { ...COMMON.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: p => {
          const tgt = p.find(x=>x.seriesName==='Objetivo').value;
          const act = p.find(x=>x.seriesName==='Producido').value;
          const pct = ((act/tgt)*100).toFixed(1);
          return `<div style="font-size:11px;color:${PALETTE.text};margin-bottom:4px;font-weight:600;">${p[0].name}</div>
            <div style="font-size:11px;color:${PALETTE.textDim};">Objetivo: <b style="color:${PALETTE.text}">${tgt.toLocaleString('es-ES')}</b></div>
            <div style="font-size:11px;color:${PALETTE.textDim};">Producido: <b style="color:${PALETTE.text}">${act.toLocaleString('es-ES')}</b> (${pct}%)</div>`;
        } },
      legend: { data: ['Objetivo','Producido'], textStyle: { color: PALETTE.textDim, fontSize: 10 }, right: 0, top: 0,
        itemWidth: 10, itemHeight: 10, itemGap: 12 },
      xAxis: {
        type: 'value', max: 13000,
        axisLabel: { color: PALETTE.textFaint, fontSize: 10, formatter: v => v >= 1000 ? (v/1000).toFixed(0)+'k' : v },
        splitLine: { lineStyle: { color: PALETTE.grid, type: 'dashed', opacity: 0.4 } },
        axisLine: { show: false }, axisTick: { show: false },
      },
      yAxis: {
        type: 'category', data: data.map(d => d.line),
        axisLabel: { color: PALETTE.text, fontSize: 11, fontWeight: 600 },
        axisLine: { lineStyle: { color: PALETTE.grid } }, axisTick: { show: false },
      },
      series: [
        { name: 'Objetivo', type: 'bar', barGap: '-100%', barCategoryGap: '45%',
          data: data.map(d => d.target),
          itemStyle: { color: 'rgba(255,255,255,0.06)', borderRadius: [0,3,3,0] }, z: 1 },
        { name: 'Producido', type: 'bar', barCategoryGap: '45%',
          data: data.map(d => {
            const pct = d.actual / d.target;
            const col = pct >= 0.95 ? PALETTE.good : pct >= 0.80 ? PALETTE.warn : PALETTE.bad;
            return { value: d.actual, itemStyle: { color: col, borderRadius: [0,3,3,0] } };
          }),
          label: { show: true, position: 'right', color: PALETTE.text, fontSize: 10, fontWeight: 700,
            formatter: p => p.value.toLocaleString('es-ES') },
          z: 2 },
      ],
    });
    return c;
  },

  // ── Stop categories (donut) ──
  stopDonut(el) {
    const c = echarts.init(el, null, { renderer: 'svg' });
    const colors = [PALETTE.bad, PALETTE.warn, '#9b6eff', PALETTE.info, '#2cc4b4', PALETTE.textFaint];
    const total = window.STOP_CAT.reduce((s,d)=>s+d.value, 0);
    c.setOption({
      ...COMMON, color: colors,
      tooltip: { ...COMMON.tooltip, trigger: 'item', formatter: '{b}: <b>{c} min</b> ({d}%)' },
      legend: { orient: 'vertical', right: 8, top: 'center',
        textStyle: { color: PALETTE.textMid || PALETTE.text, fontSize: 10 },
        icon: 'circle', itemWidth: 8, itemHeight: 8, itemGap: 8,
        formatter: name => {
          const item = window.STOP_CAT.find(x=>x.name===name);
          return `${name}  {v|${item.value}m}`;
        },
        textStyle: { color: PALETTE.text, fontSize: 11, rich: { v: { color: PALETTE.textFaint, fontSize: 10 } } },
      },
      series: [{
        type: 'pie', radius: ['58%','78%'], center: ['32%','50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 4, borderColor: PALETTE.bgPanel, borderWidth: 2 },
        label: { show: true, position: 'center',
          formatter: () => `{v|${total}}\n{l|min totales}`,
          rich: {
            v: { color: PALETTE.text, fontSize: 22, fontWeight: 800, fontFamily: 'Ringside Wide, Ringside, sans-serif', lineHeight: 26 },
            l: { color: PALETTE.textFaint, fontSize: 10, letterSpacing: 1 },
          } },
        labelLine: { show: false },
        emphasis: { scale: true, scaleSize: 4, label: { show: true, formatter: '{b}\n{d}%',
          rich: { b: { color: PALETTE.text, fontSize: 12 }, d: { color: PALETTE.textFaint, fontSize: 10 } } } },
        data: window.STOP_CAT,
      }],
    });
    return c;
  },

  // ── Sites OEE bar ──
  sitesBar(el) {
    const c = echarts.init(el, null, { renderer: 'svg' });
    const data = window.SITE_OEE;
    c.setOption({
      ...COMMON,
      grid: { top: 16, right: 28, bottom: 8, left: 90 },
      tooltip: { ...COMMON.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: {
        type: 'value', min: 60, max: 100,
        axisLabel: { color: PALETTE.textFaint, fontSize: 10, formatter: '{value}%' },
        splitLine: { lineStyle: { color: PALETTE.grid, type: 'dashed', opacity: 0.4 } },
        axisLine: { show: false }, axisTick: { show: false },
      },
      yAxis: {
        type: 'category', data: data.map(d => d.site),
        axisLabel: { color: PALETTE.text, fontSize: 11, fontWeight: 600 },
        axisLine: { lineStyle: { color: PALETTE.grid } }, axisTick: { show: false },
      },
      series: [{
        type: 'bar', barCategoryGap: '50%',
        data: data.map(d => ({ value: d.oee, itemStyle: { color: oeeColor(d.oee), borderRadius: [0,3,3,0] } })),
        label: { show: true, position: 'right', color: PALETTE.text, fontSize: 10, fontWeight: 700, formatter: '{c}%' },
        markLine: {
          silent: true, symbol: 'none',
          data: [{ xAxis: 85, lineStyle: { color: PALETTE.good, type: 'dashed', width: 1 },
            label: { formatter: 'Meta', color: PALETTE.good, fontSize: 9, position: 'insideEndTop' } }],
        },
      }],
    });
    return c;
  },

  // ── Heatmap ──
  heatmap(el) {
    const c = echarts.init(el, null, { renderer: 'svg' });
    const { days, hours, data } = window.HEATMAP;
    c.setOption({
      ...COMMON,
      grid: { top: 16, right: 24, bottom: 38, left: 38 },
      tooltip: { ...COMMON.tooltip, position: 'top',
        formatter: p => `${days[p.data[1]]} ${hours[p.data[0]]}<br/>Paradas: <b>${p.data[2]} min</b>` },
      xAxis: {
        type: 'category', data: hours,
        axisLabel: { color: PALETTE.textFaint, fontSize: 9, interval: 2 },
        axisLine: { lineStyle: { color: PALETTE.grid } }, axisTick: { show: false },
        splitArea: { show: false },
      },
      yAxis: {
        type: 'category', data: days,
        axisLabel: { color: PALETTE.text, fontSize: 10 },
        axisLine: { lineStyle: { color: PALETTE.grid } }, axisTick: { show: false },
      },
      visualMap: {
        min: 0, max: 40, calculable: false, show: false,
        inRange: { color: ['#1a2535', PALETTE.info + '88', PALETTE.warn, PALETTE.bad] },
      },
      series: [{
        type: 'heatmap', data,
        itemStyle: { borderRadius: 2, borderColor: PALETTE.bgPanel, borderWidth: 1 },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.6)' } },
      }],
    });
    return c;
  },
};
