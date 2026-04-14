const fmtPct = (n) => `${(Number(n) * 100).toFixed(1)}%`;
const fmtNum = (n, d = 2) => Number(n).toFixed(d);
const byId = (id) => document.getElementById(id);

const RADAR_AXES = ['Resultados', 'Ataque', 'Defesa', 'Ritmo'];
const LEAGUE_LABELS = {
  E0: 'Premier League (Inglaterra)',
  E1: 'Championship (Inglaterra)',
  F1: 'Ligue 1 (França)',
  I1: 'Serie A (Itália)',
  P1: 'Liga Portugal',
  D1: 'Bundesliga',
  SP1: 'La Liga',
  SC0: 'Scottish Premier League',
  N1: 'Eredivisie',
  T1: 'Turkish Superleague'
};
const WATCHLIST_KEY = 'radar_watchlist_v1';

let DATA = null;
const TABLE_SORT_STATE = {};
let PREJOGO_STATE = { league: null, home: null, away: null, probs: null, shortlist: [] };
let WATCHLIST = new Set();

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

function downloadCSV(filename, headers, rows) {
  const esc = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  const csv = [headers.map(esc).join(',')]
    .concat(rows.map((r) => r.map(esc).join(',')))
    .join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function setActiveTab(tabId) {
  document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tabId));
  document.querySelectorAll('.tab-panel').forEach((p) => {
    p.classList.remove('active');
    p.hidden = true;
  });
  const panel = byId(`panel-${tabId}`);
  if (!panel) return;
  panel.classList.add('active');
  panel.hidden = false;
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

function norm(v, min, max) {
  if (!Number.isFinite(v) || max <= min) return 0;
  return clamp((v - min) / (max - min), 0, 1);
}

function leagueLabel(code) {
  return LEAGUE_LABELS[code] || code;
}

function chartTheme() {
  const css = getComputedStyle(document.documentElement);
  const pick = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  return {
    bg: pick('--chart-bg', '#0f1a27'),
    grid: pick('--chart-grid', '#2b3d52'),
    axis: pick('--chart-axis', '#8ea1b4'),
    main: pick('--chart-main', '#76a9ff'),
    alt: pick('--chart-alt', '#c8a66a'),
    text: pick('--text', '#e8edf3'),
    muted: pick('--muted', '#95a6b8')
  };
}

function leagueOptions(leagues) {
  return leagues.map((l) => `<option value="${l}">${leagueLabel(l)}</option>`).join('');
}

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return;
    const items = JSON.parse(raw);
    if (Array.isArray(items)) WATCHLIST = new Set(items.map(String));
  } catch {
    WATCHLIST = new Set();
  }
}

function saveWatchlist() {
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(Array.from(WATCHLIST)));
}

function watchKey(row) {
  return `${row.league}|${row.team}|${row.scope}|${row.market}`;
}

function sampleQuality(games) {
  const g = Number(games || 0);
  if (g >= 20) return { label: 'Alta', cls: 'good' };
  if (g >= 12) return { label: 'Média', cls: '' };
  return { label: 'Baixa', cls: 'warn' };
}

function miniSparkline(row) {
  const a = toNum(row.hit_rate);
  const b = toNum(row.form_recent_5);
  if (a == null || b == null) return '—';
  const series = [0, 1, 2, 3, 4].map((i) => a + ((b - a) * i / 4));
  const width = 78;
  const height = 22;
  const xAt = (i) => 4 + (i / 4) * (width - 8);
  const yAt = (v) => 2 + (1 - clamp(v, 0, 1)) * (height - 6);
  const pts = series.map((v, i) => `${xAt(i)},${yAt(v)}`).join(' ');
  const t = chartTheme();
  return `<div class="spark-wrap"><svg viewBox="0 0 ${width} ${height}" class="spark"><polyline fill="none" stroke="${t.main}" stroke-width="2" points="${pts}" /></svg><span>${fmtPct(b)}</span></div>`;
}

function groupLabel(group) {
  const map = {
    resultados: 'Resultados',
    golos: 'Golos',
    btts: 'BTTS',
    cantos: 'Cantos',
    outros: 'Outros'
  };
  return map[group] || group;
}

function opportunityScore(row) {
  const edge = toNum(row.edge_vs_liga);
  const games = toNum(row.jogos) ?? 0;
  const lo = toNum(row.wilson_lo);
  const hi = toNum(row.wilson_hi);

  const edgeFactor = edge == null ? 0 : norm(edge, -0.05, 0.2);
  const sampleFactor = norm(games, 5, 28);
  const width = (lo != null && hi != null) ? Math.max(0, hi - lo) : null;
  const stabilityFactor = width == null ? 0.5 : norm(0.4 - width, 0, 0.4);
  return Math.round((edgeFactor * 0.5 + sampleFactor * 0.25 + stabilityFactor * 0.25) * 100);
}

function scoreBadge(score) {
  if (score >= 75) return '<span class="badge good">Alta</span>';
  if (score >= 55) return '<span class="badge">Média</span>';
  return '<span class="badge warn">Baixa</span>';
}

function renderSummaryChips(data) {
  const leagues = data.overview.length;
  const teams = Object.values(data.rankings).reduce((acc, arr) => acc + arr.length, 0);
  const matches = data.overview.reduce((acc, lg) => acc + (lg.matches || 0), 0);
  byId('summaryChips').innerHTML = `<span class="chip">${leagues} ligas</span><span class="chip">${teams} equipas</span><span class="chip">${matches} jogos</span>`;
}

function renderHomeKpis(league, teamFilter = 'Todas') {
  const marketRows = DATA.marketRows.filter((r) => r.league === league && r.scope === 'Total' && (teamFilter === 'Todas' || r.team === teamFilter));
  const alerts = ((DATA.weeklyAlerts?.byLeague || {})[league] || []).filter((a) => teamFilter === 'Todas' || a.entity === teamFilter);
  const topOpp = marketRows
    .map((r) => ({ ...r, opportunityScore: opportunityScore(r) }))
    .sort((a, b) => Number(b.opportunityScore ?? -999) - Number(a.opportunityScore ?? -999))[0];
  const bestMatch = DATA.matchOfWeekByLeague?.[league];

  byId('homeKpis').innerHTML = `
    <article class="kpi-card"><h3>Melhor jogo da semana</h3><div class="kpi-row"><span>${leagueLabel(league)}</span><strong>${bestMatch ? `${bestMatch.homeTeam} vs ${bestMatch.awayTeam}` : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Oportunidades ativas</h3><div class="kpi-row"><span>Edge positivo</span><strong>${marketRows.filter((r) => toNum(r.edge_vs_liga) != null && Number(r.edge_vs_liga) > 0).length}</strong></div></article>
    <article class="kpi-card"><h3>Maior edge médio</h3><div class="kpi-row"><span>${topOpp ? `${topOpp.team} · ${topOpp.market}` : '—'}</span><strong>${topOpp && toNum(topOpp.edge_vs_liga) != null ? `${fmtNum(topOpp.edge_vs_liga * 100, 1)} pp` : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Alertas ativos</h3><div class="kpi-row"><span>Alta severidade</span><strong>${alerts.filter((a) => a.severity === 'high').length}</strong></div></article>
  `;
}

function syncDashboardTeamOptions(league) {
  const teamSelect = byId('dashboardTeamSelect');
  if (!teamSelect) return;
  const current = teamSelect.value || 'Todas';
  const teams = (DATA.rankings[league] || []).map((x) => x.team);
  teamSelect.innerHTML = ['Todas', ...teams].map((t) => `<option value="${t}">${t}</option>`).join('');
  if (['Todas', ...teams].includes(current)) teamSelect.value = current;
}

function renderHomeNarrative(league, teamFilter = 'Todas') {
  const alerts = ((DATA.weeklyAlerts?.byLeague || {})[league] || []).filter((a) => teamFilter === 'Todas' || a.entity === teamFilter);
  const high = alerts.filter((a) => a.severity === 'high').length;
  const accelTeams = (DATA.rankings[league] || [])
    .map((t) => {
      const all = DATA.seriesRows
        .filter((r) => r.league === league && r.team === t.team)
        .sort((a, b) => String(a.date).localeCompare(String(b.date)))
        .map((r) => Number(r.roll5_points))
        .filter((x) => Number.isFinite(x));
      if (all.length < 2) return null;
      return { team: t.team, delta: all[all.length - 1] - all[all.length - 2] };
    })
    .filter((x) => x && x.delta > 0.4)
    .slice(0, 3);
  const topOpp = DATA.marketRows
    .filter((r) => r.league === league && r.scope === 'Total' && (teamFilter === 'Todas' || r.team === teamFilter))
    .map((r) => ({ ...r, opportunityScore: opportunityScore(r) }))
    .sort((a, b) => Number(b.opportunityScore ?? -999) - Number(a.opportunityScore ?? -999))
    .slice(0, 2);

  byId('homeNarrative').innerHTML = `
    <article class="item"><p class="title">Leitura rápida da semana</p><p class="meta">${accelTeams.length} equipas em aceleração (${accelTeams.map((x) => x.team).join(', ') || 'n/a'}).</p></article>
    <article class="item"><p class="title">Convicção de mercado</p><p class="meta">${topOpp.length} mercados com maior edge relativo (${topOpp.map((x) => `${x.team} · ${x.market}`).join(' | ') || 'n/a'}).</p></article>
    <article class="item"><p class="title">Risco imediato</p><p class="meta">${high} alertas críticos na liga selecionada.</p></article>
  `;
}

