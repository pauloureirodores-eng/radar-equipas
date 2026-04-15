import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

const scannerRows = [
  { team: "Benfica", league: "POR1", market: "Over 2.5", games: 30, hit: "83.3%", edge: "45.8 pp", roi: "20.4%" },
  { team: "Bayern Munich", league: "GER1", market: "Vitoria (1X2)", games: 28, hit: "82.1%", edge: "44.6 pp", roi: "18.7%" },
  { team: "Porto", league: "POR1", market: "Vitoria (1X2)", games: 28, hit: "82.1%", edge: "45.1 pp", roi: "19.1%" },
  { team: "PSV Eindhoven", league: "NED1", market: "Over 2.5", games: 29, hit: "79.3%", edge: "42.0 pp", roi: "17.4%" },
  { team: "Inter", league: "ITA1", market: "Vitoria (1X2)", games: 31, hit: "74.2%", edge: "37.3 pp", roi: "14.8%" }
];

function CardShell({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-[2rem] border border-white/10 bg-white/5 shadow-2xl shadow-black/20 ${className}`}>
      {children}
    </section>
  );
}

export default function ScannerPage() {
  return (
    <>
      <SiteHeader activeTab="Scanner" />
      <PageShell>
        <PageIntro
          title="Scanner Operacional"
          description="Area de exploracao completa com filtros detalhados, watchlist persistente e exportacao."
        />

        <CardShell className="bg-gradient-to-br from-[#0d1d34] to-[#0a1321] p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-3xl font-semibold tracking-tight text-white">Scanner Multi-Equipa</h2>
              <p className="mt-2 text-white/60">
                O Dashboard mostra apenas resumo editorial. O scanner completo vive aqui, com filtros e tabela total.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 transition hover:bg-white/10">
                Limpar filtros
              </button>
              <button className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 transition hover:bg-white/10">
                Exportar dados
              </button>
            </div>
          </div>

          <div className="mt-5 rounded-2xl border border-white/10 bg-black/15 p-4">
            <div className="text-sm tracking-wide text-white/70">FILTROS</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {["Liga", "Contexto", "Mercado", "Grupo", "Min. jogos", "Conf. minima"].map((chip) => (
                <span key={chip} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/80">
                  {chip}
                </span>
              ))}
            </div>
            <p className="mt-4 text-sm leading-6 text-white/65">
              120 mercados listados nesta vista. Melhor oportunidade do dia: Barcelona (Vitoria 1X2).
            </p>
          </div>

          <div className="mt-5 overflow-x-auto rounded-2xl border border-white/10">
            <table className="w-full min-w-[980px] border-collapse">
              <thead className="bg-white/5">
                <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-white/60">
                  <th className="px-4 py-3">Equipa</th>
                  <th className="px-4 py-3">Liga</th>
                  <th className="px-4 py-3">Mercado</th>
                  <th className="px-4 py-3">Jogos</th>
                  <th className="px-4 py-3">Sucesso</th>
                  <th className="px-4 py-3">Edge vs liga</th>
                  <th className="px-4 py-3">ROI</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {scannerRows.map((row) => (
                  <tr key={`${row.team}-${row.market}`} className="border-t border-white/10 text-white/85">
                    <td className="px-4 py-4">{row.team}</td>
                    <td className="px-4 py-4 text-white/65">{row.league}</td>
                    <td className="px-4 py-4">{row.market}</td>
                    <td className="px-4 py-4">{row.games}</td>
                    <td className="px-4 py-4">{row.hit}</td>
                    <td className="px-4 py-4 text-emerald-300">{row.edge}</td>
                    <td className="px-4 py-4">{row.roi}</td>
                    <td className="px-4 py-4">
                      <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-200">Alta</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardShell>
      </PageShell>
    </>
  );
}
