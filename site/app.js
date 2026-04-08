const fmtPct = (n) => `${(Number(n) * 100).toFixed(1)}%`;
const fmtNum = (n, d = 2) => Number(n).toFixed(d);
const byId = (id) => document.getElementById(id);

const MARKET_GROUPS = {
  resultados: ['vit', 'derrota', 'empate', '1x2'],
  golos: ['over', 'under', 'golos'],
  btts: ['btts', 'ambas'],
  cantos: ['cantos'],
  todos: []
};

const RADAR_AXES = ['Resultados', 'Ataque', 'Defesa', 'Ritmo'];

let DATA = null;
const TABLE_SORT_STATE = {};

function parseSortableNumber(raw) {
  const text = String(raw ?? '').trim();
  if (!text || text === '—') return null;
  const cleaned = text
    .replace(/\s+/g, '')
    .replace('%', '')
    .replace('pp', '')
    .replace(',', '.');
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function getCellSortValue(cell) {
  const text = cell?.textContent?.trim() ?? '';
  const num = parseSortableNumber(text);
  return num != null ? num : text.toLowerCase();
}

function updateSortIndicators(table, colIdx, direction) {
  const headers = Array.from(table.querySelectorAll('thead th'));
  headers.forEach((th, idx) => {
    if (!th.dataset.labelBase) th.dataset.labelBase = th.textContent.trim().replace(/\s+[▲▼]$/, '');
    th.classList.add('sortable');
    if (idx === colIdx) {
      th.textContent = `${th.dataset.labelBase} ${direction === 'asc' ? '▲' : '▼'}`;
    } else {
      th.textContent = th.dataset.labelBase;
    }
  });
}

function sortTableRows(tableId, colIdx, direction) {
  const table = byId(tableId);
  if (!table) return;
  const tbody = table.querySelector('tbody');
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr'));
  if (!rows.length) return;

  const dir = direction === 'asc' ? 1 : -1;
  rows.sort((a, b) => {
    const av = getCellSortValue(a.children[colIdx]);
    const bv = getCellSortValue(b.children[colIdx]);

    const aNum = typeof av === 'number';
    const bNum = typeof bv === 'number';
    if (aNum && bNum) return (av - bv) * dir;
    if (aNum && !bNum) return -1 * dir;
    if (!aNum && bNum) return 1 * dir;
    return String(av).localeCompare(String(bv), 'pt', { numeric: true }) * dir;
  });

  rows.forEach((r) => tbody.appendChild(r));
  TABLE_SORT_STATE[tableId] = { colIdx, direction };
  updateSortIndicators(table, colIdx, direction);
}

function enableTableSorting(tableId) {
  const table = byId(tableId);
  if (!table || table.dataset.sortingBound === '1') return;
  const headers = Array.from(table.querySelectorAll('thead th'));
  headers.forEach((th, idx) => {
    th.classList.add('sortable');
    if (!th.dataset.labelBase) th.dataset.labelBase = th.textContent.trim().replace(/\s+[▲▼]$/, '');
    th.addEventListener('click', () => {
      const current = TABLE_SORT_STATE[tableId];
      const direction = current && current.colIdx === idx && current.direction === 'asc' ? 'desc' : 'asc';
      sortTableRows(tableId, idx, direction);
    });
  });
  table.dataset.sortingBound = '1';
}

function applyExistingSort(tableId) {
  const current = TABLE_SORT_STATE[tableId];
  if (current) {
    sortTableRows(tableId, current.colIdx, current.direction);
  }
}

function setActiveTab(tabId) {
  document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tabId));
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
  byId(`panel-${tabId}`).classList.add('active');
}

function toNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function avg(arr) {
  const valid = arr.filter((x) => Number.isFinite(x));
  if (!valid.length) return null;
  return valid.reduce((a, b) => a + b, 0) / valid.length;
}

function renderSummaryChips(data) {
  const leagues = data.overview.length;
  const teams = Object.values(data.rankings).reduce((acc, arr) => acc + arr.length, 0);
  const matches = data.overview.reduce((acc, lg) => acc + (lg.matches || 0), 0);
  byId('summaryChips').innerHTML = `<span class="chip">${leagues} ligas</span><span class="chip">${teams} equipas</span><span class="chip">${matches} jogos</span>`;
}