function renderLeagueCards(data, selectedLeague) {
  byId('leagueCards').innerHTML = data.overview.map((lg) => {
    const activeStyle = lg.league === selectedLeague ? 'style="border-color:#0e7490"' : '';
    return `<button class="league-card" data-league="${lg.league}" ${activeStyle}><h3>${leagueLabel(lg.league)}</h3><p>Líder: <strong>${lg.topTeam}</strong></p><p>PPG líder: ${fmtNum(lg.topPPG)}</p><p>Equipas: ${lg.teams} · Jogos: ${lg.matches}</p></button>`;
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

function renderMarkets(league, teamFilter = 'Todas') {
  const rows = DATA.marketRows
    .filter((r) => r.league === league && r.scope === 'Total' && r.hit_rate != null && (teamFilter === 'Todas' || r.team === teamFilter))
    .sort((a, b) => Number(b.value_estimado ?? -999) - Number(a.value_estimado ?? -999))
    .slice(0, 6);

  byId('marketsList').innerHTML = rows.map((m) => {
    const value = toNum(m.value_estimado);
    const badge = value != null && value >= 0.08 ? 'Convicção Alta' : value != null && value >= 0 ? 'Convicção Média' : 'Observar';
    const cls = value != null && value >= 0.08 ? 'good' : value != null && value >= 0 ? '' : 'warn';
    return `<article class="item"><p class="title">${m.team} · ${m.market}</p><p class="meta">Hit ${m.hit_rate != null ? fmtPct(m.hit_rate) : '—'} · Edge ${toNum(m.edge_vs_liga) != null ? `${fmtNum(m.edge_vs_liga * 100, 1)} pp` : '—'} · Jogos ${m.jogos}</p><span class="badge ${cls}">${badge}</span></article>`;
  }).join('') || '<p class="meta">Sem mercados suficientes.</p>';
}

function renderLay(league) {
  const rows = DATA.layRows
    .filter((r) => r.league === league)
    .sort((a, b) => Number(b.lay_score ?? -999) - Number(a.lay_score ?? -999))
    .slice(0, 10);

  byId('layList').innerHTML = rows.map((m) => `<article class="item"><p class="title">${m.team} · ${m.cenario_lay}</p><p class="meta">${m.descricao} · Hit: ${m.hit_rate != null ? fmtPct(m.hit_rate) : '—'} · Score: ${m.lay_score != null ? fmtNum(m.lay_score, 2) : '—'}</p><span class="badge ${m.flag_candidato ? 'good' : 'warn'}">${m.flag_candidato ? 'candidato' : 'observar'}</span></article>`).join('') || '<p class="meta">Sem cenários lay.</p>';
}

function renderHomeScannerTop(league, teamFilter = 'Todas') {
  const rows = DATA.marketRows
    .filter((r) => r.league === league && r.scope === 'Total' && Number(r.jogos || 0) >= 8 && (teamFilter === 'Todas' || r.team === teamFilter))
    .map((r) => ({ ...r, opportunityScore: opportunityScore(r) }))
    .sort((a, b) => Number(b.opportunityScore ?? -999) - Number(a.opportunityScore ?? -999))
    .slice(0, 5);
  byId('homeScannerTop').innerHTML = rows.length
    ? rows.map((r) => `<article class="item"><p class="title">${r.team} · ${r.market}</p><p class="meta">Score <strong>${r.opportunityScore}</strong> · Edge ${toNum(r.edge_vs_liga) != null ? `${fmtNum(r.edge_vs_liga * 100, 1)} pp` : '—'} · ${scoreBadge(r.opportunityScore)}</p></article>`).join('')
    : '<p class="meta">Sem oportunidades para esta liga.</p>';
}

function renderHomeScannerSummary(league, teamFilter = 'Todas') {
  const rows = DATA.marketRows
    .filter((r) => r.league === league && r.scope === 'Total' && Number(r.jogos || 0) >= 8 && (teamFilter === 'Todas' || r.team === teamFilter))
    .map((r) => ({ ...r, opportunityScore: opportunityScore(r) }))
    .sort((a, b) => Number(b.opportunityScore ?? -999) - Number(a.opportunityScore ?? -999))
    .slice(0, 5);
  byId('homeScannerSummary').innerHTML = rows.length
    ? rows.map((r) => `<article class="item"><p class="title">${r.team} · ${r.market}</p><p class="meta">Hit ${toNum(r.hit_rate) != null ? fmtPct(r.hit_rate) : '—'} · Jogos ${r.jogos} · Edge ${toNum(r.edge_vs_liga) != null ? `${fmtNum(r.edge_vs_liga * 100, 1)} pp` : '—'}</p></article>`).join('')
    : '<p class="meta">Sem sinais suficientes para resumo do scanner.</p>';
}

function renderHomeWatchlistCompact(league) {
  const keys = Array.from(WATCHLIST);
  const rows = keys.map((k) => parseWatchKey(k))
    .filter((x) => x && x.league === league)
    .map((x) => {
      const row = DATA.marketRows.find((r) => r.league === x.league && r.team === x.team && r.scope === x.scope && r.market === x.market);
      if (!row) return null;
      return row;
    })
    .filter(Boolean)
    .slice(0, 5);
  byId('homeWatchlistCompact').innerHTML = rows.length
    ? rows.map((r) => `<article class="item"><p class="title">${r.team} · ${r.market}</p><p class="meta">${r.scope} · Hit ${toNum(r.hit_rate) != null ? fmtPct(r.hit_rate) : '—'} · Edge ${toNum(r.edge_vs_liga) != null ? `${fmtNum(r.edge_vs_liga * 100, 1)} pp` : '—'}</p></article>`).join('')
    : '<p class="meta">Sem itens na watchlist desta liga.</p>';
}

function renderHomeOpsMeta() {
  const generatedAt = DATA.meta?.generatedAt ? String(DATA.meta.generatedAt) : '';
  const formatted = generatedAt
    ? new Date(generatedAt).toLocaleString('pt-PT', { timeZone: 'Europe/Lisbon' })
    : '—';
  const changes = (DATA.changelog || []).length;
  byId('homeLastUpdate').textContent = `Última atualização de dados: ${formatted} · changelog semanal: ${changes} registos.`;
}

function renderWeeklyVariation(league) {
  const teams = (DATA.rankings[league] || []).map((x) => x.team);
  const teamVar = teams.map((team) => {
    const all = DATA.seriesRows
      .filter((r) => r.league === league && r.team === team)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map((r) => Number(r.roll5_points))
      .filter((x) => Number.isFinite(x));
    if (all.length < 2) return null;
    const d = all[all.length - 1] - all[all.length - 2];
    return { team, delta: d };
  }).filter(Boolean).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 8);

  byId('variationTeams').innerHTML = teamVar.length
    ? teamVar.map((x) => `<article class="item"><p class="title">${x.team}</p><p class="meta">Variação pontos (últ. vs ant.): <strong>${x.delta >= 0 ? '+' : ''}${fmtNum(x.delta, 2)}</strong></p></article>`).join('')
    : '<p class="meta">Sem variação suficiente.</p>';

  const marketVar = DATA.marketRows
    .filter((r) => r.league === league && r.scope === 'Total')
    .map((r) => {
      const recent = toNum(r.form_recent_5);
      const season = toNum(r.hit_rate);
      if (recent == null || season == null) return null;
      return { team: r.team, market: r.market, delta: recent - season, recent, season };
    })
    .filter(Boolean)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 8);

  byId('variationMarkets').innerHTML = marketVar.length
    ? marketVar.map((x) => `<article class="item"><p class="title">${x.team} · ${x.market}</p><p class="meta">Forma 5J vs época: ${fmtPct(x.recent)} vs ${fmtPct(x.season)} · <strong>${x.delta >= 0 ? '+' : ''}${fmtNum(x.delta * 100, 1)} pp</strong></p></article>`).join('')
    : '<p class="meta">Sem variação suficiente.</p>';
}

function renderWeeklyAlerts(league) {
  const payload = DATA.weeklyAlerts || { summary: { total: 0, high: 0, medium: 0 }, byLeague: {} };
  const leagueAlerts = (payload.byLeague && payload.byLeague[league]) ? payload.byLeague[league] : [];
  const top = leagueAlerts.slice(0, 12);
  const high = top.filter((a) => a.severity === 'high').length;
  const medium = top.filter((a) => a.severity === 'medium').length;
  byId('weeklyAlertsMeta').textContent = top.length
    ? `${top.length} alertas nesta liga · ${high} high · ${medium} medium`
    : 'Sem alertas relevantes para esta liga na atualização atual.';

  byId('weeklyAlertsList').innerHTML = top.length
    ? top.map((a) => {
      const sevClass = a.severity === 'high' ? 'warn' : '';
      const sevLabel = a.severity === 'high' ? 'HIGH' : 'MEDIUM';
      const dir = a.direction === 'up' ? '↑' : '↓';
      const typeLabel = a.type === 'team_form' ? 'Equipa' : 'Mercado';
      return `<article class="item"><p class="title">${dir} ${a.entity}${a.market ? ` · ${a.market}` : ''}</p><p class="meta">${a.message}</p><span class="badge ${sevClass}">${typeLabel} · ${sevLabel}</span></article>`;
    }).join('')
    : '<p class="meta">Sem alertas automáticos para mostrar.</p>';
}

function renderSosTable(league) {
  const rows = (DATA.phase2Sos || [])
    .filter((r) => r.league === league)
    .sort((a, b) => Number(b.adj_ppg ?? -999) - Number(a.adj_ppg ?? -999))
    .slice(0, 20);
  byId('sosTable').querySelector('tbody').innerHTML = rows.length
    ? rows.map((r) => `<tr><td>${r.team}</td><td>${fmtNum(r.raw_ppg)}</td><td>${fmtNum(r.sos_ppg)}</td><td>${fmtNum(r.adj_ppg)}</td><td>${r.last5_ppg != null ? fmtNum(r.last5_ppg) : '—'}</td><td>${r.sample_matches}</td></tr>`).join('')
    : '<tr><td colspan="6">Sem dados SOS.</td></tr>';
  applyExistingSort('sosTable');
}

function renderOverview(league) {
  syncDashboardTeamOptions(league);
  const teamFilter = byId('dashboardTeamSelect')?.value || 'Todas';
  renderMatchOfWeek(league);
  renderMarkets(league, teamFilter);
  renderHomeScannerTop(league, teamFilter);
  renderHomeScannerSummary(league, teamFilter);
  renderHomeWatchlistCompact(league);
  renderHomeOpsMeta();
  renderWeeklyAlerts(league);
}

function populateScannerFilters(leagues) {
  byId('scanLeague').innerHTML = ['Todas', ...leagues].map((l) => `<option value="${l}">${l === 'Todas' ? l : leagueLabel(l)}</option>`).join('');
}

function marketInGroup(market, group) {
  const m = String(market || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  if (group === 'todos') return true;
  if (!m) return false;

  const isCorners = m.includes('canto');
  const isBtts = m.includes('btts') || m.includes('ambas marcam');
  const isGoalCore = m.includes('golo')
    || m.includes('casa marca')
    || m.includes('clean sheet')
    || m.includes('over 1.5')
    || m.includes('over 2.5')
    || m.includes('over 3.5')
    || m.includes('under 2.5');
  const isResult = m.includes('vitoria')
    || m.includes('empate')
    || m.includes('1x2')
    || m.includes('handicap');

  if (group === 'cantos') return isCorners;
  if (group === 'btts') return isBtts;
  if (group === 'golos') return isGoalCore && !isCorners && !isBtts;
  if (group === 'resultados') return isResult && !isCorners;
  return true;
}

function renderScanner() {
  const league = byId('scanLeague').value;
  const scope = byId('scanScope').value;
  const group = byId('scanGroup').value;
  const minGames = Number(byId('scanMinGames').value || 1);

  let rows = DATA.marketRows.filter((r) => (league === 'Todas' || r.league === league)
    && r.scope === scope
    && Number(r.jogos || 0) >= minGames
    && marketInGroup(r.market, group));
  rows = rows
    .map((r) => ({ ...r, opportunityScore: opportunityScore(r) }))
    .sort((a, b) => Number(b.opportunityScore ?? -999) - Number(a.opportunityScore ?? -999));

  const shown = rows.slice(0, 120);
  const avgOpp = shown.length ? Math.round(shown.reduce((acc, r) => acc + (r.opportunityScore || 0), 0) / shown.length) : null;
  const top = shown[0];
  const meta = byId('scannerMeta');
  if (meta) {
    meta.textContent = shown.length
      ? `${shown.length} mercados listados · oportunidade média ${avgOpp} · topo: ${top.team} (${top.market})`
      : 'Sem mercados para estes filtros.';
  }

  byId('scannerTable').querySelector('tbody').innerHTML = shown.map((r) => {
    const key = watchKey(r);
    const watched = WATCHLIST.has(key);
    const sq = sampleQuality(r.jogos);
    return `<tr>
      <td><button class="watch-btn ${watched ? 'active' : ''}" data-watch-key="${key}" title="Adicionar/remover watchlist">${watched ? '★' : '☆'}</button></td>
      <td>${r.team}</td>
      <td>${r.market}</td>
      <td>${r.jogos}</td>
      <td>${r.hit_rate != null ? fmtPct(r.hit_rate) : '—'}</td>
      <td>${renderCiCell(r)}</td>
      <td>${miniSparkline(r)}</td>
      <td><span class="badge ${sq.cls}">${sq.label}</span></td>
      <td>${r.opportunityScore}<br>${scoreBadge(r.opportunityScore)}</td>
      <td>${r.edge_vs_liga != null ? `${fmtNum(r.edge_vs_liga * 100, 1)} pp` : '—'}</td>
      <td>${r.roi_unid_por_aposta != null ? fmtNum(r.roi_unid_por_aposta, 3) : '—'}</td>
      <td>${r.value_estimado != null ? `${fmtNum(r.value_estimado * 100, 1)}%` : '—'}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="12">Sem dados para os filtros escolhidos.</td></tr>';

  byId('scannerTable').querySelectorAll('.watch-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.watchKey;
      if (!key) return;
      if (WATCHLIST.has(key)) WATCHLIST.delete(key); else WATCHLIST.add(key);
      saveWatchlist();
      renderScanner();
    });
  });
  renderWatchlistPanel();
  applyExistingSort('scannerTable');
}

function renderCiCell(r) {
  const lo = toNum(r.wilson_lo);
  const hi = toNum(r.wilson_hi);
  const hr = toNum(r.hit_rate);
  if (lo == null || hi == null || hr == null) return '—';
  const left = clamp(lo * 100, 0, 100);
  const right = clamp(hi * 100, 0, 100);
  const point = clamp(hr * 100, 0, 100);
  return `<div class="ci-cell"><div class="ci-track"><span class="ci-range" style="left:${left}%;width:${Math.max(1,right-left)}%"></span><span class="ci-point" style="left:${point}%"></span></div><div class="ci-label">${fmtPct(lo)}–${fmtPct(hi)}</div></div>`;
}

function renderWatchlistPanel() {
  const el = byId('scannerWatchlist');
  if (!el) return;
  const items = Array.from(WATCHLIST).map((k) => {
    const [league, team, scope, market] = k.split('|');
    return { key: k, league, team, scope, market };
  });
  el.innerHTML = items.length
    ? items.map((x) => `<article class="item"><p class="title">${x.team} · ${x.market}</p><p class="meta">${leagueLabel(x.league)} · ${x.scope}</p><button class="ghost-btn watch-remove" data-watch-key="${x.key}">Remover</button></article>`).join('')
    : '<p class="meta">Sem mercados guardados na watchlist.</p>';

  el.querySelectorAll('.watch-remove').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.watchKey;
      if (!key) return;
      WATCHLIST.delete(key);
      saveWatchlist();
      renderScanner();
    });
  });
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

function renderMatchupExecutive(league, home, away) {
  const el = byId('matchupExecutive');
  if (!el) return;
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  if (!h || !a) {
    el.innerHTML = '<p class="meta">Sem dados suficientes para resumo executivo do matchup.</p>';
    return;
  }

  const ppgDelta = Number(h.ppg) - Number(a.ppg);
  const overAvg = avg([Number(h['O2.5%']), Number(a['O2.5%'])]);
  const merged = buildConfrontoMerged(league, home, away).sort((x, y) => Number(y.avg) - Number(x.avg));
  const topMarket = merged[0] || null;
  const conf = matchConfidence(league, home, away);

  const direction = ppgDelta >= 0
    ? `vantagem estrutural da casa (${home})`
    : `vantagem estrutural visitante (${away})`;
  const rhythm = overAvg != null && overAvg >= 0.57
    ? 'ritmo projetado alto'
    : 'ritmo projetado controlado';

  el.innerHTML = `
    <p class="title">Resumo Executivo: ${direction}</p>
    <p class="meta">${leagueLabel(league)} · ${rhythm} · leitura rápida para decisão pré-jogo.</p>
    <div class="chips">
      <span class="chip">Delta PPG: ${ppgDelta >= 0 ? '+' : ''}${fmtNum(ppgDelta, 2)}</span>
      <span class="chip">Confiança: ${conf ? conf.score : '—'}/100</span>
      <span class="chip">Top mercado: ${topMarket ? topMarket.market : '—'}</span>
      <span class="chip">Edge médio topo: ${topMarket ? `${fmtNum(topMarket.avg * 100, 1)} pp` : '—'}</span>
    </div>
  `;
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

function regressionAlertForTeam(league, team, scopeLabel) {
  const scope = scopeLabel === 'Casa' ? 'Casa' : 'Fora';
  const venue = scopeLabel === 'Casa' ? 'H' : 'A';
  const row = getResumoRow(league, team, scope);
  if (!row) return null;

  const series = getSeries(league, team, venue, 'roll5_points').filter((x) => Number.isFinite(x.value));
  if (!series.length) return null;

  const recent = series[series.length - 1].value;
  const expected = Number(row.ppg) * 5;
  if (!Number.isFinite(recent) || !Number.isFinite(expected)) return null;

  const gap = recent - expected;
  if (gap >= 1.2) {
    return `${team}: rendimento recente acima do esperado (+${fmtNum(gap, 2)} pts/5j), possível regressão à média.`;
  }
  if (gap <= -1.2) {
    return `${team}: rendimento recente abaixo do esperado (${fmtNum(gap, 2)} pts/5j), possível recuperação à média.`;
  }
  return null;
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

  const regHome = regressionAlertForTeam(league, home, 'Casa');
  const regAway = regressionAlertForTeam(league, away, 'Fora');
  if (regHome) out.push(regHome);
  if (regAway) out.push(regAway);

  return out.slice(0, 5);
}

function renderConfrontoInsights(league, home, away) {
  const insights = matchupInsights(league, home, away);
  byId('confrontoInsights').innerHTML = insights.length
    ? insights.map((x) => `<li>${x}</li>`).join('')
    : '<li>Sem sinais fortes para este matchup com os dados atuais.</li>';
}

function processMetricsFromResumoRow(row) {
  if (!row) return null;
  const shots = toNum(row.remates);
  const sot = toNum(row.SOT);
  const shotsA = toNum(row.remates_sofridos);
  const sotA = toNum(row.SOT_sofridos);
  const gf = toNum(row.golos_marcados);
  const ga = toNum(row.golos_sofridos);
  if ([shots, sot, shotsA, sotA, gf, ga].some((x) => x == null)) return null;

  const xg = (shots * 0.10) + (sot * 0.20);
  const xga = (shotsA * 0.10) + (sotA * 0.20);
  const xgPerShot = shots > 0 ? xg / shots : null;
  const xgaPerShot = shotsA > 0 ? xga / shotsA : null;
  const goalsMinusXg = gf - xg;
  const goalsConcededMinusXga = ga - xga;
  const bigChancesProxy = sot * 0.65;
  const boxShotsProxy = shots * 0.55;
  return {
    xg,
    xga,
    xgPerShot,
    xgaPerShot,
    goalsMinusXg,
    goalsConcededMinusXga,
    bigChancesProxy,
    boxShotsProxy
  };
}

function renderProcessLayer(league, home, away) {
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  const hm = processMetricsFromResumoRow(h);
  const am = processMetricsFromResumoRow(a);
  const el = byId('processLayerCards');
  if (!el) return;
  if (!hm || !am) {
    el.innerHTML = '<article class="kpi-card"><h3>Processo</h3><p class="meta">Sem dados suficientes para calcular a camada de processo.</p></article>';
    return;
  }
  el.innerHTML = `
    <article class="kpi-card">
      <h3>${home} (Casa)</h3>
      <div class="kpi-row"><span>xG proxy</span><strong>${fmtNum(hm.xg, 2)}</strong></div>
      <div class="kpi-row"><span>xGA proxy</span><strong>${fmtNum(hm.xga, 2)}</strong></div>
      <div class="kpi-row"><span>Golos - xG</span><strong>${hm.goalsMinusXg >= 0 ? '+' : ''}${fmtNum(hm.goalsMinusXg, 2)}</strong></div>
      <div class="kpi-row"><span>Big chances (proxy)</span><strong>${fmtNum(hm.bigChancesProxy, 2)}</strong></div>
    </article>
    <article class="kpi-card">
      <h3>${away} (Fora)</h3>
      <div class="kpi-row"><span>xG proxy</span><strong>${fmtNum(am.xg, 2)}</strong></div>
      <div class="kpi-row"><span>xGA proxy</span><strong>${fmtNum(am.xga, 2)}</strong></div>
      <div class="kpi-row"><span>Golos - xG</span><strong>${am.goalsMinusXg >= 0 ? '+' : ''}${fmtNum(am.goalsMinusXg, 2)}</strong></div>
      <div class="kpi-row"><span>Big chances (proxy)</span><strong>${fmtNum(am.bigChancesProxy, 2)}</strong></div>
    </article>
    <article class="kpi-card">
      <h3>Comparação direta</h3>
      <div class="kpi-row"><span>xG diff (Casa-Fora)</span><strong>${fmtNum(hm.xg - am.xg, 2)}</strong></div>
      <div class="kpi-row"><span>xGA diff (Casa-Fora)</span><strong>${fmtNum(hm.xga - am.xga, 2)}</strong></div>
      <div class="kpi-row"><span>xG/remate (Casa)</span><strong>${hm.xgPerShot != null ? fmtNum(hm.xgPerShot, 3) : '—'}</strong></div>
      <div class="kpi-row"><span>xG/remate (Fora)</span><strong>${am.xgPerShot != null ? fmtNum(am.xgPerShot, 3) : '—'}</strong></div>
    </article>
    <article class="kpi-card">
      <h3>Leitura de eficiência</h3>
      <div class="kpi-row"><span>${home} golos - xG</span><strong>${hm.goalsMinusXg >= 0 ? '+' : ''}${fmtNum(hm.goalsMinusXg, 2)}</strong></div>
      <div class="kpi-row"><span>${away} golos - xG</span><strong>${am.goalsMinusXg >= 0 ? '+' : ''}${fmtNum(am.goalsMinusXg, 2)}</strong></div>
      <div class="kpi-row"><span>${home} golos sofridos - xGA</span><strong>${hm.goalsConcededMinusXga >= 0 ? '+' : ''}${fmtNum(hm.goalsConcededMinusXga, 2)}</strong></div>
      <div class="kpi-row"><span>${away} golos sofridos - xGA</span><strong>${am.goalsConcededMinusXga >= 0 ? '+' : ''}${fmtNum(am.goalsConcededMinusXga, 2)}</strong></div>
    </article>
  `;
}

function normalizeTeamName(s) {
  return String(s || '')
    .toLowerCase()
    .trim()
    .replace(/[.'’-]/g, '')
    .replace(/\b(fc|cf|ac|sc)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function teamContextFor(league, team) {
  const byLeague = DATA.teamContextByLeague?.[league] || {};
  if (byLeague[team]) return byLeague[team];
  const normMap = DATA.teamContextByLeagueNorm?.[league] || {};
  const n = normalizeTeamName(team);
  if (normMap[n]) return normMap[n];
  const keys = Object.keys(normMap);
  for (const k of keys) {
    if (k === n || k.includes(n) || n.includes(k)) return normMap[k];
  }
  return null;
}

function renderTeamContext(league, home, away) {
  const el = byId('teamContextCards');
  if (!el) return;
  const h = teamContextFor(league, home);
  const a = teamContextFor(league, away);
  const meta = DATA.teamContextMeta || {};
  const errors = Array.isArray(DATA.teamContextErrors) ? DATA.teamContextErrors : [];

  if (!h && !a) {
    const reason = !meta.keyConfigured
      ? 'API_FOOTBALL_KEY não configurada.'
      : (errors.length ? errors.join(' | ') : 'A API devolveu sem registos para esta janela/competições.');
    el.innerHTML = `
      <article class="kpi-card">
        <h3>Disponibilidade indisponível nesta atualização</h3>
        <div class="kpi-row"><span>Provider</span><strong>${meta.provider || 'api-football'}</strong></div>
        <div class="kpi-row"><span>Chave API</span><strong>${meta.keyConfigured ? 'Configurada' : 'Não configurada'}</strong></div>
        <p class="meta">${reason}</p>
      </article>
    `;
    return;
  }

  const card = (team, ctx) => {
    if (!ctx) {
      return `<article class="kpi-card"><h3>${team}</h3><p class="meta">Sem disponibilidade específica para esta equipa na resposta atual.</p></article>`;
    }
    const abs = (ctx.keyAbsences || []).slice(0, 3);
    return `<article class="kpi-card">
      <h3>${team}</h3>
      <div class="kpi-row"><span>Indisponíveis</span><strong>${ctx.unavailableCount ?? 0}</strong></div>
      <div class="kpi-row"><span>Lesionados</span><strong>${ctx.injuryCount ?? 0}</strong></div>
      <div class="kpi-row"><span>Suspensos</span><strong>${ctx.suspensionCount ?? 0}</strong></div>
      <div class="kpi-row"><span>XI provável (formação)</span><strong>${ctx.probableFormation || '—'}</strong></div>
      <p class="meta">${abs.length ? `Baixas chave: ${abs.map((x) => x.player).join(', ')}` : 'Sem baixas chave mapeadas.'}</p>
    </article>`;
  };

  el.innerHTML = `
    ${card(home, h)}
    ${card(away, a)}
    <article class="kpi-card">
      <h3>Fonte e atualização</h3>
      <div class="kpi-row"><span>Provider</span><strong>${meta.provider || '—'}</strong></div>
      <div class="kpi-row"><span>Atualizado</span><strong>${meta.generatedAt ? String(meta.generatedAt).slice(0, 16).replace('T', ' ') : '—'}</strong></div>
      <div class="kpi-row"><span>Chave API</span><strong>${meta.keyConfigured ? 'Configurada' : 'Não configurada'}</strong></div>
      <p class="meta">Quando disponível, o XI provável é inferido da formação prevista no próximo jogo.</p>
    </article>
  `;
}

function styleVector(row) {
  if (!row) return null;
  const shots = toNum(row.remates) ?? 0;
  const sot = toNum(row.SOT) ?? 0;
  const conv = toNum(row.conversion_rate) ?? 0;
  const corners = toNum(row.cantos) ?? 0;
  const againstShots = toNum(row.remates_sofridos) ?? 0;
  const againstSot = toNum(row.SOT_sofridos) ?? 0;
  const gpm = toNum(row.golos_marcados) ?? 0;

  const directness = clamp((conv * 2.2) + (gpm * 0.35) - (shots * 0.03), 0, 1);
  const crossingBias = clamp(corners / 7.5, 0, 1);
  const transitionBias = clamp((sot / Math.max(shots, 1)) * 2.2, 0, 1);
  const pressProxy = clamp(1 - (againstShots / 16), 0, 1);
  const ppdaProxy = Number.isFinite(againstSot) ? (againstShots / Math.max(againstSot, 0.5)) : null;
  return { directness, crossingBias, transitionBias, pressProxy, ppdaProxy };
}

function styleLabel(v) {
  if (!v) return 'Sem perfil';
  const tags = [];
  if (v.pressProxy >= 0.62) tags.push('pressão alta (proxy)');
  if (v.directness >= 0.58) tags.push('jogo direto');
  if (v.crossingBias >= 0.55) tags.push('dependência de cruzamentos');
  if (v.transitionBias >= 0.56) tags.push('ataques rápidos');
  if (!tags.length) tags.push('perfil equilibrado');
  return tags.join(' · ');
}

function renderStyleMismatch(league, home, away) {
  const el = byId('styleMismatchCards');
  if (!el) return;
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  const hs = styleVector(h);
  const as = styleVector(a);
  if (!hs || !as) {
    el.innerHTML = '<article class="kpi-card"><h3>Style Mismatch</h3><p class="meta">Sem dados suficientes para classificar estilos.</p></article>';
    return;
  }
  const mismatch = Math.abs(hs.directness - as.directness)
    + Math.abs(hs.crossingBias - as.crossingBias)
    + Math.abs(hs.transitionBias - as.transitionBias)
    + Math.abs(hs.pressProxy - as.pressProxy);
  const mismatchScore = Math.round((mismatch / 4) * 100);
  const verdict = mismatchScore >= 55 ? 'choque elevado de estilos' : mismatchScore >= 35 ? 'choque moderado' : 'encaixe mais neutro';

  const clashes = [];
  if (hs.pressProxy - as.pressProxy >= 0.16) clashes.push(`${home} tende a pressionar mais alto do que ${away}.`);
  else if (as.pressProxy - hs.pressProxy >= 0.16) clashes.push(`${away} tende a pressionar mais alto do que ${home}.`);
  if (Math.abs(hs.directness - as.directness) >= 0.18) clashes.push('Diferença relevante entre jogo direto e construção.');
  if (Math.abs(hs.crossingBias - as.crossingBias) >= 0.18) clashes.push('Assimetria no uso de cruzamentos e bolas laterais.');
  if (Math.abs(hs.transitionBias - as.transitionBias) >= 0.18) clashes.push('Ritmo de transição ofensiva em conflito.');
  if (!clashes.length) clashes.push('Perfis relativamente próximos; matchup tende a ser mais tático e menos caótico.');

  el.innerHTML = `
    <article class="kpi-card">
      <h3>Leitura executiva de estilos</h3>
      <div class="kpi-row"><span>Mismatch score</span><strong>${mismatchScore}/100</strong></div>
      <div class="kpi-row"><span>Diagnóstico</span><strong>${verdict}</strong></div>
      <p class="meta">${clashes.slice(0, 2).join(' ')}</p>
      <p class="meta">*PPDA proxy: estimativa por remates permitidos vs remates à baliza sofridos (não é PPDA oficial).</p>
    </article>
    <article class="kpi-card">
      <h3>Comparação de perfil</h3>
      <div class="kpi-row"><span>${home}</span><strong>${styleLabel(hs)}</strong></div>
      <div class="kpi-row"><span>${away}</span><strong>${styleLabel(as)}</strong></div>
      <div class="kpi-row"><span>PPDA proxy (${home})</span><strong>${hs.ppdaProxy != null ? fmtNum(hs.ppdaProxy, 2) : '—'}</strong></div>
      <div class="kpi-row"><span>PPDA proxy (${away})</span><strong>${as.ppdaProxy != null ? fmtNum(as.ppdaProxy, 2) : '—'}</strong></div>
    </article>
  `;
}

function nearestFixtureDateForTeam(league, team) {
  const target = normalizeTeamName(team);
  const list = Array.isArray(DATA.upcomingFixtures) ? DATA.upcomingFixtures : [];
  const hits = list
    .filter((f) => f.league === league)
    .filter((f) => {
      const h = normalizeTeamName(f.homeTeamApi || f.homeTeamNorm);
      const a = normalizeTeamName(f.awayTeamApi || f.awayTeamNorm);
      return h === target || a === target || h.includes(target) || a.includes(target) || target.includes(h) || target.includes(a);
    })
    .map((f) => new Date(f.utcDate || f.fixtureUtcDate || f.date))
    .filter((d) => !Number.isNaN(d.getTime()))
    .sort((x, y) => x.getTime() - y.getTime());
  return hits[0] || null;
}

function lastMatchDateForTeam(league, team) {
  const rows = (DATA.seriesRows || [])
    .filter((r) => r.league === league && r.team === team)
    .map((r) => new Date(r.date))
    .filter((d) => !Number.isNaN(d.getTime()))
    .sort((a, b) => a.getTime() - b.getTime());
  return rows.length ? rows[rows.length - 1] : null;
}

function gamesInWindow(league, team, endDate, daysBack) {
  if (!endDate) return 0;
  const start = new Date(endDate);
  start.setDate(start.getDate() - daysBack);
  return (DATA.seriesRows || [])
    .filter((r) => r.league === league && r.team === team)
    .map((r) => new Date(r.date))
    .filter((d) => !Number.isNaN(d.getTime()) && d >= start && d < endDate)
    .length;
}

function rotationRiskLabel(unavailable, daysRest, games8) {
  let score = 0;
  if ((unavailable || 0) >= 4) score += 2;
  else if ((unavailable || 0) >= 2) score += 1;
  if ((daysRest ?? 99) <= 3) score += 2;
  else if ((daysRest ?? 99) <= 5) score += 1;
  if ((games8 || 0) >= 2) score += 2;
  if (score >= 5) return 'Alta';
  if (score >= 3) return 'Média';
  return 'Baixa';
}

function fallbackFatigueConfidence(nextFx, lastFx, daysRest) {
  if (!nextFx || !lastFx) return false;
  if (!Number.isFinite(daysRest)) return false;
  if (daysRest < 0 || daysRest > 14) return false;
  const now = new Date();
  const lastAgeDays = Math.max(0, Math.round((now - lastFx) / 86400000));
  return lastAgeDays <= 21;
}

function renderFatigueRotation(league, home, away) {
  const el = byId('fatigueRotationCards');
  if (!el) return;
  const homeCtx = teamContextFor(league, home) || {};
  const awayCtx = teamContextFor(league, away) || {};

  const build = (team, ctx) => {
    const apiFatigue = ctx?.fatigue || {};
    const hasApiFatigue = apiFatigue && Object.keys(apiFatigue).length > 0;
    const nextFx = hasApiFatigue && apiFatigue.referenceFixtureDate
      ? new Date(apiFatigue.referenceFixtureDate)
      : nearestFixtureDateForTeam(league, team);
    const lastFx = lastMatchDateForTeam(league, team);
    const rawDaysRest = hasApiFatigue
      ? (toNum(apiFatigue.daysRest) != null ? Number(apiFatigue.daysRest) : null)
      : ((nextFx && lastFx) ? Math.max(0, Math.round((nextFx - lastFx) / 86400000)) : null);
    const fallbackOk = hasApiFatigue || fallbackFatigueConfidence(nextFx, lastFx, rawDaysRest);
    const daysRest = fallbackOk ? rawDaysRest : null;
    const rawGames8 = hasApiFatigue
      ? Number(apiFatigue.gamesLast8d || 0)
      : (nextFx ? gamesInWindow(league, team, nextFx, 8) : 0);
    const games8 = fallbackOk ? rawGames8 : null;
    const thirdIn8 = !fallbackOk
      ? 'N/D'
      : (hasApiFatigue
      ? (apiFatigue.thirdGameIn8d ? 'Sim' : 'Não')
      : (games8 >= 2 ? 'Sim' : 'Não'));
    const euroBefore = hasApiFatigue ? !!apiFatigue.europeanBefore : false;
    const euroAfter = hasApiFatigue ? !!apiFatigue.europeanAfter : false;
    const extraTimeRecent = hasApiFatigue ? !!apiFatigue.extraTimeRecent : false;
    const risk = rotationRiskLabel(ctx.unavailableCount || 0, daysRest, games8);
    return { team, daysRest, games8, thirdIn8, risk, euroBefore, euroAfter, extraTimeRecent, hasApiFatigue, fallbackOk };
  };

  const h = build(home, homeCtx);
  const a = build(away, awayCtx);
  const riskSummary = (h.risk === 'Alta' || a.risk === 'Alta')
    ? 'Risco elevado de rotação em pelo menos uma equipa.'
    : (h.risk === 'Média' || a.risk === 'Média')
      ? 'Risco moderado de rotação; confirmar onze inicial.'
      : 'Carga competitiva controlada para as duas equipas.';
  const sourceLabel = (h.hasApiFatigue && a.hasApiFatigue)
    ? 'API multi-competição'
    : ((h.hasApiFatigue || a.hasApiFatigue) ? 'Misto (API + fallback doméstico)' : 'Fallback doméstico local');
  const lowConfidenceNote = (!h.hasApiFatigue && !h.fallbackOk) || (!a.hasApiFatigue && !a.fallbackOk)
    ? '<p class="meta">Nota: fallback local com baixa confiança temporal (pode estar desatualizado).</p>'
    : '';

  el.innerHTML = `
    <article class="kpi-card">
      <h3>Resumo de carga competitiva</h3>
      <div class="kpi-row"><span>${home}</span><strong>${h.risk} (descanso ${h.daysRest != null ? h.daysRest : '—'}d)</strong></div>
      <div class="kpi-row"><span>${away}</span><strong>${a.risk} (descanso ${a.daysRest != null ? a.daysRest : '—'}d)</strong></div>
      <p class="meta">${riskSummary}</p>
      <p class="meta">Jogo europeu antes/depois: ${home} ${h.euroBefore ? 'Sim' : 'Não'}/${h.euroAfter ? 'Sim' : 'Não'} · ${away} ${a.euroBefore ? 'Sim' : 'Não'}/${a.euroAfter ? 'Sim' : 'Não'}.</p>
      <p class="meta">Prolongamento recente: ${home} ${h.extraTimeRecent ? 'Sim' : 'Não'} · ${away} ${a.extraTimeRecent ? 'Sim' : 'Não'}.</p>
    </article>
    <article class="kpi-card">
      <h3>Detalhe por equipa</h3>
      <div class="kpi-row"><span>${home}: jogos últimos 8d</span><strong>${h.games8 != null ? h.games8 : 'N/D'}</strong></div>
      <div class="kpi-row"><span>${home}: 3.º jogo em 8d</span><strong>${h.thirdIn8}</strong></div>
      <div class="kpi-row"><span>${away}: jogos últimos 8d</span><strong>${a.games8 != null ? a.games8 : 'N/D'}</strong></div>
      <div class="kpi-row"><span>${away}: 3.º jogo em 8d</span><strong>${a.thirdIn8}</strong></div>
      <p class="meta">Fonte de fadiga: ${sourceLabel}</p>
      ${lowConfidenceNote}
    </article>
  `;
}

function renderSetPiecesModule(league, home, away) {
  const el = byId('setPiecesCards');
  if (!el) return;
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  if (!h || !a) {
    el.innerHTML = '<article class="kpi-card"><h3>Bolas paradas</h3><p class="meta">Sem dados suficientes.</p></article>';
    return;
  }

  const card = (team, row) => {
    const cornersFor = toNum(row.cantos);
    const cornersAgainst = toNum(row.cantos_sofridos);
    const yellows = toNum(row.amarelos);
    const yellowsAgainst = toNum(row.amarelos_sofridos);
    const setPieceThreat = ((cornersFor ?? 0) * 0.65) + ((toNum(row.SOT) ?? 0) * 0.35);
    return `<article class="kpi-card">
      <h3>${team}</h3>
      <div class="kpi-row"><span>Cantos a favor (90')</span><strong>${cornersFor != null ? fmtNum(cornersFor, 2) : '—'}</strong></div>
      <div class="kpi-row"><span>Cantos contra (90')</span><strong>${cornersAgainst != null ? fmtNum(cornersAgainst, 2) : '—'}</strong></div>
      <div class="kpi-row"><span>Cartões (proxy 90')</span><strong>${yellows != null ? fmtNum(yellows, 2) : '—'}</strong></div>
      <div class="kpi-row"><span>Set-piece threat (proxy)</span><strong>${fmtNum(setPieceThreat, 2)}</strong></div>
      <p class="meta">Faltas, árbitro e tendência penalties: N/D sem feed dedicado.</p>
    </article>`;
  };

  el.innerHTML = `
    ${card(home, h)}
    ${card(away, a)}
  `;
}

function populateConfronto(leagues) {
  const leagueSel = byId('cfLeague');
  leagueSel.innerHTML = leagueOptions(leagues);

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
  renderMatchupExecutive(league, home, away);
  renderConfrontoKpis(league, home, away);
  renderRadarSection(league, home, away);
  renderCompareSection(league, home, away);
  renderProcessLayer(league, home, away);
  renderStyleMismatch(league, home, away);
  renderConfrontoMarkets(league, home, away);
  renderConfrontoInsights(league, home, away);
  renderTeamContext(league, home, away);
  renderFatigueRotation(league, home, away);
  renderSetPiecesModule(league, home, away);
  renderH2H(league, home, away);
}

function renderCompareSection(league, home, away) {
  const homePoints = getSeries(league, home, 'H', 'roll5_points').filter((x) => Number.isFinite(x.value));
  const awayPoints = getSeries(league, away, 'A', 'roll5_points').filter((x) => Number.isFinite(x.value));
  drawCompareLineChart(homePoints, awayPoints, home, away);

  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  if (!h || !a) {
    byId('compareDeltaTable').querySelector('tbody').innerHTML = '<tr><td colspan="4">Sem dados para comparar.</td></tr>';
    return;
  }

  const rows = [
    ['PPG', Number(h.ppg), Number(a.ppg)],
    ['Vitórias %', Number(h['vit%']) * 100, Number(a['vit%']) * 100],
    ['Golos marcados', Number(h.golos_marcados), Number(a.golos_marcados)],
    ['Golos sofridos', Number(h.golos_sofridos), Number(a.golos_sofridos)],
    ['BTTS %', Number(h['BTTS%']) * 100, Number(a['BTTS%']) * 100],
    ['Over 2.5 %', Number(h['O2.5%']) * 100, Number(a['O2.5%']) * 100]
  ];

  byId('compareDeltaTable').querySelector('tbody').innerHTML = rows.map(([m, hv, av]) => {
    const d = hv - av;
    const suffix = m.includes('%') ? '%' : '';
    return `<tr><td>${m}</td><td>${fmtNum(hv, 2)}${suffix}</td><td>${fmtNum(av, 2)}${suffix}</td><td>${d >= 0 ? '+' : ''}${fmtNum(d, 2)}${suffix}</td></tr>`;
  }).join('');
  applyExistingSort('compareDeltaTable');
}

function drawCompareLineChart(homeSeries, awaySeries, homeName, awayName) {
  const svg = byId('compareLineChart');
  const t = chartTheme();
  if (!svg) return;
  if (!homeSeries.length && !awaySeries.length) {
    svg.innerHTML = `<text x="16" y="28" fill="${t.muted}" font-size="14">Sem séries para comparar.</text>`;
    return;
  }

  const width = 760;
  const height = 300;
  const margin = { top: 18, right: 18, bottom: 34, left: 42 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;

  const maxN = Math.max(homeSeries.length, awaySeries.length, 2);
  const allVals = homeSeries.concat(awaySeries).map((x) => x.value).filter((v) => Number.isFinite(v));
  const minV = Math.min(...allVals, 0);
  const maxV = Math.max(...allVals, 1);
  const yMin = minV === maxV ? minV - 1 : minV;
  const yMax = minV === maxV ? maxV + 1 : maxV;

  const xAt = (i, n) => margin.left + (i / Math.max(n - 1, 1)) * chartW;
  const yAt = (v) => margin.top + (1 - ((v - yMin) / (yMax - yMin))) * chartH;

  const toPoints = (arr) => arr.map((p, i) => `${xAt(i, arr.length)},${yAt(p.value)}`).join(' ');
  const hPts = homeSeries.length ? toPoints(homeSeries) : '';
  const aPts = awaySeries.length ? toPoints(awaySeries) : '';

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="${t.bg}"/>
    <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="${t.grid}"/>
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="${t.grid}"/>
    ${hPts ? `<polyline fill="none" stroke="${t.main}" stroke-width="2.5" points="${hPts}" />` : ''}
    ${aPts ? `<polyline fill="none" stroke="${t.alt}" stroke-width="2.5" points="${aPts}" />` : ''}
    <text x="${margin.left}" y="14" fill="${t.main}" font-size="12">${homeName} (Casa)</text>
    <text x="${width - margin.right}" y="14" text-anchor="end" fill="${t.alt}" font-size="12">${awayName} (Fora)</text>
    <text x="${margin.left}" y="${height - 8}" fill="${t.axis}" font-size="11">Início</text>
    <text x="${width - margin.right}" y="${height - 8}" text-anchor="end" fill="${t.axis}" font-size="11">Recente</text>
  `;
}

function renderMatchOfWeek(league) {
  const bestApi = DATA.matchOfWeekByLeague?.[league];
  if (bestApi && bestApi.homeTeam && bestApi.awayTeam) {
    const topMarkets = Array.isArray(bestApi.topMarkets) ? bestApi.topMarkets : [];
    const marketsText = topMarkets.length
      ? topMarkets.map((m) => `${m.market}${toNum(m.avg_edge) != null ? ` (${fmtNum(m.avg_edge * 100, 1)} pp)` : ''}`).join(' · ')
      : 'Sem mercados convergentes fortes.';
    const dt = bestApi.fixtureUtcDate
      ? new Date(bestApi.fixtureUtcDate).toLocaleString('pt-PT', { timeZone: 'Europe/Lisbon' })
      : (bestApi.fixtureDate || '—');
    const conf = toNum(bestApi.confidenceScore);
    const reading = conf != null && conf >= 70
      ? 'Jogo real do fim de semana com sinais fortes de convergência.'
      : 'Jogo real do fim de semana com leitura equilibrada e oportunidade monitorizada.';

    byId('matchOfWeekCard').innerHTML = `
      <article class="kpi-card">
        <h3>Jogo real da jornada</h3>
        <div class="kpi-row"><span>Jogo</span><strong>${bestApi.homeTeam} vs ${bestApi.awayTeam}</strong></div>
        <div class="kpi-row"><span>Data/Hora</span><strong>${dt}</strong></div>
        <p class="meta">${reading}</p>
        <button id="homeOpenMatchupFromCard" class="ghost-btn">Abrir Matchup completo</button>
      </article>
      <article class="kpi-card">
        <h3>Sinal principal</h3>
        <div class="kpi-row"><span>Confiança</span><strong>${conf != null ? `${conf}/100` : '—'}</strong></div>
        <div class="kpi-row"><span>Top edge</span><strong>${toNum(bestApi.topEdge) != null ? `${fmtNum(bestApi.topEdge * 100, 1)} pp` : '—'}</strong></div>
        <div class="kpi-row"><span>Forma (delta)</span><strong>${toNum(bestApi.formDelta) != null ? `${bestApi.formDelta >= 0 ? '+' : ''}${fmtNum(bestApi.formDelta, 2)}` : '—'}</strong></div>
      </article>
      <article class="kpi-card">
        <h3>Mercados sugeridos</h3>
        <p class="meta">${marketsText}</p>
      </article>
      <article class="kpi-card">
        <h3>Fonte</h3>
        <div class="kpi-row"><span>Provider</span><strong>${bestApi.source || '—'}</strong></div>
        <div class="kpi-row"><span>Liga</span><strong>${leagueLabel(league)}</strong></div>
      </article>
    `;
    byId('homeOpenMatchupFromCard')?.addEventListener('click', () => {
      openMatchupWithTeams(league, bestApi.homeTeam, bestApi.awayTeam);
    });
    return;
  }

  const best = computeBestMatchOfWeek(league);
  if (!best) {
    byId('matchOfWeekCard').innerHTML = '<article class="kpi-card"><h3>Jogo da Semana</h3><p class="meta">Sem dados suficientes.</p></article>';
    return;
  }

  const merged = buildConfrontoMerged(league, best.home, best.away).slice(0, 3);
  const markets = merged.length ? merged.map((m) => m.market).join(' · ') : 'Sem mercados convergentes fortes';
  const reading = best.conf.score >= 70
    ? 'Cenário com boa convergência entre forma, amostra e edge de mercado.'
    : 'Cenário equilibrado, com sinais úteis mas exigindo gestão de risco.';

  byId('matchOfWeekCard').innerHTML = `
    <article class="kpi-card">
      <h3>Matchup em foco</h3>
      <div class="kpi-row"><span>Jogo</span><strong>${best.home} vs ${best.away}</strong></div>
      <div class="kpi-row"><span>Liga</span><strong>${leagueLabel(league)}</strong></div>
      <p class="meta">${reading}</p>
      <button id="homeOpenMatchupFromCard" class="ghost-btn">Abrir Matchup completo</button>
    </article>
    <article class="kpi-card"><h3>Probabilidades-chave</h3><div class="kpi-row"><span>1 / X / 2</span><strong>${fmtPct(best.probs.p1)} / ${fmtPct(best.probs.px)} / ${fmtPct(best.probs.p2)}</strong></div><div class="kpi-row"><span>Over 2.5</span><strong>${fmtPct(best.probs.over25)}</strong></div><div class="kpi-row"><span>BTTS</span><strong>${fmtPct(best.probs.btts)}</strong></div></article>
    <article class="kpi-card"><h3>Confiança e estrutura</h3><div class="kpi-row"><span>Score</span><strong>${best.conf.score}</strong></div><div class="kpi-row"><span>Estabilidade</span><strong>${fmtPct(best.conf.stabilityFactor)}</strong></div><div class="kpi-row"><span>Amostra</span><strong>${best.conf.gamesHome}/${best.conf.gamesAway}</strong></div></article>
    <article class="kpi-card"><h3>Mercados sugeridos</h3><div class="kpi-row"><span>Top edge</span><strong>${best.edgeTop ? `${fmtNum(best.edgeTop * 100, 1)} pp` : '—'}</strong></div><p class="meta">${markets}</p></article>
  `;
  byId('homeOpenMatchupFromCard')?.addEventListener('click', () => setActiveTab('confronto'));
}

function openMatchupWithTeams(league, home, away) {
  setActiveTab('confronto');
  const lg = byId('cfLeague');
  const h = byId('cfHome');
  const a = byId('cfAway');
  if (!lg || !h || !a) return;

  const applyTeams = () => {
    if (Array.from(h.options).some((o) => o.value === home)) h.value = home;
    if (Array.from(a.options).some((o) => o.value === away)) a.value = away;
    renderConfronto();
  };

  if (lg.value !== league) {
    lg.value = league;
    lg.dispatchEvent(new Event('change'));
    setTimeout(applyTeams, 0);
    return;
  }
  applyTeams();
}

function computeBestMatchOfWeek(league) {
  const teams = (DATA.rankings[league] || []).map((x) => x.team).slice(0, 8);
  if (teams.length < 2) return null;

  let best = null;
  for (let i = 0; i < teams.length; i += 1) {
    for (let j = 0; j < teams.length; j += 1) {
      if (i === j) continue;
      const home = teams[i];
      const away = teams[j];
      const eg = computeExpectedGoals(league, home, away, 0.35);
      const conf = matchConfidence(league, home, away);
      if (!eg || !conf) continue;
      const probs = poissonProbs(eg.lambdaHome, eg.lambdaAway, 10);
      const shortlist = buildConfrontoMerged(league, home, away);
      const edgeTop = shortlist.length ? Math.max(...shortlist.map((x) => x.avg || 0)) : 0;
      const score = conf.score * 0.6 + (probs.over25 * 100) * 0.25 + (edgeTop * 100) * 0.15;
      if (!best || score > best.score) {
        best = { home, away, conf, probs, score, edgeTop };
      }
    }
  }
  return best;
}

function getSeries(league, team, venue, metric) {
  return DATA.seriesRows
    .filter((r) => r.league === league && r.team === team && r.venue === venue)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .map((r) => ({ date: r.date, value: Number(r[metric]) }));
}

function drawFormLineChart(series, metric) {
  const svg = byId('formLineChart');
  const t = chartTheme();
  if (!svg) return;

  if (!series.length) {
    svg.innerHTML = `<text x="16" y="28" fill="${t.muted}" font-size="14">Sem dados suficientes para o gráfico.</text>`;
    return;
  }

  const width = 960;
  const height = 340;
  const margin = { top: 16, right: 24, bottom: 36, left: 52 };
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
    grid += `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="${t.grid}" stroke-width="1" />`;
    labels += `<text x="${margin.left - 8}" y="${y + 4}" text-anchor="end" fill="${t.axis}" font-size="11">${label}</text>`;
  }

  const xStart = series[0].date ?? '';
  const xEnd = series[series.length - 1].date ?? '';

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="${t.bg}" />
    ${grid}
    <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    ${labels}
    <polyline fill="none" stroke="${t.main}" stroke-width="3" points="${points}" />
    ${series.map((s, i) => `<circle cx="${xAt(i)}" cy="${yAt(s.value)}" r="3.2" fill="${t.main}" />`).join('')}
    <text x="${margin.left}" y="${height - 8}" fill="${t.axis}" font-size="11">${xStart}</text>
    <text x="${width - margin.right}" y="${height - 8}" text-anchor="end" fill="${t.axis}" font-size="11">${xEnd}</text>
  `;
}

function renderForma() {
  const league = byId('formLeague').value;
  const team = byId('formTeam').value;
  const venue = byId('formVenue').value;
  const metric = byId('formMetric').value;

  const series = getSeries(league, team, venue, metric).filter((x) => Number.isFinite(x.value));
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
  byId('formLeague').innerHTML = leagueOptions(leagues);

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

function stdDev(values) {
  const valid = values.filter((x) => Number.isFinite(x));
  if (!valid.length) return null;
  const m = avg(valid);
  const variance = valid.reduce((acc, x) => acc + ((x - m) ** 2), 0) / valid.length;
  return Math.sqrt(variance);
}

function matchConfidence(league, home, away) {
  const h = getResumoRow(league, home, 'Casa');
  const a = getResumoRow(league, away, 'Fora');
  if (!h || !a) return null;

  const gamesHome = Number(h.jogos);
  const gamesAway = Number(a.jogos);
  const sampleFactor = clamp(Math.min(gamesHome, gamesAway) / 19, 0, 1);

  const hs = getSeries(league, home, 'H', 'roll5_goal_diff').map((x) => x.value).slice(-6);
  const as = getSeries(league, away, 'A', 'roll5_goal_diff').map((x) => x.value).slice(-6);
  const hStd = stdDev(hs);
  const aStd = stdDev(as);
  const combinedStd = avg([hStd, aStd]);
  const stabilityFactor = combinedStd == null ? 0.5 : clamp(1 - (combinedStd / 2.5), 0, 1);

  const score = Math.round((sampleFactor * 0.55 + stabilityFactor * 0.45) * 100);
  return { score, sampleFactor, stabilityFactor, gamesHome, gamesAway };
}

function evKellyRows(probs) {
  const items = [
    ['1 (Casa vence)', probs.p1, Number(byId('odds1').value)],
    ['X (Empate)', probs.px, Number(byId('oddsX').value)],
    ['2 (Fora vence)', probs.p2, Number(byId('odds2').value)],
    ['Over 2.5', probs.over25, Number(byId('oddsO25').value)],
    ['BTTS', probs.btts, Number(byId('oddsBTTS').value)]
  ];

  return items.map(([market, p, odds]) => {
    const o = Number.isFinite(odds) && odds > 1 ? odds : null;
    const ev = o ? (p * o - 1) : null;
    const kelly = o ? Math.max(0, (p * o - 1) / (o - 1)) : null;
    return { market, p, odds: o, ev, kelly };
  });
}

function renderEVKellyTable(probs) {
  const rows = evKellyRows(probs);
  byId('evKellyTable').querySelector('tbody').innerHTML = rows.map((r) => `<tr><td>${r.market}</td><td>${fmtPct(r.p)}</td><td>${r.odds ? fmtNum(r.odds, 2) : '—'}</td><td>${r.ev != null ? `${fmtNum(r.ev * 100, 1)}%` : '—'}</td><td>${r.kelly != null ? `${fmtNum(r.kelly * 100, 1)}%` : '—'}</td></tr>`).join('');
  applyExistingSort('evKellyTable');
}

function h2hRows(league, home, away) {
  const rows = DATA.seriesRows
    .filter((r) => r.league === league && r.team === home && r.opponent === away)
    .map((r) => {
      const gf = Number(r.gf);
      const ga = Number(r.ga);
      return {
        date: r.date,
        context: r.venue === 'H' ? 'Casa' : 'Fora',
        score: `${home} ${gf}-${ga} ${away}`,
        totalGoals: gf + ga,
        outcome: gf > ga ? 'W' : gf === ga ? 'D' : 'L'
      };
    })
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));
  return rows;
}

function renderH2H(league, home, away) {
  const rows = h2hRows(league, home, away);
  if (!rows.length) {
    byId('h2hSummary').innerHTML = '<article class="kpi-card"><h3>H2H</h3><p class="meta">Sem histórico direto disponível nesta liga.</p></article>';
    byId('h2hTable').querySelector('tbody').innerHTML = '<tr><td colspan="4">Sem histórico direto.</td></tr>';
    return;
  }

  const n = rows.length;
  const wins = rows.filter((r) => r.outcome === 'W').length;
  const draws = rows.filter((r) => r.outcome === 'D').length;
  const losses = rows.filter((r) => r.outcome === 'L').length;
  const avgGoals = avg(rows.map((r) => r.totalGoals));

  byId('h2hSummary').innerHTML = `
    <article class="kpi-card"><h3>Amostra</h3><div class="kpi-row"><span>Jogos</span><strong>${n}</strong></div></article>
    <article class="kpi-card"><h3>Registo (${home})</h3><div class="kpi-row"><span>V-E-D</span><strong>${wins}-${draws}-${losses}</strong></div></article>
    <article class="kpi-card"><h3>Média de golos</h3><div class="kpi-row"><span>Total por jogo</span><strong>${avgGoals != null ? fmtNum(avgGoals) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Último jogo</h3><div class="kpi-row"><span>Data</span><strong>${rows[0].date}</strong></div></article>
  `;

  byId('h2hTable').querySelector('tbody').innerHTML = rows.slice(0, 12).map((r) => `<tr><td>${r.date}</td><td>${r.context}</td><td>${r.score}</td><td>${r.totalGoals}</td></tr>`).join('');
  applyExistingSort('h2hTable');
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
  const t = chartTheme();
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
    const border = top.has(`${c.h}-${c.a}`) ? `2px solid ${t.main}` : '1px solid var(--line)';
    return `<div class="heat-cell" style="background: color-mix(in srgb, ${t.main} ${(alpha * 100).toFixed(1)}%, transparent); border:${border}"><div class="score">${c.h} - ${c.a}</div><div class="prob">${(c.p * 100).toFixed(1)}%</div></div>`;
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
    byId('prejogoConfidenceCards').innerHTML = '<article class="kpi-card"><h3>Confiança</h3><p class="meta">Sem dados suficientes.</p></article>';
    byId('evKellyTable').querySelector('tbody').innerHTML = '<tr><td colspan="5">Insere odds para calcular EV/Kelly.</td></tr>';
    byId('prejogoShortlistTable').querySelector('tbody').innerHTML = '<tr><td colspan="5">Sem shortlist para este jogo.</td></tr>';
    byId('scoreHeatmap').innerHTML = '<p class="meta">Sem dados de heatmap.</p>';
    byId('h2hSummary').innerHTML = '<article class="kpi-card"><h3>H2H</h3><p class="meta">Sem dados.</p></article>';
    byId('h2hTable').querySelector('tbody').innerHTML = '<tr><td colspan="4">Sem histórico direto.</td></tr>';
    return;
  }

  const probs = poissonProbs(eg.lambdaHome, eg.lambdaAway, 10);

  byId('prejogoProbCards').innerHTML = `
    <article class="kpi-card"><h3>Expected Goals</h3><div class="kpi-row"><span>${home}</span><strong>${fmtNum(eg.lambdaHome)}</strong></div><div class="kpi-row"><span>${away}</span><strong>${fmtNum(eg.lambdaAway)}</strong></div></article>
    <article class="kpi-card"><h3>1X2</h3><div class="kpi-row"><span>1</span><strong>${fmtPct(probs.p1)}</strong></div><div class="kpi-row"><span>X</span><strong>${fmtPct(probs.px)}</strong></div><div class="kpi-row"><span>2</span><strong>${fmtPct(probs.p2)}</strong></div></article>
    <article class="kpi-card"><h3>Totais</h3><div class="kpi-row"><span>Over 2.5</span><strong>${fmtPct(probs.over25)}</strong></div><div class="kpi-row"><span>BTTS</span><strong>${fmtPct(probs.btts)}</strong></div></article>
    <article class="kpi-card"><h3>Configuração</h3><div class="kpi-row"><span>Peso forma</span><strong>${fmtPct(weight)}</strong></div><div class="kpi-row"><span>Liga</span><strong>${leagueLabel(league)}</strong></div></article>
  `;

  const conf = matchConfidence(league, home, away);
  byId('prejogoConfidenceCards').innerHTML = conf
    ? `
      <article class="kpi-card"><h3>Score de Confiança</h3><div class="kpi-row"><span>0-100</span><strong>${conf.score}</strong></div></article>
      <article class="kpi-card"><h3>Fator Amostra</h3><div class="kpi-row"><span>Casa/Fora</span><strong>${conf.gamesHome}/${conf.gamesAway}</strong></div></article>
      <article class="kpi-card"><h3>Qualidade da Amostra</h3><div class="kpi-row"><span>normalizado</span><strong>${fmtPct(conf.sampleFactor)}</strong></div></article>
      <article class="kpi-card"><h3>Estabilidade</h3><div class="kpi-row"><span>forma recente</span><strong>${fmtPct(conf.stabilityFactor)}</strong></div></article>
    `
    : '<article class="kpi-card"><h3>Confiança</h3><p class="meta">Sem dados suficientes.</p></article>';

  PREJOGO_STATE = { league, home, away, probs, shortlist: [] };
  renderEVKellyTable(probs);

  renderScoreHeatmap(probs.pmfHome, probs.pmfAway);

  const shortlist = buildConfrontoMerged(league, home, away)
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 15);
  PREJOGO_STATE.shortlist = shortlist;

  byId('prejogoShortlistTable').querySelector('tbody').innerHTML = shortlist.map((r) => `<tr><td>${r.market}</td><td>${fmtNum(r.homeEdge * 100, 1)} pp</td><td>${fmtNum(r.awayEdge * 100, 1)} pp</td><td>${fmtNum(r.avg * 100, 1)} pp</td><td>${r.hitAvg != null ? fmtPct(r.hitAvg) : '—'}</td></tr>`).join('') || '<tr><td colspan="5">Sem shortlist para este jogo.</td></tr>';
  applyExistingSort('prejogoShortlistTable');

}

function populatePrejogo(leagues) {
  byId('pjLeague').innerHTML = leagueOptions(leagues);

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
  ['odds1', 'oddsX', 'odds2', 'oddsO25', 'oddsBTTS'].forEach((id) => byId(id).addEventListener('input', () => {
    if (PREJOGO_STATE?.probs) renderEVKellyTable(PREJOGO_STATE.probs);
  }));
  refreshTeams();
}

function resetScannerFilters() {
  if (byId('scanLeague')) byId('scanLeague').value = 'Todas';
  if (byId('scanScope')) byId('scanScope').value = 'Total';
  if (byId('scanGroup')) byId('scanGroup').value = 'resultados';
  if (byId('scanMinGames')) byId('scanMinGames').value = 8;
  renderScanner();
}

function resetPrejogoFilters() {
  const pjLeague = byId('pjLeague');
  if (pjLeague && pjLeague.options.length) {
    pjLeague.selectedIndex = 0;
    pjLeague.dispatchEvent(new Event('change'));
  }
  if (byId('pjRecentWeight')) byId('pjRecentWeight').value = 35;
  ['odds1', 'oddsX', 'odds2', 'oddsO25', 'oddsBTTS'].forEach((id) => {
    const el = byId(id);
    if (el) el.value = '';
  });
  renderPrejogo();
}

function renderChangelog() {
  const el = byId('changelogList');
  if (!el) return;
  const entries = DATA.changelog || [];
  el.innerHTML = entries.length
    ? entries.slice(0, 8).map((c) => `<article class="item"><p class="title">${c.date || '—'} · ${c.title || 'Atualização semanal'}</p><p class="meta">${c.summary || 'Refresh automático de dados e métricas.'}</p></article>`).join('')
    : '<p class="meta">Sem entradas de changelog ainda.</p>';
}

function drawCapitalCurve(curve) {
  const svg = byId('capitalCurveChart');
  const t = chartTheme();
  if (!svg) return;
  if (!curve || !curve.length) {
    svg.innerHTML = `<text x="16" y="28" fill="${t.muted}" font-size="14">Sem bets temporais para curva de capital.</text>`;
    return;
  }

  const width = 980;
  const height = 320;
  const margin = { top: 16, right: 26, bottom: 36, left: 52 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;

  const caps = curve.map((x) => Number(x.capital)).filter((v) => Number.isFinite(v));
  const yMin = Math.min(...caps) - 1;
  const yMax = Math.max(...caps) + 1;
  const xAt = (i) => margin.left + (i / Math.max(curve.length - 1, 1)) * chartW;
  const yAt = (v) => margin.top + (1 - ((v - yMin) / Math.max(yMax - yMin, 1e-9))) * chartH;

  const pts = curve.map((x, i) => `${xAt(i)},${yAt(Number(x.capital))}`).join(' ');
  const ddPts = curve.map((x, i) => `${xAt(i)},${yAt(Number(x.capital) - Number(x.drawdown || 0))}`).join(' ');
  const start = curve[0]?.date || '';
  const end = curve[curve.length - 1]?.date || '';

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="${t.bg}" />
    <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    <polyline fill="none" stroke="${t.main}" stroke-width="2.8" points="${pts}" />
    <polyline fill="none" stroke="${t.alt}" stroke-dasharray="5 4" stroke-width="1.8" points="${ddPts}" />
    <text x="${margin.left}" y="14" fill="${t.main}" font-size="12">Capital</text>
    <text x="${margin.left + 66}" y="14" fill="${t.alt}" font-size="12">Drawdown path</text>
    <text x="${margin.left}" y="${height - 8}" fill="${t.axis}" font-size="11">${start}</text>
    <text x="${width - margin.right}" y="${height - 8}" text-anchor="end" fill="${t.axis}" font-size="11">${end}</text>
  `;
}

function drawStakeCurve(staking) {
  const svg = byId('stakeCurveChart');
  const t = chartTheme();
  if (!svg) return;
  const curve = staking?.curve || [];
  if (!curve.length) {
    svg.innerHTML = `<text x="16" y="28" fill="${t.muted}" font-size="14">Sem dados de stake para comparar estratégias.</text>`;
    return;
  }

  const width = 980;
  const height = 320;
  const margin = { top: 18, right: 24, bottom: 36, left: 52 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;
  const groups = {};
  curve.forEach((r) => {
    if (!groups[r.strategy]) groups[r.strategy] = [];
    groups[r.strategy].push(r);
  });
  const strategies = Object.keys(groups);
  const allCaps = curve.map((r) => Number(r.capital)).filter((x) => Number.isFinite(x));
  const yMin = Math.min(...allCaps) - 1;
  const yMax = Math.max(...allCaps) + 1;
  const maxLen = Math.max(...strategies.map((s) => groups[s].length));
  const xAt = (i) => margin.left + (i / Math.max(maxLen - 1, 1)) * chartW;
  const yAt = (v) => margin.top + (1 - ((v - yMin) / Math.max(yMax - yMin, 1e-9))) * chartH;
  const palette = {
    flat_1u: t.main,
    kelly_q: '#8f9dff',
    dynamic_c: t.alt
  };

  const lines = strategies.map((s) => {
    const pts = groups[s].map((r, i) => `${xAt(i)},${yAt(Number(r.capital))}`).join(' ');
    const color = palette[s] || '#0f172a';
    return `<polyline fill="none" stroke="${color}" stroke-width="2.4" points="${pts}" />`;
  }).join('');

  const startDate = (curve[0]?.date) || '';
  const endDate = (curve[curve.length - 1]?.date) || '';
  const legend = strategies.map((s, i) => {
    const color = palette[s] || '#0f172a';
    const label = groups[s][0]?.strategy_label || s;
    return `<text x="${margin.left + i * 220}" y="14" fill="${color}" font-size="12">${label}</text>`;
  }).join('');

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="${t.bg}" />
    <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    ${lines}
    ${legend}
    <text x="${margin.left}" y="${height - 8}" fill="${t.axis}" font-size="11">${startDate}</text>
    <text x="${width - margin.right}" y="${height - 8}" text-anchor="end" fill="${t.axis}" font-size="11">${endDate}</text>
  `;
}

function renderPerformanceGuide() {
  const temporal = DATA.temporalBacktest || {};
  const sel = temporal.selectionStats || {};
  const initial = toNum(temporal.initial_bankroll) ?? 100;
  const final = toNum(temporal.final_bankroll);
  const profit = final != null ? final - initial : null;
  const hit = toNum(temporal.hit_rate);
  const bets = toNum(temporal.total_bets);

  byId('performanceGuideCards').innerHTML = `
    <article class="kpi-card"><h3>1) O que é isto?</h3><p class="meta">É uma simulação histórica com regras fixas de seleção de mercados.</p></article>
    <article class="kpi-card"><h3>2) Regra de lucro</h3><p class="meta">Win: + (odds - 1) por unidade. Loss: -1 unidade.</p></article>
    <article class="kpi-card"><h3>3) Hit rate</h3><p class="meta">É a taxa de acerto das apostas simuladas (não de todos os jogos).</p></article>
    <article class="kpi-card"><h3>4) Limitação</h3><p class="meta">Não é garantia futura. Serve para comparar estratégias e risco.</p></article>
  `;

  const summary = [
    `Banca inicial: ${fmtNum(initial, 2)}`,
    final != null ? `Banca final simulada: ${fmtNum(final, 2)}` : 'Banca final simulada: —',
    profit != null ? `Lucro simulado: ${profit >= 0 ? '+' : ''}${fmtNum(profit, 2)}` : 'Lucro simulado: —',
    hit != null ? `Hit rate: ${fmtPct(hit)}` : 'Hit rate: —',
    bets != null ? `Apostas: ${fmtNum(bets, 0)}` : 'Apostas: —'
  ];
  byId('performanceGuideNote').textContent = summary.join(' · ');

  const total = toNum(sel.total_home_matches) ?? 0;
  const stage1 = toNum(sel.with_team_data) ?? 0;
  const stage2 = toNum(sel.with_market_overlap) ?? 0;
  const stage3 = toNum(sel.with_positive_edge_odds) ?? 0;
  const selected = toNum(sel.selected_bets) ?? 0;
  const selRate = toNum(sel.selection_rate);

  byId('performanceSelectionFlow').innerHTML = `
    <article class="item"><p class="title">Critério de seleção (ordem real)</p><p class="meta">1) jogo em casa na série temporal · 2) existe dados de mercado para equipa casa (Casa) e adversário (Fora) · 3) existe mercado comum entre as duas equipas · 4) apenas mercados com edge médio > 0 e odds médias > 1.01 · 5) escolhe-se 1 pick por jogo: o maior edge médio.</p></article>
    <article class="item"><p class="title">Funil desta atualização</p><p class="meta">Jogos casa: <strong>${fmtNum(total, 0)}</strong> → com dados casa/fora: <strong>${fmtNum(stage1, 0)}</strong> → com mercado comum: <strong>${fmtNum(stage2, 0)}</strong> → com edge+odds válidos: <strong>${fmtNum(stage3, 0)}</strong> → apostas selecionadas: <strong>${fmtNum(selected, 0)}</strong>${selRate != null ? ` (${fmtPct(selRate)})` : ''}.</p></article>
  `;
}

function renderStrategyProfiles() {
  const payload = DATA.phase24Profiles || { profiles: [] };
  const selected = byId('strategyProfileSelect')?.value || 'balanceado';
  const profile = (payload.profiles || []).find((p) => p.id === selected) || (payload.profiles || [])[0];

  if (!profile) {
    byId('strategyProfileCards').innerHTML = '<article class="kpi-card"><h3>Perfis</h3><p class="meta">Sem dados de perfil disponíveis.</p></article>';
    byId('strategyProfileTable').querySelector('tbody').innerHTML = '<tr><td colspan="8">Sem estratégias avaliadas.</td></tr>';
    return;
  }

  const rec = profile.recommendation || null;
  byId('strategyProfileCards').innerHTML = `
    <article class="kpi-card"><h3>Perfil selecionado</h3><div class="kpi-row"><span>Modo</span><strong>${profile.label}</strong></div></article>
    <article class="kpi-card"><h3>Estratégia recomendada</h3><div class="kpi-row"><span>Top score</span><strong>${rec ? rec.strategy_label : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Score da recomendação</h3><div class="kpi-row"><span>0-100</span><strong>${rec ? fmtNum(rec.score, 1) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Risco da recomendação</h3><div class="kpi-row"><span>Drawdown máx</span><strong>${rec && toNum(rec.max_drawdown_pct) != null ? `${fmtNum(rec.max_drawdown_pct * 100, 2)}%` : '—'}</strong></div></article>
  `;

  byId('strategyProfileTable').querySelector('tbody').innerHTML = (profile.ranking || [])
    .map((r) => `<tr>
      <td>${r.strategy_label}</td>
      <td>${fmtNum(r.score, 1)}</td>
      <td>${toNum(r.roi_on_staked) != null ? `${fmtNum(r.roi_on_staked * 100, 2)}%` : '—'}</td>
      <td>${toNum(r.profit_pct) != null ? `${fmtNum(r.profit_pct * 100, 2)}%` : '—'}</td>
      <td>${toNum(r.max_drawdown_pct) != null ? `${fmtNum(r.max_drawdown_pct * 100, 2)}%` : '—'}</td>
      <td>${toNum(r.weekly_roi_std) != null ? `${fmtNum(r.weekly_roi_std * 100, 2)}%` : '—'}</td>
      <td>${toNum(r.hit_rate) != null ? fmtPct(r.hit_rate) : '—'}</td>
      <td>${r.total_bets ?? '—'}</td>
    </tr>`).join('') || '<tr><td colspan="8">Sem estratégias avaliadas.</td></tr>';
  applyExistingSort('strategyProfileTable');
}

function renderPerformance() {
  renderPerformanceGuide();

  const rows = DATA.backtestRows || [];
  const dq = DATA.dataQuality || { checks: [], summary: { checks_total: 0, checks_warn: 0 } };
  const validRoi = rows.map((r) => toNum(r.roi_mean)).filter((x) => x != null);
  const validEv = rows.map((r) => toNum(r.ev_mean)).filter((x) => x != null);
  const totalBets = rows.reduce((acc, r) => acc + Number(r.bets || 0), 0);
  const best = rows
    .filter((r) => toNum(r.roi_mean) != null)
    .sort((a, b) => Number(b.roi_mean) - Number(a.roi_mean))[0];

  byId('perfCards').innerHTML = `
    <article class="kpi-card"><h3>Bets avaliadas</h3><div class="kpi-row"><span>Total</span><strong>${totalBets}</strong></div></article>
    <article class="kpi-card"><h3>ROI médio</h3><div class="kpi-row"><span>Todos os grupos</span><strong>${validRoi.length ? `${fmtNum(avg(validRoi) * 100, 2)}%` : '—'}</strong></div></article>
    <article class="kpi-card"><h3>EV médio</h3><div class="kpi-row"><span>Todos os grupos</span><strong>${validEv.length ? `${fmtNum(avg(validEv) * 100, 2)}%` : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Melhor segmento</h3><div class="kpi-row"><span>Liga/Grupo</span><strong>${best ? `${leagueLabel(best.league)} · ${groupLabel(best.group)}` : '—'}</strong></div></article>
  `;

  byId('perfMarketTable').querySelector('tbody').innerHTML = rows
    .sort((a, b) => Number(b.roi_mean ?? -999) - Number(a.roi_mean ?? -999))
    .map((r) => `<tr>
      <td>${leagueLabel(r.league)}</td>
      <td>${groupLabel(r.group)}</td>
      <td>${r.markets}</td>
      <td>${r.bets}</td>
      <td>${toNum(r.hit_rate) != null ? fmtPct(r.hit_rate) : '—'}</td>
      <td>${toNum(r.roi_mean) != null ? `${fmtNum(r.roi_mean * 100, 2)}%` : '—'}</td>
      <td>${toNum(r.ev_mean) != null ? `${fmtNum(r.ev_mean * 100, 2)}%` : '—'}</td>
      <td>${toNum(r.drawdown_proxy) != null ? `${fmtNum(r.drawdown_proxy * 100, 1)}%` : '—'}</td>
      <td>${toNum(r.brier_proxy) != null ? fmtNum(r.brier_proxy, 3) : '—'}</td>
    </tr>`).join('') || '<tr><td colspan="9">Sem dados de backtesting.</td></tr>';
  applyExistingSort('perfMarketTable');

  byId('qualityCards').innerHTML = `
    <article class="kpi-card"><h3>Checks executados</h3><div class="kpi-row"><span>Total</span><strong>${dq.summary?.checks_total ?? 0}</strong></div></article>
    <article class="kpi-card"><h3>Alertas</h3><div class="kpi-row"><span>Warn</span><strong>${dq.summary?.checks_warn ?? 0}</strong></div></article>
    <article class="kpi-card"><h3>Estado</h3><div class="kpi-row"><span>Qualidade global</span><strong>${(dq.summary?.checks_warn ?? 0) === 0 ? 'OK' : 'Atenção'}</strong></div></article>
    <article class="kpi-card"><h3>Atualização</h3><div class="kpi-row"><span>Dados</span><strong>${(DATA.meta?.generatedAt || '').slice(0, 10) || '—'}</strong></div></article>
  `;

  byId('qualityChecksTable').querySelector('tbody').innerHTML = (dq.checks || [])
    .map((c) => `<tr><td>${c.name}</td><td><span class="badge ${c.status === 'ok' ? 'good' : 'warn'}">${c.status === 'ok' ? 'OK' : 'WARN'}</span></td><td>${c.detail}</td></tr>`)
    .join('') || '<tr><td colspan="3">Sem checks de qualidade.</td></tr>';
  applyExistingSort('qualityChecksTable');

  const temporal = DATA.temporalBacktest || {};
  drawCapitalCurve(temporal.curve || []);
  byId('weeklyBacktestTable').querySelector('tbody').innerHTML = (temporal.weekly || [])
    .map((w) => `<tr>
      <td>${w.week_key}</td>
      <td>${w.bets}</td>
      <td>${w.wins}</td>
      <td>${toNum(w.hit_rate) != null ? fmtPct(w.hit_rate) : '—'}</td>
      <td>${toNum(w.roi) != null ? `${fmtNum(w.roi * 100, 2)}%` : '—'}</td>
      <td>${toNum(w.profit) != null ? fmtNum(w.profit, 2) : '—'}</td>
      <td>${toNum(w.capital_end) != null ? fmtNum(w.capital_end, 2) : '—'}</td>
      <td>${toNum(w.max_drawdown_week) != null ? fmtNum(w.max_drawdown_week, 2) : '—'}</td>
    </tr>`).join('') || '<tr><td colspan="8">Sem dados temporais.</td></tr>';
  applyExistingSort('weeklyBacktestTable');

  const staking = DATA.phase23Staking || { strategies: [], curve: [] };
  const bestKey = staking.best_strategy;
  const bestStrategy = (staking.strategies || []).find((x) => x.strategy === bestKey) || null;
  byId('stakeCards').innerHTML = `
    <article class="kpi-card"><h3>Estratégias testadas</h3><div class="kpi-row"><span>Total</span><strong>${(staking.strategies || []).length}</strong></div></article>
    <article class="kpi-card"><h3>Melhor estratégia</h3><div class="kpi-row"><span>ROI ajustado</span><strong>${bestStrategy ? bestStrategy.strategy_label : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Capital final (melhor)</h3><div class="kpi-row"><span>simulação</span><strong>${bestStrategy ? fmtNum(bestStrategy.final_capital, 2) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Drawdown (melhor)</h3><div class="kpi-row"><span>máx %</span><strong>${bestStrategy && toNum(bestStrategy.max_drawdown_pct) != null ? `${fmtNum(bestStrategy.max_drawdown_pct * 100, 2)}%` : '—'}</strong></div></article>
  `;
  drawStakeCurve(staking);

  byId('stakeTable').querySelector('tbody').innerHTML = (staking.strategies || [])
    .sort((a, b) => Number(b.roi_on_staked ?? -999) - Number(a.roi_on_staked ?? -999))
    .map((s) => `<tr>
      <td>${s.strategy_label}</td>
      <td>${toNum(s.final_capital) != null ? fmtNum(s.final_capital, 2) : '—'}</td>
      <td>${toNum(s.total_profit) != null ? fmtNum(s.total_profit, 2) : '—'}</td>
      <td>${toNum(s.roi_on_staked) != null ? `${fmtNum(s.roi_on_staked * 100, 2)}%` : '—'}</td>
      <td>${toNum(s.max_drawdown_pct) != null ? `${fmtNum(s.max_drawdown_pct * 100, 2)}%` : '—'}</td>
      <td>${toNum(s.hit_rate) != null ? fmtPct(s.hit_rate) : '—'}</td>
      <td>${s.total_bets ?? '—'}</td>
    </tr>`).join('') || '<tr><td colspan="7">Sem dados de estratégias.</td></tr>';
  applyExistingSort('stakeTable');

  renderStrategyProfiles();
}

function modelConfidenceBadge(score) {
  const s = Number(score || 0);
  if (s >= 75) return '<span class="badge good">Alta</span>';
  if (s >= 55) return '<span class="badge">Média</span>';
  return '<span class="badge warn">Baixa</span>';
}

function renderModel() {
  const league = byId('modelLeague')?.value || 'Todas';
  const scope = byId('modelScope')?.value || 'Todos';
  const group = byId('modelGroup')?.value || 'todos';
  const minConf = Number(byId('modelMinConf')?.value || 0);

  const rows = (DATA.phase2ModelRows || [])
    .filter((r) => (league === 'Todas' || r.league === league)
      && (scope === 'Todos' || r.scope === scope)
      && marketInGroup(r.market, group)
      && Number(r.confidence_score || 0) >= minConf)
    .sort((a, b) => {
      const ca = Number(a.confidence_score || 0);
      const cb = Number(b.confidence_score || 0);
      if (cb !== ca) return cb - ca;
      return Number(b.ev_model || -999) - Number(a.ev_model || -999);
    });

  const edgeVals = rows.map((r) => toNum(r.edge_vs_odds)).filter((x) => x != null);
  const evVals = rows.map((r) => toNum(r.ev_model)).filter((x) => x != null);
  const best = rows
    .filter((r) => toNum(r.ev_model) != null)
    .sort((a, b) => Number(b.ev_model) - Number(a.ev_model))[0];

  byId('modelCards').innerHTML = `
    <article class="kpi-card"><h3>Mercados filtrados</h3><div class="kpi-row"><span>Total</span><strong>${rows.length}</strong></div></article>
    <article class="kpi-card"><h3>Edge médio vs odds</h3><div class="kpi-row"><span>Modelo - implícita</span><strong>${edgeVals.length ? `${fmtNum(avg(edgeVals) * 100, 2)} pp` : '—'}</strong></div></article>
    <article class="kpi-card"><h3>EV médio modelo</h3><div class="kpi-row"><span>Com odds médias</span><strong>${evVals.length ? `${fmtNum(avg(evVals) * 100, 2)}%` : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Top oportunidade</h3><div class="kpi-row"><span>EV máximo</span><strong>${best ? `${best.team} · ${best.market}` : '—'}</strong></div></article>
  `;

  byId('modelTable').querySelector('tbody').innerHTML = rows.slice(0, 300).map((r) => {
    const ci = (toNum(r.ci_lo) != null && toNum(r.ci_hi) != null) ? `${fmtPct(r.ci_lo)}–${fmtPct(r.ci_hi)}` : '—';
    const sqCls = String(r.sample_quality || '').toLowerCase() === 'alta'
      ? 'good'
      : String(r.sample_quality || '').toLowerCase() === 'média' || String(r.sample_quality || '').toLowerCase() === 'media'
        ? ''
        : 'warn';
    return `<tr>
      <td>${leagueLabel(r.league)}</td>
      <td>${r.team}</td>
      <td>${r.scope}</td>
      <td>${r.market}</td>
      <td>${r.sample_games} <span class="badge ${sqCls}">${r.sample_quality || '—'}</span></td>
      <td>${toNum(r.p_empirical) != null ? fmtPct(r.p_empirical) : '—'}</td>
      <td>${toNum(r.p_model) != null ? fmtPct(r.p_model) : '—'}</td>
      <td>${ci}</td>
      <td>${toNum(r.fair_odds) != null ? fmtNum(r.fair_odds, 2) : '—'}</td>
      <td>${toNum(r.odds_avg) != null ? fmtNum(r.odds_avg, 2) : '—'}</td>
      <td>${toNum(r.edge_vs_odds) != null ? `${fmtNum(r.edge_vs_odds * 100, 2)} pp` : '—'}</td>
      <td>${toNum(r.ev_model) != null ? `${fmtNum(r.ev_model * 100, 2)}%` : '—'}</td>
      <td>${r.confidence_score ?? 0} ${modelConfidenceBadge(r.confidence_score)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="13">Sem dados para os filtros escolhidos.</td></tr>';
  applyExistingSort('modelTable');

  const cal = DATA.phase2Calibration || { summary: {}, bins: [], by_group: [] };
  const s = cal.summary || {};
  byId('calibrationCards').innerHTML = `
    <article class="kpi-card"><h3>Amostras ponderadas</h3><div class="kpi-row"><span>Total</span><strong>${toNum(s.weighted_samples) != null ? fmtNum(s.weighted_samples, 0) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Brier Score</h3><div class="kpi-row"><span>Quanto menor melhor</span><strong>${toNum(s.brier) != null ? fmtNum(s.brier, 4) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>LogLoss</h3><div class="kpi-row"><span>Quanto menor melhor</span><strong>${toNum(s.logloss) != null ? fmtNum(s.logloss, 4) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>ECE</h3><div class="kpi-row"><span>Erro de calibração</span><strong>${toNum(s.ece) != null ? fmtNum(s.ece, 4) : '—'}</strong></div></article>
  `;

  drawCalibrationChart(cal.bins || []);

  byId('calibrationBinsTable').querySelector('tbody').innerHTML = (cal.bins || []).map((b) => `<tr>
    <td>${b.bin}</td>
    <td>${toNum(b.p_pred) != null ? fmtPct(b.p_pred) : '—'}</td>
    <td>${toNum(b.p_obs) != null ? fmtPct(b.p_obs) : '—'}</td>
    <td>${toNum(b.gap_abs) != null ? fmtNum(b.gap_abs * 100, 2) + ' pp' : '—'}</td>
    <td>${b.rows ?? '—'}</td>
    <td>${toNum(b.samples) != null ? fmtNum(b.samples, 0) : '—'}</td>
  </tr>`).join('') || '<tr><td colspan="6">Sem bins de calibração.</td></tr>';
  applyExistingSort('calibrationBinsTable');

  byId('calibrationGroupTable').querySelector('tbody').innerHTML = (cal.by_group || [])
    .sort((a, b) => Number(a.brier ?? 999) - Number(b.brier ?? 999))
    .map((g) => `<tr>
      <td>${groupLabel(g.group)}</td>
      <td>${g.rows ?? '—'}</td>
      <td>${toNum(g.samples) != null ? fmtNum(g.samples, 0) : '—'}</td>
      <td>${toNum(g.brier) != null ? fmtNum(g.brier, 4) : '—'}</td>
      <td>${toNum(g.logloss) != null ? fmtNum(g.logloss, 4) : '—'}</td>
      <td>${toNum(g.avg_confidence) != null ? fmtNum(g.avg_confidence, 1) : '—'}</td>
    </tr>`).join('') || '<tr><td colspan="6">Sem grupos para calibração.</td></tr>';
  applyExistingSort('calibrationGroupTable');
}

function drawCalibrationChart(bins) {
  const svg = byId('calibrationChart');
  const t = chartTheme();
  if (!svg) return;
  const valid = (bins || []).filter((b) => toNum(b.p_pred) != null && toNum(b.p_obs) != null);
  if (!valid.length) {
    svg.innerHTML = `<text x="16" y="28" fill="${t.muted}" font-size="14">Sem dados de calibração.</text>`;
    return;
  }

  const width = 900;
  const height = 320;
  const margin = { top: 16, right: 22, bottom: 38, left: 52 };
  const chartW = width - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;
  const xAt = (v) => margin.left + clamp(v, 0, 1) * chartW;
  const yAt = (v) => margin.top + (1 - clamp(v, 0, 1)) * chartH;

  const pts = valid.map((b) => `${xAt(Number(b.p_pred))},${yAt(Number(b.p_obs))}`).join(' ');
  const circles = valid.map((b) => `<circle cx="${xAt(Number(b.p_pred))}" cy="${yAt(Number(b.p_obs))}" r="4" fill="${t.main}" />`).join('');
  const labels = valid.map((b) => `<text x="${xAt(Number(b.p_pred)) + 6}" y="${yAt(Number(b.p_obs)) - 6}" fill="${t.axis}" font-size="10">${b.bin}</text>`).join('');

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="${t.bg}" />
    <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="${t.grid}" />
    <line x1="${xAt(0)}" y1="${yAt(0)}" x2="${xAt(1)}" y2="${yAt(1)}" stroke="${t.axis}" stroke-dasharray="5 4" />
    <polyline fill="none" stroke="${t.main}" stroke-width="2.6" points="${pts}" />
    ${circles}
    ${labels}
    <text x="${margin.left}" y="14" fill="${t.main}" font-size="12">Curva observada</text>
    <text x="${margin.left + 126}" y="14" fill="${t.axis}" font-size="12">Diagonal ideal</text>
    <text x="${margin.left}" y="${height - 8}" fill="${t.axis}" font-size="11">P prevista</text>
    <text x="${margin.left - 40}" y="${margin.top + 8}" fill="${t.axis}" font-size="11">P obs.</text>
  `;
}

function populateModel(leagues) {
  byId('modelLeague').innerHTML = `<option value="Todas">Todas</option>${leagueOptions(leagues)}`;
  ['modelLeague', 'modelScope', 'modelGroup', 'modelMinConf'].forEach((id) => byId(id)?.addEventListener('change', renderModel));
  renderModel();
}

function exportPrejogoPdf() {
  if (!PREJOGO_STATE?.league || !PREJOGO_STATE?.home || !PREJOGO_STATE?.away || !PREJOGO_STATE?.probs) return;
  const now = new Date().toLocaleString('pt-PT', { timeZone: 'Europe/Lisbon' });
  const rows = PREJOGO_STATE.shortlist.slice(0, 12).map((r) => `<tr><td>${r.market}</td><td>${fmtNum(r.avg * 100, 1)} pp</td><td>${r.hitAvg != null ? fmtPct(r.hitAvg) : '—'}</td></tr>`).join('');
  const html = `
    <!doctype html><html lang="pt"><head><meta charset="UTF-8"><title>Relatório Pré-jogo</title>
    <style>
      body{font-family:Arial,sans-serif;padding:24px;color:#111} h1,h2{margin:0 0 10px} .meta{color:#555;margin-bottom:16px}
      .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}
      .card{border:1px solid #ddd;border-radius:8px;padding:10px}
      table{width:100%;border-collapse:collapse} th,td{border-bottom:1px solid #eee;padding:8px;text-align:left}
    </style></head><body>
      <h1>Relatório Pré-jogo</h1>
      <p class="meta">${PREJOGO_STATE.home} vs ${PREJOGO_STATE.away} · ${leagueLabel(PREJOGO_STATE.league)} · gerado em ${now}</p>
      <div class="grid">
        <div class="card"><h2>1X2</h2><p>1: ${fmtPct(PREJOGO_STATE.probs.p1)} · X: ${fmtPct(PREJOGO_STATE.probs.px)} · 2: ${fmtPct(PREJOGO_STATE.probs.p2)}</p></div>
        <div class="card"><h2>Totais</h2><p>Over 2.5: ${fmtPct(PREJOGO_STATE.probs.over25)} · BTTS: ${fmtPct(PREJOGO_STATE.probs.btts)}</p></div>
      </div>
      <h2>Shortlist de mercados</h2>
      <table><thead><tr><th>Mercado</th><th>Edge médio</th><th>Hit médio</th></tr></thead><tbody>${rows || '<tr><td colspan="3">Sem shortlist.</td></tr>'}</tbody></table>
      <script>window.onload=()=>window.print();</script>
    </body></html>
  `;
  const w = window.open('', '_blank');
  if (!w) return;
  w.document.open();
  w.document.write(html);
  w.document.close();
}

async function main() {
  const res = await fetch('./data/site-data.json?v=20260413b', { cache: 'no-store' });
  DATA = await res.json();
  loadWatchlist();

  renderSummaryChips(DATA);
  renderChangelog();

  const leagues = DATA.overview.map((x) => x.league);

  byId('leagueSelect').innerHTML = leagueOptions(leagues);
  byId('leagueSelect').addEventListener('change', (e) => renderOverview(e.target.value));
  byId('dashboardTeamSelect')?.addEventListener('change', () => renderOverview(byId('leagueSelect').value));
  renderOverview(leagues[0]);

  populateScannerFilters(leagues);
  ['scanLeague', 'scanScope', 'scanGroup', 'scanMinGames'].forEach((id) => byId(id).addEventListener('change', renderScanner));
  renderScanner();

  populateConfronto(leagues);
  if (byId('panel-performance')) renderPerformance();
  populateModel(leagues);
  populatePrejogo(leagues);

  document.querySelectorAll('.tab').forEach((btn) => btn.addEventListener('click', () => setActiveTab(btn.dataset.tab)));

  ['scannerTable', 'confrontoMarketTable', 'compareDeltaTable', 'perfMarketTable', 'qualityChecksTable', 'weeklyBacktestTable', 'stakeTable', 'strategyProfileTable', 'modelTable', 'calibrationBinsTable', 'calibrationGroupTable', 'prejogoShortlistTable', 'evKellyTable', 'h2hTable'].forEach(enableTableSorting);
  byId('strategyProfileSelect')?.addEventListener('change', renderStrategyProfiles);
  byId('exportPrejogoPdfBtn')?.addEventListener('click', exportPrejogoPdf);
  byId('scannerResetBtn')?.addEventListener('click', resetScannerFilters);
  byId('prejogoResetBtn')?.addEventListener('click', resetPrejogoFilters);
  byId('heroOpenScanner')?.addEventListener('click', () => setActiveTab('scanner'));
  byId('heroOpenMatchup')?.addEventListener('click', () => setActiveTab('confronto'));
  byId('homeOpenScannerTop')?.addEventListener('click', () => setActiveTab('scanner'));
  byId('homeOpenScannerSummary')?.addEventListener('click', () => setActiveTab('scanner'));
  byId('homeOpenWatchlist')?.addEventListener('click', () => setActiveTab('scanner'));

  byId('scannerExportBtn')?.addEventListener('click', () => {
    const league = byId('scanLeague').value;
    const scope = byId('scanScope').value;
    const group = byId('scanGroup').value;
    const minGames = Number(byId('scanMinGames').value || 1);
    const rows = DATA.marketRows
      .filter((r) => (league === 'Todas' || r.league === league) && r.scope === scope && Number(r.jogos || 0) >= minGames && marketInGroup(r.market, group))
      .map((r) => ({ ...r, opportunityScore: opportunityScore(r) }))
      .sort((a, b) => Number(b.opportunityScore ?? -999) - Number(a.opportunityScore ?? -999));
    downloadCSV(
      `scanner_${league}_${scope}.csv`,
      ['Liga', 'Equipa', 'Mercado', 'Jogos', 'HitRate', 'FormRecent5', 'SampleQuality', 'OpportunityScore', 'EdgeVsLiga', 'ROI', 'Value'],
      rows.map((r) => [leagueLabel(r.league), r.team, r.market, r.jogos, r.hit_rate, r.form_recent_5, sampleQuality(r.jogos).label, r.opportunityScore, r.edge_vs_liga, r.roi_unid_por_aposta, r.value_estimado])
    );
  });

  byId('shortlistExportBtn')?.addEventListener('click', () => {
    const s = PREJOGO_STATE?.shortlist || [];
    if (!s.length) return;
    downloadCSV(
      `shortlist_${PREJOGO_STATE.league}_${PREJOGO_STATE.home}_vs_${PREJOGO_STATE.away}.csv`,
      ['Mercado', 'EdgeCasa', 'EdgeFora', 'EdgeMedia', 'HitMedio'],
      s.map((r) => [r.market, r.homeEdge, r.awayEdge, r.avg, r.hitAvg])
    );
  });
}

main().catch((err) => {
  console.error(err);
  alert('Não foi possível carregar os dados do site.');
});
