/* OpEx Pharma — App logic */
(function () {
  // ===== Screen routing =====
  const screens = document.querySelectorAll('.pp-screen[data-screen]');
  const links   = document.querySelectorAll('[data-go]');

  function go(name) {
    screens.forEach(s => s.classList.toggle('active', s.dataset.screen === name));
    document.querySelectorAll('.pp-side-item[data-go]').forEach(l => {
      l.classList.toggle('active', l.dataset.go === name);
    });
    // Resize charts on the new screen
    setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  window.ppGo = go;

  links.forEach(l => l.addEventListener('click', e => {
    e.preventDefault(); go(l.dataset.go);
  }));

  // ===== Charts =====
  const echarts = window.echarts;
  if (!echarts) return;

  const COLOR_TEXT = '#1a1816';
  const COLOR_DIM  = '#6b6661';
  const COLOR_LINE = '#ece8e2';
  const COLOR_RED  = '#d52b1e';
  const COLOR_GOOD = '#2d7a3a';
  const COLOR_WARN = '#d68910';
  const COLOR_INFO = '#1f6391';

  const FONT_SANS    = 'Ringside, Inter, sans-serif';
  const FONT_DISPLAY = '"Ringside Wide", Ringside, sans-serif';

  function baseAxis(opts = {}) {
    return {
      axisLine: { lineStyle: { color: COLOR_LINE }},
      axisTick: { show: false },
      axisLabel: { color: COLOR_DIM, fontFamily: FONT_SANS, fontSize: 11, ...opts.label },
      splitLine: { lineStyle: { color: COLOR_LINE }},
      ...opts.extra,
    };
  }

  function tooltip() {
    return {
      backgroundColor: '#ffffff',
      borderColor: COLOR_LINE,
      textStyle: { color: COLOR_TEXT, fontFamily: FONT_SANS, fontSize: 12 },
      padding: [8, 12],
    };
  }

  // ── Dashboard: OEE 24h ─────────────────────────────────────
  function chartOee24h(el) {
    const c = echarts.init(el);
    const hours = Array.from({length: 12}, (_,i) => `${String(i*2).padStart(2,'0')}:00`);
    c.setOption({
      grid: { left: 48, right: 24, top: 24, bottom: 36 },
      tooltip: { trigger: 'axis', ...tooltip() },
      xAxis: { type: 'category', data: hours, ...baseAxis() },
      yAxis: { type: 'value', min: 60, max: 100, ...baseAxis({ label: { formatter: '{value}%' }, extra: { axisLine: { show: false }}}) },
      series: [{
        type: 'line', smooth: true, symbol: 'circle', symbolSize: 6,
        data: [78,82,84,85,83,86,88,87,84,86,89,85],
        lineStyle: { color: COLOR_RED, width: 2.5 },
        itemStyle: { color: COLOR_RED },
        areaStyle: { color: { type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[
          {offset:0,color:'rgba(213,43,30,0.18)'},
          {offset:1,color:'rgba(213,43,30,0.00)'}
        ]}},
        markLine: {
          symbol: 'none', silent: true,
          lineStyle: { color: '#9b9690', type: 'dashed' },
          data: [{ yAxis: 85, label: { formatter: 'Objetivo 85%', color: COLOR_DIM, fontFamily: FONT_SANS, fontSize: 10 }}]
        },
      }]
    });
    return c;
  }

  // ── Dashboard: Producción vs objetivo ──────────────────────
  function chartProd(el) {
    const c = echarts.init(el);
    const days = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
    c.setOption({
      grid: { left: 48, right: 16, top: 24, bottom: 36 },
      tooltip: { trigger: 'axis', ...tooltip() },
      legend: { data: ['Real','Objetivo'], right: 0, top: 0, textStyle: { color: COLOR_DIM, fontFamily: FONT_SANS, fontSize: 11 }},
      xAxis: { type: 'category', data: days, ...baseAxis() },
      yAxis: { type: 'value', ...baseAxis({ extra: { axisLine: { show: false }}}) },
      series: [
        { name: 'Real', type: 'bar', data: [128,135,142,138,145,118,128], barWidth: 22, itemStyle: { color: COLOR_TEXT, borderRadius: [4,4,0,0] }},
        { name: 'Objetivo', type: 'line', data: [140,140,140,140,140,140,140], lineStyle: { color: COLOR_RED, type: 'dashed', width: 2 }, symbol: 'none' },
      ]
    });
    return c;
  }

  // ── Dashboard: Categorías paro (donut) ─────────────────────
  function chartDowntime(el) {
    const c = echarts.init(el);
    c.setOption({
      tooltip: { trigger: 'item', ...tooltip() },
      legend: { orient: 'vertical', right: 0, top: 'middle', textStyle: { color: COLOR_TEXT, fontFamily: FONT_SANS, fontSize: 12 }, itemGap: 12 },
      series: [{
        type: 'pie', radius: ['56%','78%'], center: ['32%','50%'],
        data: [
          { value: 38, name: 'Cambio formato', itemStyle: { color: COLOR_TEXT }},
          { value: 22, name: 'Mantenimiento',  itemStyle: { color: COLOR_INFO }},
          { value: 18, name: 'Calidad',        itemStyle: { color: COLOR_WARN }},
          { value: 14, name: 'Suministro',     itemStyle: { color: COLOR_RED }},
          { value: 8,  name: 'Otros',          itemStyle: { color: '#9b9690' }},
        ],
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      }]
    });
    return c;
  }

  // ── Active shift: prod en vivo ─────────────────────────────
  function chartLive(el) {
    const c = echarts.init(el);
    const mins = Array.from({length: 30}, (_,i) => `${i*2}min`);
    c.setOption({
      grid: { left: 48, right: 16, top: 16, bottom: 36 },
      tooltip: { trigger: 'axis', ...tooltip() },
      xAxis: { type: 'category', data: mins, ...baseAxis({ label: { fontSize: 9 }}) },
      yAxis: { type: 'value', ...baseAxis({ extra: { axisLine: { show: false }}}) },
      series: [{
        type: 'line', smooth: true, symbol: 'none',
        data: [120,125,128,122,130,135,138,134,140,142,138,141,145,142,144,148,146,150,152,148,154,151,156,158,160,157,162,165,168,164],
        lineStyle: { color: COLOR_RED, width: 2 },
        areaStyle: { color: { type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[
          {offset:0,color:'rgba(213,43,30,0.16)'},{offset:1,color:'rgba(213,43,30,0)'}]}},
      }]
    });
    return c;
  }

  // ── Summary: pareto ────────────────────────────────────────
  function chartPareto(el) {
    const c = echarts.init(el);
    const cats = ['Cambio formato','Mantenimiento','Calidad','Suministro','Limpieza','Otros'];
    const vals = [38,22,18,14,6,2];
    let acc = 0; const total = vals.reduce((a,b)=>a+b,0);
    const cum = vals.map(v => { acc += v; return Math.round(acc/total*100); });
    c.setOption({
      grid: { left: 48, right: 48, top: 24, bottom: 36 },
      tooltip: { trigger: 'axis', ...tooltip() },
      xAxis: { type: 'category', data: cats, ...baseAxis({ label: { fontSize: 10, interval: 0, rotate: 0 }}) },
      yAxis: [
        { type: 'value', ...baseAxis({ extra: { axisLine: { show: false }}}) },
        { type: 'value', max: 100, ...baseAxis({ label: { formatter: '{value}%' }, extra: { splitLine: { show: false }, axisLine: { show: false }}}) },
      ],
      series: [
        { type: 'bar', data: vals, barWidth: 32, itemStyle: { color: COLOR_TEXT, borderRadius: [4,4,0,0] }},
        { type: 'line', yAxisIndex: 1, data: cum, lineStyle: { color: COLOR_RED, width: 2 }, itemStyle: { color: COLOR_RED }, symbol: 'circle', symbolSize: 6 },
      ]
    });
    return c;
  }

  // ── History: trend ─────────────────────────────────────────
  function chartHistTrend(el) {
    const c = echarts.init(el);
    const days = Array.from({length:14},(_,i)=>`D-${14-i}`);
    c.setOption({
      grid: { left: 48, right: 16, top: 16, bottom: 36 },
      tooltip: { trigger: 'axis', ...tooltip() },
      xAxis: { type: 'category', data: days, ...baseAxis() },
      yAxis: { type: 'value', min: 60, max: 100, ...baseAxis({ label: { formatter: '{value}%' }, extra: { axisLine: { show: false }}}) },
      series: [{
        type: 'line', smooth: true, data: [76,79,82,80,84,86,82,85,87,84,86,88,85,84],
        lineStyle: { color: COLOR_TEXT, width: 2 }, itemStyle: { color: COLOR_TEXT }, symbol: 'circle', symbolSize: 6,
        markLine: { symbol: 'none', silent: true, lineStyle: { color: COLOR_RED, type:'dashed' }, data: [{ yAxis: 85 }]},
      }]
    });
    return c;
  }

  // ── Initiatives: savings ───────────────────────────────────
  function chartSavings(el) {
    const c = echarts.init(el);
    const months = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct'];
    c.setOption({
      grid: { left: 48, right: 16, top: 24, bottom: 36 },
      tooltip: { trigger: 'axis', ...tooltip() },
      legend: { data: ['Real','Plan'], top: 0, right: 0, textStyle: { color: COLOR_DIM, fontFamily: FONT_SANS, fontSize: 11 }},
      xAxis: { type: 'category', data: months, ...baseAxis() },
      yAxis: { type: 'value', ...baseAxis({ label: { formatter: '€{value}k' }, extra: { axisLine: { show: false }}}) },
      series: [
        { name:'Plan', type:'line', data:[80,180,280,400,540,680,820,980,1120,1280], lineStyle:{color:'#9b9690', type:'dashed', width:1.5}, symbol:'none' },
        { name:'Real', type:'line', smooth:true, data:[95,210,340,460,610,750,910,1060,1180,1240], lineStyle:{color:COLOR_RED, width:2.5}, itemStyle:{color:COLOR_RED}, symbol:'circle', symbolSize:5,
          areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(213,43,30,0.16)'},{offset:1,color:'rgba(213,43,30,0)'}]}}}
      ]
    });
    return c;
  }

  // ── Initiatives: by type donut ─────────────────────────────
  function chartIniType(el) {
    const c = echarts.init(el);
    c.setOption({
      tooltip: { trigger: 'item', ...tooltip() },
      legend: { orient: 'vertical', right: 0, top: 'middle', textStyle: { color: COLOR_TEXT, fontFamily: FONT_SANS, fontSize: 12 }, itemGap: 10 },
      series: [{
        type: 'pie', radius: ['56%','78%'], center: ['32%','50%'],
        data: [
          { value: 8, name: 'SMED',    itemStyle: { color: COLOR_TEXT }},
          { value: 5, name: 'TPM',     itemStyle: { color: COLOR_INFO }},
          { value: 4, name: 'Kaizen',  itemStyle: { color: COLOR_WARN }},
          { value: 3, name: '5S',      itemStyle: { color: COLOR_GOOD }},
          { value: 2, name: 'Otros',   itemStyle: { color: '#9b9690' }},
        ],
        label: { show: false }, labelLine: { show: false },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      }]
    });
    return c;
  }

  // Init all charts present on the page (init lazily on first show)
  const chartFns = {
    'oee-24h': chartOee24h,
    'prod-7d': chartProd,
    'downtime-cat': chartDowntime,
    'live': chartLive,
    'pareto': chartPareto,
    'hist-trend': chartHistTrend,
    'savings': chartSavings,
    'ini-type': chartIniType,
  };
  const inited = {};
  function initVisibleCharts() {
    document.querySelectorAll('[data-chart]').forEach(el => {
      const id = el.dataset.chart;
      if (inited[id]) { inited[id].resize(); return; }
      // only init if visible
      if (el.offsetParent === null) return;
      const fn = chartFns[id];
      if (fn) inited[id] = fn(el);
    });
  }
  window.addEventListener('resize', () => {
    Object.values(inited).forEach(c => c.resize());
  });
  // Initial + on screen change
  setTimeout(initVisibleCharts, 100);
  const _go = window.ppGo;
  window.ppGo = function (name) { _go(name); setTimeout(initVisibleCharts, 80); };
})();