function renderLeagueCards(data, selectedLeague) {
  byId('leagueCards').innerHTML = data.overview.map((lg) => {
    const activeStyle = lg.league === selectedLeague ? 'style="border-color:#0e7490"' : '';
    return `<button class="league-card" data-league="${lg.league}" ${activeStyle}><h3>${lg.league}</h3><p>Líder: <strong>${lg.topTeam}</strong></p><p>PPG líder: ${fmtNum(lg.topPPG)}</p><p>Equipas: ${lg.teams} · Jogos: ${lg.matches}</p></button>`;
  }).join('');

  byId('leagueCards').querySelectorAll('[data-league]').forEach((el) => {
    el.addEventListener('click', () => {
      byId('leagueSelect').value = el.dataset.league;
      renderOverview(el.dataset.league);
    });
  });
}

function renderRanking(league) {
  const rows = (DATA.rankings[league] || []).map((r, i) => `<tr><td>${i + 1}</td><td>${r.team}</td><td>${fmtNum(r.ppg)}</td><td>${fmtPct(r.wins)}</td><td>${fmtNum(r.gf)}</td><td>${fmtNum(r.ga)}</td><td>${fmtNum(r.gd)}</td><td>${fmtPct(r.btts)}</td><td>${fmtPct(r.over25)}</td></tr>`).join('');
  byId('rankingTable').querySelector('tbody').innerHTML = rows || '<tr><td colspan="9">Sem dados</td></tr>';
  applyExistingSort('rankingTable');
}

function renderMarkets(league) {
  const rows = DATA.marketRows
    .filter((r) => r.league === league && r.scope === 'Total' && r.hit_rate != null)
    .sort((a, b) => Number(b.value_estimado ?? -999) - Number(a.value_estimado ?? -999))
    .slice(0, 10);

  byId('marketsList').innerHTML = rows.map((m) => {
    const good = (m.value_estimado ?? -999) >= 0;
    return `<article class="item"><p class="title">${m.team} · ${m.market}</p><p class="meta">Hit: ${m.hit_rate != null ? fmtPct(m.hit_rate) : '—'} · ROI: ${m.roi_unid_por_aposta != null ? fmtNum(m.roi_unid_por_aposta, 3) : '—'} · Jogos: ${m.jogos}</p><span class="badge ${good ? 'good' : 'warn'}">${good ? 'value positivo' : 'value fraco'}</span></article>`;
  }).join('') || '<p class="meta">Sem mercados suficientes.</p>';
}

function renderLay(league) {
  const rows = DATA.layRows
    .filter((r) => r.league === league)
    .sort((a, b) => Number(b.lay_score ?? -999) - Number(a.lay_score ?? -999))
    .slice(0, 10);

  byId('layList').innerHTML = rows.map((m) => `<article class="item"><p class="title">${m.team} · ${m.cenario_lay}</p><p class="meta">${m.descricao} · Hit: ${m.hit_rate != null ? fmtPct(m.hit_rate) : '—'} · Score: ${m.lay_score != null ? fmtNum(m.lay_score, 2) : '—'}</p><span class="badge ${m.flag_candidato ? 'good' : 'warn'}">${m.flag_candidato ? 'candidato' : 'observar'}</span></article>`).join('') || '<p class="meta">Sem cenários lay.</p>';
}

function renderOverview(league) {
  renderLeagueCards(DATA, league);
  renderRanking(league);
  renderMarkets(league);
  renderLay(league);
}

function populateScannerFilters(leagues) {
  byId('scanLeague').innerHTML = ['Todas', ...leagues].map((l) => `<option value="${l}">${l}</option>`).join('');
}

function marketInGroup(market, group) {
  if (group === 'todos') return true;
  const keys = MARKET_GROUPS[group] || [];
  const m = String(market || '').toLowerCase();
  return keys.some((k) => m.includes(k));
}

function renderScanner() {
  const league = byId('scanLeague').value;
  const scope = byId('scanScope').value;
  const group = byId('scanGroup').value;
  const minGames = Number(byId('scanMinGames').value || 1);

  let rows = DATA.marketRows.filter((r) => (league === 'Todas' || r.league === league) && r.scope === scope && Number(r.jogos || 0) >= minGames && marketInGroup(r.market, group));
  rows = rows.sort((a, b) => Number(b.edge_vs_liga ?? -999) - Number(a.edge_vs_liga ?? -999));

  byId('scannerTable').querySelector('tbody').innerHTML = rows.slice(0, 120).map((r) => `<tr><td>${r.team}</td><td>${r.market}</td><td>${r.jogos}</td><td>${r.hit_rate != null ? fmtPct(r.hit_rate) : '—'}</td><td>${r.edge_vs_liga != null ? `${fmtNum(r.edge_vs_liga * 100, 1)} pp` : '—'}</td><td>${r.roi_unid_por_aposta != null ? fmtNum(r.roi_unid_por_aposta, 3) : '—'}</td><td>${r.value_estimado != null ? `${fmtNum(r.value_estimado * 100, 1)}%` : '—'}</td></tr>`).join('') || '<tr><td colspan="7">Sem dados para os filtros escolhidos.</td></tr>';
  applyExistingSort('scannerTable');
}

