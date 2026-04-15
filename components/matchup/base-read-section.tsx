import type { MatchupData } from "@/lib/mock/matchup";
import RadarChartClient from "@/components/matchup/radar-chart-client";

function MiniInsight({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
      <div className="text-sm font-medium text-white">{title}</div>
      <div className="mt-2 text-sm leading-6 text-white/60">{text}</div>
    </div>
  );
}

export function BaseReadSection({ data }: { data: MatchupData }) {
  return (
    <section id="base-read" className="scroll-mt-28 space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-[0.3em] text-white/45">Camada 1</div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white md:text-3xl">Leitura Base</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60 md:text-base">
          Primeiro o retrato estatistico do confronto. Esta camada deve responder rapido ao que o jogo tende a ser.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20">
          <h3 className="text-xl font-semibold text-white">Confronto Casa vs Fora</h3>
          <p className="mt-1 text-sm text-white/55">Overview imediato da forca relativa em contexto.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {data.overview.map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                <div className="text-[11px] uppercase tracking-[0.22em] text-white/45">{item.label}</div>
                <div className="mt-2 text-xl font-semibold text-white">{item.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20">
          <h3 className="text-xl font-semibold text-white">Radar + Comparador</h3>
          <p className="mt-1 text-sm text-white/55">Juntar estes dois blocos reduz friccao e melhora leitura visual.</p>
          <div className="mt-5 grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-[1.5rem] border border-white/10 bg-black/15 p-5">
              <RadarChartClient />
            </div>
            <div className="space-y-3">
              {data.comparator.map((item) => (
                <div key={item.metric} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-white/75">{item.metric}</span>
                    <span className="font-medium text-white">{item.delta}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20">
          <h3 className="text-xl font-semibold text-white">Mercados Convergentes</h3>
          <p className="mt-1 text-sm text-white/55">Este bloco deve ser mais visual e menos tabelar.</p>
          <div className="mt-5 space-y-3">
            {data.convergingMarkets.map((item) => (
              <div key={item.market} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-white">{item.market}</div>
                  <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-200">{item.avg}</span>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-white/60 sm:grid-cols-2">
                  <div>{item.home}</div>
                  <div>{item.away}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20">
          <h3 className="text-xl font-semibold text-white">Insights + H2H</h3>
          <p className="mt-1 text-sm text-white/55">Sintese editorial acima; historico direto como contexto secundario.</p>
          <div className="mt-5 space-y-4">
            {data.insights.map((item) => (
              <MiniInsight key={item.title} title={item.title} text={item.text} />
            ))}
            <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
              <div className="text-sm font-medium text-white">Historico Direto</div>
              <div className="mt-2 text-sm leading-6 text-white/60">
                Mostrar so 3 a 5 jogos em formato compacto, para nao distrair da leitura principal.
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
