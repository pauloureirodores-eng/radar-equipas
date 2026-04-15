import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

const shortlist = [
  { market: "Over 2.5", game: "Benfica vs Braga", edge: "+7.2%" },
  { market: "BTTS", game: "Atalanta vs Napoli", edge: "+5.8%" },
  { market: "Casa DNB", game: "Lille vs Rennes", edge: "+4.6%" }
];

function CardShell({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-[2rem] border border-white/10 bg-white/5 shadow-2xl shadow-black/20 ${className}`}>
      {children}
    </section>
  );
}

function TinyKpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/15 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-white/45">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}

export default function EstrategiaPage() {
  return (
    <>
      <SiteHeader activeTab="Estrategia" />
      <PageShell>
        <PageIntro
          title="Fluxo de Decisao"
          description="Transforma analise em execucao: probabilidade, preco, edge, stake e risco numa sequencia objetiva."
        />

        <CardShell id="fluxo-decisao" className="scroll-mt-28 bg-gradient-to-br from-[#10233c] to-[#09111e] p-6">
          <div className="grid gap-3 md:grid-cols-5">
            <TinyKpi label="Probabilidade" value="64%" />
            <TinyKpi label="Preco mercado" value="1.72" />
            <TinyKpi label="Edge" value="+7.2%" />
            <TinyKpi label="Stake (Kelly)" value="3.4%" />
            <TinyKpi label="Risco" value="Medio" />
          </div>
        </CardShell>

        <div className="grid gap-6 xl:grid-cols-2">
          <CardShell className="p-6">
            <h2 className="text-2xl font-semibold text-white">Pre-jogo (Poisson + Shortlist)</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Expected Goals</p>
                <div className="mt-3 space-y-2">
                  <div className="flex items-center justify-between text-white/85"><span>Bayern Munich</span><span>2.37</span></div>
                  <div className="flex items-center justify-between text-white/85"><span>Dortmund</span><span>1.47</span></div>
                </div>
              </CardShell>
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">1X2</p>
                <div className="mt-3 space-y-2">
                  <div className="flex items-center justify-between text-white/85"><span>1</span><span>57.4%</span></div>
                  <div className="flex items-center justify-between text-white/85"><span>X</span><span>19.3%</span></div>
                  <div className="flex items-center justify-between text-white/85"><span>2</span><span>23.2%</span></div>
                </div>
              </CardShell>
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Totais</p>
                <div className="mt-3 space-y-2">
                  <div className="flex items-center justify-between text-white/85"><span>Over 2.5</span><span>73.8%</span></div>
                  <div className="flex items-center justify-between text-white/85"><span>BTTS</span><span>69.9%</span></div>
                </div>
              </CardShell>
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Configuracao</p>
                <div className="mt-3 space-y-2">
                  <div className="flex items-center justify-between text-white/85"><span>Peso forma</span><span>35%</span></div>
                  <div className="flex items-center justify-between text-white/85"><span>Liga</span><span>Bundesliga</span></div>
                </div>
              </CardShell>
            </div>
          </CardShell>

          <CardShell className="p-6">
            <h2 className="text-2xl font-semibold text-white">Confianca do Matchup</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Score de confianca</p>
                <p className="mt-2 text-4xl font-semibold text-white">75</p>
              </CardShell>
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Fator amostra</p>
                <p className="mt-2 text-4xl font-semibold text-white">14/14</p>
              </CardShell>
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Qualidade da amostra</p>
                <p className="mt-2 text-4xl font-semibold text-white">73.7%</p>
              </CardShell>
              <CardShell className="bg-black/15 p-5">
                <p className="text-sm text-white/60">Estabilidade</p>
                <p className="mt-2 text-4xl font-semibold text-white">76.1%</p>
              </CardShell>
            </div>
          </CardShell>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <CardShell className="p-6">
            <h2 className="text-2xl font-semibold text-white">Shortlist de Mercados</h2>
            <div className="mt-4 space-y-3">
              {shortlist.map((row) => (
                <article key={row.market} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{row.market}</p>
                      <p className="text-sm text-white/60">{row.game}</p>
                    </div>
                    <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-200">{row.edge}</span>
                  </div>
                </article>
              ))}
            </div>
          </CardShell>

          <CardShell className="p-6">
            <h2 className="text-2xl font-semibold text-white">Heatmap de Resultados</h2>
            <div className="mt-4 grid grid-cols-5 gap-2">
              {Array.from({ length: 25 }).map((_, idx) => (
                <div
                  key={idx}
                  className={`aspect-square rounded-xl border border-white/10 ${
                    idx % 6 === 0 ? "bg-cyan-400/20" : idx % 4 === 0 ? "bg-emerald-400/15" : "bg-white/5"
                  }`}
                />
              ))}
            </div>
          </CardShell>
        </div>
      </PageShell>
    </>
  );
}