function getResumoRow(league, team, scope) {
  return DATA.resumoRows.find((r) => r.league === league && r.team === team && r.scope === scope);
}

function getScopeRows(league, scope) {
  return DATA.resumoRows.filter((r) => r.league === league && r.scope === scope);
}

function zScore(rows, col, val, invert = false) {
  const values = rows.map((r) => Number(r[col])).filter((x) => Number.isFinite(x));
  if (!values.length || !Number.isFinite(val)) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((acc, x) => acc + ((x - mean) ** 2), 0) / values.length;
  const std = Math.sqrt(variance);
  if (!std) return 0;
  const z = (val - mean) / std;
  return invert ? -z : z;
}

function radarProfile(league, row, scope) {
  const rows = getScopeRows(league, scope);
  const results = avg([
    zScore(rows, 'ppg', Number(row.ppg), false),
    zScore(rows, 'vit%', Number(row['vit%']), false),
    zScore(rows, 'der%', Number(row['der%']), true)
  ]);
  const attack = avg([
    zScore(rows, 'golos_marcados', Number(row.golos_marcados), false),
    zScore(rows, 'marca%', Number(row['marca%']), false),
    zScore(rows, 'SOT', Number(row.SOT), false),
    zScore(rows, 'conversion_rate', Number(row.conversion_rate), false)
  ]);
  const defense = avg([
    zScore(rows, 'golos_sofridos', Number(row.golos_sofridos), true),
    zScore(rows, 'CS%', Number(row['CS%']), false),
    zScore(rows, 'SOT_sofridos', Number(row.SOT_sofridos), true)
  ]);
  const rhythm = avg([
    zScore(rows, 'BTTS%', Number(row['BTTS%']), false),
    zScore(rows, 'O2.5%', Number(row['O2.5%']), false)
  ]);

  return [results, attack, defense, rhythm].map((z) => clamp(50 + (z || 0) * 16, 8, 95));
}

