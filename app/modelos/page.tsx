import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

const modelRows = [
  { league: "Bundesliga", team: "Bayern Munich", market: "Under 2.5 golos", pModel: "13.1%", oddsFair: "7.64", edge: "-14.27 pp", confidence: "Alta" },
  { league: "Eredivisie", team: "PSV Eindhoven", market: "Under 2.5 golos", pModel: "18.6%", oddsFair: "5.38", edge: "-11.96 pp", confidence: "Alta" },
  { league: "Serie A", team: "Inter", market: "Vitoria (1X2)", pModel: "71.2%", oddsFair: "1.40", edge: "8.42 pp", confidence: "Alta" },
  { league: "Ligue 1", team: "Lille", market: "Casa DNB", pModel: "64.3%", oddsFair: "1.55", edge: "4.61 pp", confidence: "Media" }
];

function CardShell({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-[2rem] border border-white/10 bg-white/5 shadow-2xl shadow-black/20 ${className}`}>
      {children}
    </section>
  );
}

export default function ModelosPage() {
  return (
    <>
      <SiteHeader activeTab="Modelos" />
      <PageShell>
        <PageIntro
          title="Lab Pro"
          description="Ambiente tecnico de validacao e robustez do modelo. Use para confirmar qualidade do sinal antes da execucao."
        />

        <CardShell className="bg-gradient-to-br from-[#0d1d34] to-[#09111e] p-6">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-3xl font-semibold tracking-tight text-white">Modelos (Lab Pro)</h2>
            <span className="rounded-full border border-white/15 bg-white/5 px-3 py-1 text-sm text-white/80">Area avancada</span>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-4">
            {["Liga", "Contexto", "Grupo", "Min. confianca"].map((label) => (
              <label key={label} className="space-y-2">
                <span className="text-sm text-white/60">{label}</span>
                <div className="rounded-2xl border border-white/10 bg-black/15 px-4 py-3 text-white/85">Todos</div>
              </label>
            ))}
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <CardShell className="bg-black/15 p-5">
              <p className="text-sm text-white/60">Mercados filtrados</p>
              <p className="mt-2 text-4xl font-semibold text-white">4210</p>
            </CardShell>
            <CardShell className="bg-black/15 p-5">
              <p className="text-sm text-white/60">Edge medio vs odds</p>
              <p className="mt-2 text-4xl font-semibold text-white">-0.48 pp</p>
            </CardShell>
            <CardShell className="bg-black/15 p-5">
              <p className="text-sm text-white/60">EV medio modelo</p>
              <p className="mt-2 text-4xl font-semibold text-white">-0.11%</p>
            </CardShell>
            <CardShell className="bg-black/15 p-5">
              <p className="text-sm text-white/60">Top oportunidade</p>
              <p className="mt-2 text-2xl font-semibold text-white">Getafe Vitoria (1X2)</p>
            </CardShell>
          </div>
        </CardShell>

        <CardShell className="p-6">
          <h3 className="text-2xl font-semibold text-white">Mercados Modelados</h3>
          <div className="mt-5 overflow-x-auto rounded-2xl border border-white/10">
            <table className="w-full min-w-[980px] border-collapse">
              <thead className="bg-white/5">
                <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-white/60">
                  <th className="px-4 py-3">Liga</th>
                  <th className="px-4 py-3">Equipa</th>
                  <th className="px-4 py-3">Mercado</th>
                  <th className="px-4 py-3">P modelo</th>
                  <th className="px-4 py-3">Odds justas</th>
                  <th className="px-4 py-3">Edge vs odds</th>
                  <th className="px-4 py-3">Confianca</th>
                </tr>
              </thead>
              <tbody>
                {modelRows.map((row) => (
                  <tr key={`${row.team}-${row.market}`} className="border-t border-white/10 text-white/85">
                    <td className="px-4 py-4">{row.league}</td>
                    <td className="px-4 py-4">{row.team}</td>
                    <td className="px-4 py-4">{row.market}</td>
                    <td className="px-4 py-4">{row.pModel}</td>
                    <td className="px-4 py-4">{row.oddsFair}</td>
                    <td className={`px-4 py-4 ${row.edge.startsWith("-") ? "text-amber-300" : "text-emerald-300"}`}>{row.edge}</td>
                    <td className="px-4 py-4">
                      <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-white">{row.confidence}</span>
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
