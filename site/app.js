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

let DATA = null;

function setActiveTab(tabId) {
  document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tabId));
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
  byId(`panel-${tabId}`).classList.add('active');
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
}

function getResumoRow(league, team, scope) {
  return DATA.resumoRows.find((r) => r.league === league && r.team === team && r.scope === scope);
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
  renderConfrontoMarkets(league, home, away);
}

function getSeries(league, team, venue, metric) {
  return DATA.seriesRows
    .filter((r) => r.league === league && r.team === team && r.venue === venue)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .map((r) => ({ date: r.date, value: Number(r[metric]) }));
}

function renderForma() {
  const league = byId('formLeague').value;
  const team = byId('formTeam').value;
  const venue = byId('formVenue').value;
  const metric = byId('formMetric').value;

  const series = getSeries(league, team, venue, metric).filter((x) => Number.isFinite(x.value));
  const latest = series.length ? series[series.length - 1].value : null;
  const prev = series.length > 1 ? series[series.length - 2].value : null;
  const avg = series.length ? series.reduce((a, x) => a + x.value, 0) / series.length : null;
  const delta = (latest != null && prev != null) ? latest - prev : null;

  byId('formTrendCards').innerHTML = `
    <article class="kpi-card"><h3>Último valor</h3><div class="kpi-row"><span>${metric}</span><strong>${latest != null ? fmtNum(latest) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Tendência</h3><div class="kpi-row"><span>Último vs anterior</span><strong>${delta != null ? (delta >= 0 ? '+' : '') + fmtNum(delta) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Média da série</h3><div class="kpi-row"><span>Média</span><strong>${avg != null ? fmtNum(avg) : '—'}</strong></div></article>
    <article class="kpi-card"><h3>Amostra</h3><div class="kpi-row"><span>Registos</span><strong>${series.length}</strong></div></article>
  `;

  byId('formTable').querySelector('tbody').innerHTML = series.slice(-12).reverse().map((r, idx, arr) => {
    const next = arr[idx + 1];
    const d = next ? r.value - next.value : 0;
    const tr = next ? (d > 0 ? 'A subir' : d < 0 ? 'A descer' : 'Estável') : '—';
    return `<tr><td>${r.date}</td><td>${fmtNum(r.value)}</td><td>${tr}</td></tr>`;
  }).join('') || '<tr><td colspan="3">Sem dados de forma para este filtro.</td></tr>';
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

function avgLeague(resumoRows, league, scope, col) {
  const vals = resumoRows.filter((r) => r.league === league && r.scope === scope).map((r) => Number(r[col])).filter((x) => Number.isFinite(x));
  if (!vals.length) return null;
  return vals.reduce((a, x) => a + x, 0) / vals.length;
}

function recentFormRate(league, team, venue, metric) {
  const s = getSeries(league, team, venue, metric).filter((x) => Number.isFinite(x.value));
  if (!s.length) return null;
  return s.slice(-5).reduce((a, x) => a + x.value, 0) / Math.min(s.length, 5);
}

function poissonProbs(lambdaHome, lambdaAway, maxGoals = 10) {
  const pmf = (lam, k) => {
    if (lam <= 0) return k === 0 ? 1 : 0;
    let fact = 1;
    for (let i = 2; i <= k; i++) fact *= i;
    return Math.exp(-lam) * Math.pow(lam, k) / fact;
  };

  const h = Array.from({ length: maxGoals + 1 }, (_, k) => pmf(lambdaHome, k));
  const a = Array.from({ length: maxGoals + 1 }, (_, k) => pmf(lambdaAway, k));

  let p1 = 0, px = 0, p2 = 0, over25 = 0, btts = 0;
  for (let i = 0; i <= maxGoals; i++) {
    for (let j = 0; j <= maxGoals; j++) {
      const p = h[i] * a[j];
      if (i > j) p1 += p;
      if (i === j) px += p;
      if (i < j) p2 += p;
      if (i + j >= 3) over25 += p;
      if (i > 0 && j > 0) btts += p;
    }
  }

  return { p1, px, p2, over25, btts };
}

function computeExpectedGoals(league, homeTeam, awayTeam, weightRecent = 0.35) {
  const home = getResumoRow(league, homeTeam, 'Casa');
  const away = getResumoRow(league, awayTeam, 'Fora');
  if (!home || !away) return null;

  const lgHomeGF = avgLeague(DATA.resumoRows, league, 'Casa', 'golos_marcados');
  const lgHomeGA = avgLeague(DATA.resumoRows, league, 'Casa', 'golos_sofridos');
  const lgAwayGF = avgLeague(DATA.resumoRows, league, 'Fora', 'golos_marcados');
  const lgAwayGA = avgLeague(DATA.resumoRows, league, 'Fora', 'golos_sofridos');
  if (![lgHomeGF, lgHomeGA, lgAwayGF, lgAwayGA].every((x) => Number.isFinite(x) && x > 0)) return null;

  const seasonHome = lgHomeGF * (Number(home.golos_marcados) / lgHomeGF) * (Number(away.golos_sofridos) / lgAwayGA);
  const seasonAway = lgAwayGF * (Number(away.golos_marcados) / lgAwayGF) * (Number(home.golos_sofridos) / lgHomeGA);

  const recentHomeFor = recentFormRate(league, homeTeam, 'H', 'roll5_gf');
  const recentHomeAgainst = recentFormRate(league, homeTeam, 'H', 'roll5_ga');
  const recentAwayFor = recentFormRate(league, awayTeam, 'A', 'roll5_gf');
  const recentAwayAgainst = recentFormRate(league, awayTeam, 'A', 'roll5_ga');

  const recentHome = (Number.isFinite(recentHomeFor) && Number.isFinite(recentAwayAgainst)) ? ((recentHomeFor + recentAwayAgainst) / 2) : seasonHome;
  const recentAway = (Number.isFinite(recentAwayFor) && Number.isFinite(recentHomeAgainst)) ? ((recentAwayFor + recentHomeAgainst) / 2) : seasonAway;

  const wh = Math.max(0, Math.min(0.7, weightRecent));
  const lambdaHome = (1 - wh) * seasonHome + wh * recentHome;
  const lambdaAway = (1 - wh) * seasonAway + wh * recentAway;

  return { lambdaHome, lambdaAway };
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
    return;
  }

  const probs = poissonProbs(eg.lambdaHome, eg.lambdaAway, 10);

  byId('prejogoProbCards').innerHTML = `
    <article class="kpi-card"><h3>Expected Goals</h3><div class="kpi-row"><span>${home}</span><strong>${fmtNum(eg.lambdaHome)}</strong></div><div class="kpi-row"><span>${away}</span><strong>${fmtNum(eg.lambdaAway)}</strong></div></article>
    <article class="kpi-card"><h3>1X2</h3><div class="kpi-row"><span>1</span><strong>${fmtPct(probs.p1)}</strong></div><div class="kpi-row"><span>X</span><strong>${fmtPct(probs.px)}</strong></div><div class="kpi-row"><span>2</span><strong>${fmtPct(probs.p2)}</strong></div></article>
    <article class="kpi-card"><h3>Totais</h3><div class="kpi-row"><span>Over 2.5</span><strong>${fmtPct(probs.over25)}</strong></div><div class="kpi-row"><span>BTTS</span><strong>${fmtPct(probs.btts)}</strong></div></article>
    <article class="kpi-card"><h3>Configuração</h3><div class="kpi-row"><span>Peso forma</span><strong>${fmtPct(weight)}</strong></div><div class="kpi-row"><span>Liga</span><strong>${league}</strong></div></article>
  `;

  const shortlist = buildConfrontoMerged(league, home, away)
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 15);

  byId('prejogoShortlistTable').querySelector('tbody').innerHTML = shortlist.map((r) => `<tr><td>${r.market}</td><td>${fmtNum(r.homeEdge * 100, 1)} pp</td><td>${fmtNum(r.awayEdge * 100, 1)} pp</td><td>${fmtNum(r.avg * 100, 1)} pp</td><td>${r.hitAvg != null ? fmtPct(r.hitAvg) : '—'}</td></tr>`).join('') || '<tr><td colspan="5">Sem shortlist para este jogo.</td></tr>';
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
}

main().catch((err) => {
  console.error(err);
  alert('Não foi possível carregar os dados do site.');
});