function drawRadar(canvasId, titleId, teamName, values, color) {
  const canvas = byId(canvasId);
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const radius = Math.min(canvas.width, canvas.height) * 0.36;

  byId(titleId).textContent = teamName;

  ctx.strokeStyle = '#d9dddf';
  ctx.lineWidth = 1;
  for (let ring = 1; ring <= 4; ring += 1) {
    ctx.beginPath();
    for (let i = 0; i < RADAR_AXES.length; i += 1) {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI / RADAR_AXES.length);
      const x = cx + Math.cos(angle) * radius * (ring / 4);
      const y = cy + Math.sin(angle) * radius * (ring / 4);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  ctx.fillStyle = '#55606f';
  ctx.font = '12px Segoe UI';
  ctx.textAlign = 'center';
  RADAR_AXES.forEach((axis, i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / RADAR_AXES.length);
    const x = cx + Math.cos(angle) * (radius + 22);
    const y = cy + Math.sin(angle) * (radius + 22);
    ctx.fillText(axis, x, y);

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
    ctx.strokeStyle = '#edf0f2';
    ctx.stroke();
  });

  ctx.beginPath();
  values.forEach((v, i) => {
    const ratio = v / 100;
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / RADAR_AXES.length);
    const x = cx + Math.cos(angle) * radius * ratio;
    const y = cy + Math.sin(angle) * radius * ratio;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = `${color}44`;
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function strengthsWeakness(row, league, scope) {
  const rows = getScopeRows(league, scope);
  const specs = [
    ['ppg', 'Pontos por jogo', false],
    ['vit%', 'Taxa de vitórias', false],
    ['golos_marcados', 'Golos marcados', false],
    ['golos_sofridos', 'Golos sofridos', true],
    ['CS%', 'Clean sheet', false],
    ['BTTS%', 'BTTS', false],
    ['O2.5%', 'Over 2.5', false],
    ['SOT', 'Remates à baliza', false],
    ['SOT_sofridos', 'Remates à baliza sofridos', true],
    ['conversion_rate', 'Conversão de remates', false]
  ];

  const scored = specs.map(([col, label, inv]) => ({
    label,
    z: zScore(rows, col, Number(row[col]), inv)
  })).filter((x) => Number.isFinite(x.z));

  scored.sort((a, b) => b.z - a.z);
  const top = scored.slice(0, 2);
  const low = scored.slice(-2).reverse();
  return { top, low };
}

function renderConfrontoKpis(league, home, away) {
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');

  const makeCard = (title, row) => {
    if (!row) return `<article class="kpi-card"><h3>${title}</h3><p class="meta">Sem dados</p></article>`;
    return `<article class="kpi-card"><h3>${title}</h3>
      <div class="kpi-row"><span>PPG</span><strong>${fmtNum(row.ppg)}</strong></div>
      <div class="kpi-row"><span>Vitórias</span><strong>${fmtPct(row['vit%'])}</strong></div>
      <div class="kpi-row"><span>Golos Marcados</span><strong>${fmtNum(row.golos_marcados)}</strong></div>
      <div class="kpi-row"><span>Golos Sofridos</span><strong>${fmtNum(row.golos_sofridos)}</strong></div>
      <div class="kpi-row"><span>BTTS</span><strong>${fmtPct(row['BTTS%'])}</strong></div>
      <div class="kpi-row"><span>Over 2.5</span><strong>${fmtPct(row['O2.5%'])}</strong></div>
    </article>`;
  };

  byId('confrontoKpis').innerHTML = makeCard(`${home} (Casa)`, h) + makeCard(`${away} (Fora)`, a);
}

function buildConfrontoMerged(league, home, away) {
  const hm = DATA.marketRows.filter((r) => r.league === league && r.team === home && r.scope === 'Casa');
  const aw = DATA.marketRows.filter((r) => r.league === league && r.team === away && r.scope === 'Fora');
  const awMap = new Map(aw.map((r) => [r.market, r]));

  return hm
    .filter((r) => awMap.has(r.market))
    .map((r) => {
      const b = awMap.get(r.market);
      const eh = Number(r.edge_vs_liga ?? NaN);
      const ea = Number(b.edge_vs_liga ?? NaN);
      const hh = Number(r.hit_rate ?? NaN);
      const ha = Number(b.hit_rate ?? NaN);
      return {
        market: r.market,
        homeEdge: Number.isFinite(eh) ? eh : null,
        awayEdge: Number.isFinite(ea) ? ea : null,
        avg: (Number.isFinite(eh) && Number.isFinite(ea)) ? (eh + ea) / 2 : null,
        hitAvg: (Number.isFinite(hh) && Number.isFinite(ha)) ? (hh + ha) / 2 : null
      };
    })
    .filter((x) => x.avg != null);
}

function renderConfrontoMarkets(league, home, away) {
  const merged = buildConfrontoMerged(league, home, away)
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 20);

  byId('confrontoMarketTable').querySelector('tbody').innerHTML = merged.map((r) => `<tr><td>${r.market}</td><td>${fmtNum(r.homeEdge * 100, 1)} pp</td><td>${fmtNum(r.awayEdge * 100, 1)} pp</td><td>${fmtNum(r.avg * 100, 1)} pp</td></tr>`).join('') || '<tr><td colspan="4">Sem mercados convergentes para este confronto.</td></tr>';
  applyExistingSort('confrontoMarketTable');
}

function renderRadarSection(league, home, away) {
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  if (!h || !a) return;

  drawRadar('radarHome', 'radarHomeTitle', `${home} (Casa)`, radarProfile(league, h, 'Casa'), '#0e7490');
  drawRadar('radarAway', 'radarAwayTitle', `${away} (Fora)`, radarProfile(league, a, 'Fora'), '#c2410c');

  const hs = strengthsWeakness(h, league, 'Casa');
  const as = strengthsWeakness(a, league, 'Fora');

  byId('homeStrengths').innerHTML = `<div><strong>Pontos fortes:</strong> ${hs.top.map((x) => x.label).join(', ') || '—'}</div><div><strong>Pontos fracos:</strong> ${hs.low.map((x) => x.label).join(', ') || '—'}</div>`;
  byId('awayStrengths').innerHTML = `<div><strong>Pontos fortes:</strong> ${as.top.map((x) => x.label).join(', ') || '—'}</div><div><strong>Pontos fracos:</strong> ${as.low.map((x) => x.label).join(', ') || '—'}</div>`;
}

function matchupInsights(league, home, away) {
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  if (!h || !a) return [];

  const out = [];

  if (Number(h.golos_marcados) >= 1.7 && Number(a.golos_sofridos) >= 1.4) {
    out.push('Casa com ângulo ofensivo forte: ataque da casa acima da média e defesa visitante permissiva.');
  }
  if (Number(a.golos_marcados) >= 1.4 && Number(h.golos_sofridos) >= 1.3) {
    out.push('Visitante com potencial de marcar: produção ofensiva consistente contra defesa da casa vulnerável.');
  }
  if (Number(h['O2.5%']) >= 0.6 && Number(a['O2.5%']) >= 0.55) {
    out.push('Ritmo alto dos dois lados, jogo propenso a linhas de golos mais altas.');
  }
  if (Number(h['CS%']) >= 0.4 && Number(a['marca%']) <= 0.75) {
    out.push('Boa hipótese de controlo defensivo da casa, com risco reduzido de sofrer.');
  }
  if (Number(h.ppg) - Number(a.ppg) >= 0.45) {
    out.push('Diferença de desempenho no contexto casa/fora favorece a equipa da casa.');
  }

  return out.slice(0, 5);
}

function renderConfrontoInsights(league, home, away) {
  const insights = matchupInsights(league, home, away);
  byId('confrontoInsights').innerHTML = insights.length
    ? insights.map((x) => `<li>${x}</li>`).join('')
    : '<li>Sem sinais fortes para este matchup com os dados atuais.</li>';
}

function populateConfronto(leagues) {
  const leagueSel = byId('cfLeague');
  leagueSel.innerHTML = leagues.map((l) => `<option value="${l}">${l}</option>`).join('');

  function refreshTeams() {
    const lg = leagueSel.value;
    const teams = (DATA.rankings[lg] || []).map((x) => x.team);
    byId('cfHome').innerHTML = teams.map((t) => `<option value="${t}">${t}</option>`).join('');
    byId('cfAway').innerHTML = teams.map((t) => `<option value="${t}">${t}</option>`).join('');
    if (teams.length > 1) byId('cfAway').selectedIndex = 1;
    renderConfronto();
  }

  leagueSel.addEventListener('change', refreshTeams);
  byId('cfHome').addEventListener('change', renderConfronto);
  byId('cfAway').addEventListener('change', renderConfronto);
  refreshTeams();
}

function renderConfronto() {
  const league = byId('cfLeague').value;
  const home = byId('cfHome').value;
  const away = byId('cfAway').value;
  if (!league || !home || !away || home === away) return;
  renderConfrontoKpis(league, home, away);
  renderRadarSection(league, home, away);
  renderConfrontoMarkets(league, home, away);
  renderConfrontoInsights(league, home, away);
}

function getSeries(league, team, venue, metric) {
  return DATA.seriesRows
    .filter((r) => r.league === league && r.team === team && r.venue === venue)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .map((r) => ({ date: r.date, value: Number(r[metric]) }));
}

function drawFormLineChart(series, metric) {
  const svg = byId('formLineChart');
  if (!svg) return;

  if (!series.length) {
    svg.innerHTML = '<text x="16" y="28" fill="#5f6a78" font-size="14">Sem dados suficientes para o gráfico.</text>';
    return;
  }

  const width = 640;
  const height = 280;
  const margin = { top: 16, right: 20, bottom: 34, left: 42 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;

  const isRateMetric = ['roll5_over_2_5', 'roll5_btts', 'roll5_clean_sheet'].includes(metric);
  const values = series.map((s) => s.value).filter((v) => Number.isFinite(v));
  const minData = Math.min(...values);
  const maxData = Math.max(...values);

  let yMin = minData;
  let yMax = maxData;
  if (isRateMetric) {
    yMin = Math.min(0, yMin);
    yMax = Math.max(1, yMax);
  }
  if (yMin === yMax) {
    yMin -= 0.5;
    yMax += 0.5;
  }

  const xAt = (idx) => margin.left + (idx / Math.max(series.length - 1, 1)) * chartW;
  const yAt = (v) => margin.top + (1 - ((v - yMin) / (yMax - yMin))) * chartH;

  const points = series.map((s, i) => `${xAt(i)},${yAt(s.value)}`).join(' ');

  const yTicks = 4;
  let grid = '';
  let labels = '';
  for (let i = 0; i <= yTicks; i += 1) {
    const t = i / yTicks;
    const y = margin.top + t * chartH;
    const v = yMax - t * (yMax - yMin);
    const label = isRateMetric ? `${(v * 100).toFixed(0)}%` : v.toFixed(2);
    grid += `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#edf0f2" stroke-width="1" />`;
    labels += `<text x="${margin.left - 8}" y="${y + 4}" text-anchor="end" fill="#5f6a78" font-size="11">${label}</text>`;
  }

  const xStart = series[0].date ?? '';
  const xEnd = series[series.length - 1].date ?? '';

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff" />
    ${grid}
    <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="#d9dddf" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="#d9dddf" />
    ${labels}
    <polyline fill="none" stroke="#0e7490" stroke-width="3" points="${points}" />
    ${series.map((s, i) => `<circle cx="${xAt(i)}" cy="${yAt(s.value)}" r="3.2" fill="#0e7490" />`).join('')}
    <text x="${margin.left}" y="${height - 8}" fill="#5f6a78" font-size="11">${xStart}</text>
    <text x="${width - margin.right}" y="${height - 8}" text-anchor="end" fill="#5f6a78" font-size="11">${xEnd}</text>
  `;
}

function renderForma() {
  const league = byId('formLeague').value;
  const team = byId('formTeam').value;
  const venue = byId('formVenue').value;
  const metric = byId('formMetric').value;

  const series = getSeries(league, team, venue, metric).filter((x) => Number.isFinite(x.value));
  const latest = series.length ? series[series.length - 1].value : null;
  const prev = series.length > 1 ? series[series.length - 2].value : null;
  const avgVal = series.length ? series.reduce((a, x) => a + x.value, 0) / series.length : null;
  const delta = (latest != null && prev != null) ? latest - prev : null;

  byId('formTrendCards').innerHTML = `
    <article class="kpi-card"><h3>Último valor</h3><div class="kpi-row"><span>${metric}</span><strong>${latest != null ? fmtNum(latest) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Tendência</h3><div class="kpi-row"><span>Último vs anterior</span><strong>${delta != null ? (delta >= 0 ? '+' : '') + fmtNum(delta) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Média da série</h3><div class="kpi-row"><span>Média</span><strong>${avgVal != null ? fmtNum(avgVal) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Amostra</h3><div class="kpi-row"><span>Registos</span><strong>${series.length}</strong></div></article>
  `;

  drawFormLineChart(series, metric);

  byId('formTable').querySelector('tbody').innerHTML = series.slice(-12).reverse().map((r, idx, arr) => {
    const next = arr[idx + 1];
    const d = next ? r.value - next.value : 0;
    const trend = next ? (d > 0 ? 'A subir' : d < 0 ? 'A descer' : 'Estável') : '—';
    return `<tr><td>${r.date}</td><td>${fmtNum(r.value)}</td><td>${trend}</td></tr>`;
  }).join('') || '<tr><td colspan="3">Sem dados de forma para este filtro.</td></tr>';
  applyExistingSort('formTable');
}

function populateForma(leagues) {
  byId('formLeague').innerHTML = leagues.map((l) => `<option value="${l}">${l}</option>`).join('');

  function refreshTeams() {
    const lg = byId('formLeague').value;
    const teams = (DATA.rankings[lg] || []).map((x) => x.team);
    byId('formTeam').innerHTML = teams.map((t) => `<option value="${t}">${t}</option>`).join('');
    renderForma();
  }

  byId('formLeague').addEventListener('change', refreshTeams);
  ['formTeam', 'formVenue', 'formMetric'].forEach((id) => byId(id).addEventListener('change', renderForma));
  refreshTeams();
}

function avgLeague(league, scope, col) {
  const vals = DATA.resumoRows.filter((r) => r.league === league && r.scope === scope).map((r) => Number(r[col])).filter((x) => Number.isFinite(x));
  if (!vals.length) return null;
  return vals.reduce((a, x) => a + x, 0) / vals.length;
}

function recentFormRate(league, team, venue, metric) {
  const s = getSeries(league, team, venue, metric).filter((x) => Number.isFinite(x.value));
  if (!s.length) return null;
  const last = s.slice(-5);
  return last.reduce((a, x) => a + x.value, 0) / last.length;
}

function poissonPmfArray(lambda, maxGoals) {
  const pmf = (lam, k) => {
    if (lam <= 0) return k === 0 ? 1 : 0;
    let fact = 1;
    for (let i = 2; i <= k; i += 1) fact *= i;
    return Math.exp(-lam) * Math.pow(lam, k) / fact;
  };
  return Array.from({ length: maxGoals + 1 }, (_, k) => pmf(lambda, k));
}

function poissonProbs(lambdaHome, lambdaAway, maxGoals = 10) {
  const h = poissonPmfArray(lambdaHome, maxGoals);
  const a = poissonPmfArray(lambdaAway, maxGoals);

  let p1 = 0; let px = 0; let p2 = 0; let over25 = 0; let btts = 0;
  for (let i = 0; i <= maxGoals; i += 1) {
    for (let j = 0; j <= maxGoals; j += 1) {
      const p = h[i] * a[j];
      if (i > j) p1 += p;
      if (i === j) px += p;
      if (i < j) p2 += p;
      if (i + j >= 3) over25 += p;
      if (i > 0 && j > 0) btts += p;
    }
  }
  return { p1, px, p2, over25, btts, pmfHome: h, pmfAway: a };
}

function computeExpectedGoals(league, homeTeam, awayTeam, weightRecent = 0.35) {
  const home = getResumoRow(league, homeTeam, 'Casa');
  const away = getResumoRow(league, awayTeam, 'Fora');
  if (!home || !away) return null;

  const lgHomeGF = avgLeague(league, 'Casa', 'golos_marcados');
  const lgHomeGA = avgLeague(league, 'Casa', 'golos_sofridos');
  const lgAwayGF = avgLeague(league, 'Fora', 'golos_marcados');
  const lgAwayGA = avgLeague(league, 'Fora', 'golos_sofridos');
  if (![lgHomeGF, lgHomeGA, lgAwayGF, lgAwayGA].every((x) => Number.isFinite(x) && x > 0)) return null;

  const seasonHome = lgHomeGF * (Number(home.golos_marcados) / lgHomeGF) * (Number(away.golos_sofridos) / lgAwayGA);
  const seasonAway = lgAwayGF * (Number(away.golos_marcados) / lgAwayGF) * (Number(home.golos_sofridos) / lgHomeGA);

  const recentHomeFor = recentFormRate(league, homeTeam, 'H', 'roll5_gf');
  const recentHomeAgainst = recentFormRate(league, homeTeam, 'H', 'roll5_ga');
  const recentAwayFor = recentFormRate(league, awayTeam, 'A', 'roll5_gf');
  const recentAwayAgainst = recentFormRate(league, awayTeam, 'A', 'roll5_ga');

  const recentHome = (Number.isFinite(recentHomeFor) && Number.isFinite(recentAwayAgainst)) ? ((recentHomeFor + recentAwayAgainst) / 2) : seasonHome;
  const recentAway = (Number.isFinite(recentAwayFor) && Number.isFinite(recentHomeAgainst)) ? ((recentAwayFor + recentHomeAgainst) / 2) : seasonAway;

  const w = clamp(weightRecent, 0, 0.7);
  const lambdaHome = (1 - w) * seasonHome + w * recentHome;
  const lambdaAway = (1 - w) * seasonAway + w * recentAway;

  return { lambdaHome, lambdaAway };
}

function renderScoreHeatmap(pmfHome, pmfAway) {
  const maxGoals = 5;
  const cells = [];
  let maxP = 0;

  for (let h = 0; h <= maxGoals; h += 1) {
    for (let a = 0; a <= maxGoals; a += 1) {
      const p = (pmfHome[h] || 0) * (pmfAway[a] || 0);
      maxP = Math.max(maxP, p);
      cells.push({ h, a, p });
    }
  }

  const sorted = cells.slice().sort((x, y) => y.p - x.p);
  const top = new Set(sorted.slice(0, 6).map((x) => `${x.h}-${x.a}`));

  byId('scoreHeatmap').innerHTML = cells.map((c) => {
    const alpha = maxP > 0 ? (0.15 + 0.75 * (c.p / maxP)) : 0.15;
    const border = top.has(`${c.h}-${c.a}`) ? '2px solid #0e7490' : '1px solid #e6ddd0';
    return `<div class="heat-cell" style="background: rgba(14,116,144,${alpha.toFixed(3)}); border:${border}"><div class="score">${c.h} - ${c.a}</div><div class="prob">${(c.p * 100).toFixed(1)}%</div></div>`;
  }).join('');
}

function renderPrejogo() {
  const league = byId('pjLeague').value;
  const home = byId('pjHome').value;
  const away = byId('pjAway').value;
  const weight = Number(byId('pjRecentWeight').value || 35) / 100;

  if (!league || !home || !away || home === away) return;

  const eg = computeExpectedGoals(league, home, away, weight);
  if (!eg) {
    byId('prejogoProbCards').innerHTML = '<article class="kpi-card"><h3>Pré-jogo</h3><p class="meta">Sem dados suficientes para calcular EG.</p></article>';
    byId('prejogoShortlistTable').querySelector('tbody').innerHTML = '<tr><td colspan="5">Sem shortlist para este jogo.</td></tr>';
    byId('scoreHeatmap').innerHTML = '<p class="meta">Sem dados de heatmap.</p>';
    return;
  }

  const probs = poissonProbs(eg.lambdaHome, eg.lambdaAway, 10);

  byId('prejogoProbCards').innerHTML = `
    <article class="kpi-card"><h3>Expected Goals</h3><div class="kpi-row"><span>${home}</span><strong>${fmtNum(eg.lambdaHome)}</strong></div><div class="kpi-row"><span>${away}</span><strong>${fmtNum(eg.lambdaAway)}</strong></div></article>
    <article class="kpi-card"><h3>1X2</h3><div class="kpi-row"><span>1</span><strong>${fmtPct(probs.p1)}</strong></div><div class="kpi-row"><span>X</span><strong>${fmtPct(probs.px)}</strong></div><div class="kpi-row"><span>2</span><strong>${fmtPct(probs.p2)}</strong></div></article>
    <article class="kpi-card"><h3>Totais</h3><div class="kpi-row"><span>Over 2.5</span><strong>${fmtPct(probs.over25)}</strong></div><div class="kpi-row"><span>BTTS</span><strong>${fmtPct(probs.btts)}</strong></div></article>
    <article class="kpi-card"><h3>Configuração</h3><div class="kpi-row"><span>Peso forma</span><strong>${fmtPct(weight)}</strong></div><div class="kpi-row"><span>Liga</span><strong>${league}</strong></div></article>
  `;

  renderScoreHeatmap(probs.pmfHome, probs.pmfAway);

  const shortlist = buildConfrontoMerged(league, home, away)
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 15);

  byId('prejogoShortlistTable').querySelector('tbody').innerHTML = shortlist.map((r) => `<tr><td>${r.market}</td><td>${fmtNum(r.homeEdge * 100, 1)} pp</td><td>${fmtNum(r.awayEdge * 100, 1)} pp</td><td>${fmtNum(r.avg * 100, 1)} pp</td><td>${r.hitAvg != null ? fmtPct(r.hitAvg) : '—'}</td></tr>`).join('') || '<tr><td colspan="5">Sem shortlist para este jogo.</td></tr>';
  applyExistingSort('prejogoShortlistTable');
}

function populatePrejogo(leagues) {
  byId('pjLeague').innerHTML = leagues.map((l) => `<option value="${l}">${l}</option>`).join('');

  function refreshTeams() {
    const lg = byId('pjLeague').value;
    const teams = (DATA.rankings[lg] || []).map((x) => x.team);
    byId('pjHome').innerHTML = teams.map((t) => `<option value="${t}">${t}</option>`).join('');
    byId('pjAway').innerHTML = teams.map((t) => `<option value="${t}">${t}</option>`).join('');
    if (teams.length > 1) byId('pjAway').selectedIndex = 1;
    renderPrejogo();
  }

  byId('pjLeague').addEventListener('change', refreshTeams);
  ['pjHome', 'pjAway', 'pjRecentWeight'].forEach((id) => byId(id).addEventListener('change', renderPrejogo));
  refreshTeams();
}

async function main() {
  const res = await fetch('./data/site-data.json');
  DATA = await res.json();

  renderSummaryChips(DATA);
  byId('sourceInfo').textContent = `Fontes usadas: ${(DATA.meta?.sourceFiles || []).join(', ')}`;

  const leagues = DATA.overview.map((x) => x.league);

  byId('leagueSelect').innerHTML = leagues.map((l) => `<option value="${l}">${l}</option>`).join('');
  byId('leagueSelect').addEventListener('change', (e) => renderOverview(e.target.value));
  renderOverview(leagues[0]);

  populateScannerFilters(leagues);
  ['scanLeague', 'scanScope', 'scanGroup', 'scanMinGames'].forEach((id) => byId(id).addEventListener('change', renderScanner));
  renderScanner();

  populateConfronto(leagues);
  populateForma(leagues);
  populatePrejogo(leagues);

  document.querySelectorAll('.tab').forEach((btn) => btn.addEventListener('click', () => setActiveTab(btn.dataset.tab)));

  ['rankingTable', 'scannerTable', 'confrontoMarketTable', 'formTable', 'prejogoShortlistTable'].forEach(enableTableSorting);
}

main().catch((err) => {
  console.error(err);
  alert('Não foi possível carregar os dados do site.');
});
