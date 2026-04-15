import Link from "next/link";

type Market = { market: string; edge: string; score: number };

export function MatchupMarketStack({ markets }: { markets: Market[] }) {
  return (
    <section id="mercados" className="scroll-mt-28 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-white/45">Decisao rapida</div>
          <h2 className="mt-2 text-2xl font-semibold text-white">Mercados alinhados</h2>
          <p className="mt-1 text-sm text-white/55">O Matchup deve entregar primeiro conclusao, so depois detalhe.</p>
        </div>
        <Link
          href="/estrategia#fluxo-decisao"
          className="rounded-full bg-white px-5 py-3 text-sm font-medium text-slate-950 transition hover:bg-white/90"
        >
          Ir para Estrategia
        </Link>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        {markets.map((item) => (
          <div key={item.market} className="rounded-2xl border border-white/10 bg-black/15 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium text-white">{item.market}</div>
                <div className="text-sm text-white/55">{item.edge}</div>
              </div>
              <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-white">{item.score}%</span>
            </div>
            <div className="mt-4 h-2 rounded-full bg-white/10">
              <div className="h-2 rounded-full bg-white" style={{ width: `${item.score}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
