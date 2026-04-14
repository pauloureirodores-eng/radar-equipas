import Link from "next/link";
import { SectionHeader } from "@/components/layout/section-header";
import {
  compactWatchlist,
  dashboardKpis,
  featuredMarkets,
  scannerSummaryRows,
  topOpportunities,
  weeklyAlerts
} from "@/lib/mock/dashboard";

function CardShell({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-[2rem] border border-white/10 bg-white/5 shadow-2xl shadow-black/20 ${className}`}>
      {children}
    </div>
  );
}

export function DashboardHome() {
  return (
    <div className="space-y-10">
      <section className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
        <CardShell className="overflow-hidden bg-gradient-to-br from-white/8 via-white/5 to-transparent">
          <div className="p-8 md:p-10">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-200">Produto premium curado</span>
              <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-white/70">Pré-jogo · Matchup · Execução</span>
            </div>

            <div className="space-y-5">
              <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-white md:text-6xl">
                Um terminal de análise desportiva com <span className="text-cyan-300">convicção</span>, não apenas dados.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-white/65 md:text-lg">
                Homepage editorial, scanner operacional separado, matchup em duas camadas e uma área técnica de modelos para validação séria do sinal.
              </p>
            </div>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/scanner" className="rounded-full bg-white px-6 py-3 text-sm font-medium text-slate-950 transition hover:bg-white/90">
                Abrir Scanner
              </Link>
              <Link href="/matchup" className="rounded-full border border-white/15 bg-white/5 px-6 py-3 text-sm font-medium text-white transition hover:bg-white/10">
                Ver Matchup
              </Link>
            </div>
          </div>
        </CardShell>

        <CardShell className="bg-[#0b1628]/85 p-6">
          <div className="text-[11px] uppercase tracking-[0.28em] text-white/45">Começar em 3 passos</div>
          <h2 className="mt-2 text-2xl font-semibold text-white">Fluxo ideal</h2>
          <div className="mt-5 space-y-4">
            {[
              ["1. Ler oportunidade", "Jogo da Semana, alertas e mercados em destaque."],
              ["2. Confirmar o matchup", "Leitura Base + Contexto Avançado do jogo."],
              ["3. Executar com critério", "Preço, edge, stake, risco e plano final."]
            ].map(([title, desc]) => (
              <div key={title} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-sm font-medium text-white">{title}</div>
                <div className="mt-1 text-sm text-white/55">{desc}</div>
              </div>
            ))}
          </div>
        </CardShell>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {dashboardKpis.map((item) => (
          <CardShell key={item.label}>
            <div className="p-5">
              <div className="text-[11px] uppercase tracking-[0.24em] text-white/45">{item.label}</div>
              <div className="mt-2 text-3xl font-semibold text-white">{item.value}</div>
              <div className="mt-1 text-sm text-white/55">{item.sub}</div>
            </div>
          </CardShell>
        ))}
      </section>

      <section className="space-y-6">
        <SectionHeader
          eyebrow="Flagship"
          title="Jogo da Semana"
          description="O grande card editorial da homepage. Menos ruído, mais convicção e uma leitura curta do porquê deste ser o matchup principal."
          action={
            <Link href="/matchup" className="rounded-full border border-white/15 bg-white/5 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/10">
              Abrir Matchup
            </Link>
          }
        />

        <CardShell className="bg-gradient-to-br from-[#10233c] to-[#0b1424] p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-cyan-400/15 px-3 py-1 text-sm text-cyan-200">Primeira leitura</span>
            <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-white/70">Benfica vs Braga</span>
          </div>

          <div className="mt-6 grid gap-8 xl:grid-cols-[1fr_0.9fr]">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-white/45">Resumo executivo</div>
              <h3 className="mt-3 text-3xl font-semibold tracking-tight text-white">
                Ritmo alto, convergência em golos e pressão do mercado do lado do Over.
              </h3>
              <p className="mt-4 max-w-xl leading-7 text-white/65">
                A leitura junta forma ofensiva recente, mismatch de estilos, fragilidade em transição defensiva e um spot competitivo favorável para golos.
              </p>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                {[
                  ["Prob. Over 2.5", "64%"],
                  ["Prob. BTTS", "61%"],
                  ["Confiança", "Alta"]
                ].map(([label, value]) => (
                  <div key={label} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] text-white/45">{label}</div>
                    <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.75rem] border border-white/10 bg-black/20 p-5">
              <div className="text-[11px] uppercase tracking-[0.24em] text-white/45">Mercados sugeridos</div>
              <div className="mt-1 text-lg font-medium text-white">Top 3 sinais</div>
              <div className="mt-5 space-y-4">
                {[
                  ["Over 2.5", "+7.2% edge", "78%"],
                  ["BTTS", "+5.8% edge", "71%"],
                  ["Over Cantos", "+4.0% edge", "63%"]
                ].map(([market, edge, score]) => (
                  <div key={market} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium text-white">{market}</div>
                        <div className="text-sm text-white/55">{edge}</div>
                      </div>
                      <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-white">{score}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardShell>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <CardShell className="p-6">
          <SectionHeader eyebrow="Alertas" title="Alertas Semanais" description="Movimento de preço, indisponibilidades e contexto competitivo." />
          <div className="mt-5 space-y-3">
            {weeklyAlerts.map((alert) => (
              <div key={alert} className="rounded-2xl border border-white/10 bg-black/15 p-4 text-sm leading-6 text-white/75">
                {alert}
              </div>
            ))}
          </div>
        </CardShell>

        <CardShell className="p-6">
          <SectionHeader eyebrow="Mercados" title="Mercados em Destaque" description="Oportunidades curadas, não o scanner completo." />
          <div className="mt-5 space-y-3">
            {featuredMarkets.map((row) => (
              <div key={row.market + row.game} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-white">{row.market}</div>
                    <div className="text-sm text-white/55">{row.game}</div>
                  </div>
                  <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-200">{row.edge}</span>
                </div>
              </div>
            ))}
          </div>
        </CardShell>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <CardShell className="p-6">
          <SectionHeader
            eyebrow="Shortlist"
            title="Top Oportunidades"
            description="Versão editorial da shortlist. O scanner completo fica noutra página."
            action={
              <Link href="/scanner" className="rounded-full border border-white/15 bg-white/5 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/10">
                Abrir Scanner completo
              </Link>
            }
          />

          <div className="mt-5 space-y-3">
            {topOpportunities.map((row) => (
              <div key={row.market + row.game} className="grid gap-3 rounded-2xl border border-white/10 bg-black/15 p-4 md:grid-cols-[1.1fr_1fr_0.5fr_0.4fr] md:items-center">
                <div>
                  <div className="font-medium text-white">{row.market}</div>
                  <div className="text-sm text-white/55">{row.game}</div>
                </div>
                <div className="text-sm text-white/65">{row.note}</div>
                <div className="text-lg font-semibold text-emerald-300">{row.edge}</div>
                <div className="rounded-full bg-white/10 px-3 py-1 text-center text-sm text-white">{row.confidence}</div>
              </div>
            ))}
          </div>
        </CardShell>

        <div className="grid gap-6">
          <CardShell className="p-6">
            <SectionHeader eyebrow="Scanner" title="Resumo do Scanner" description="Só os sinais mais fortes, sem filtros densos na homepage." />
            <div className="mt-5 overflow-hidden rounded-[1.5rem] border border-white/10">
              <div className="grid grid-cols-5 bg-white/5 px-4 py-3 text-[11px] uppercase tracking-[0.22em] text-white/45">
                <div>Equipa</div>
                <div>Liga</div>
                <div>Mercado</div>
                <div>Edge</div>
                <div>Status</div>
              </div>
              {scannerSummaryRows.map((row) => (
                <div key={row.team + row.market} className="grid grid-cols-5 border-t border-white/10 px-4 py-3 text-sm text-white/78">
                  <div>{row.team}</div>
                  <div>{row.league}</div>
                  <div>{row.market}</div>
                  <div className="text-emerald-300">{row.edge}</div>
                  <div>{row.status}</div>
                </div>
              ))}
            </div>
          </CardShell>

          <CardShell className="p-6">
            <SectionHeader eyebrow="Watchlist" title="Watchlist compacta" description="A versão persistente fica na tab Scanner." />
            <div className="mt-5 flex flex-wrap gap-2">
              {compactWatchlist.map((team) => (
                <span key={team} className="rounded-full border border-white/10 bg-black/15 px-4 py-2 text-sm text-white/80">
                  {team}
                </span>
              ))}
            </div>
          </CardShell>
        </div>
      </section>

      <CardShell className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.26em] text-white/45">Atualização</div>
            <div className="mt-1 text-lg font-medium text-white">A homepage termina aqui e entrega o melhor da plataforma.</div>
            <div className="mt-1 text-sm text-white/55">Tudo o que é operacional, técnico ou de execução profunda vive nas tabs próprias.</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["Scanner", "/scanner"],
              ["Matchup", "/matchup"],
              ["Modelos", "/modelos"],
              ["Estratégia", "/estrategia"]
            ].map(([label, href]) => (
              <Link key={label} href={href} className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/10">
                {label}
              </Link>
            ))}
          </div>
        </div>
      </CardShell>
    </div>
  );
}
