import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

export default function EstrategiaPage() {
  return (
    <>
      <SiteHeader activeTab="Estrategia" />
      <PageShell>
        <PageIntro title="Estrategia" description="Fluxo executivo de decisao: probabilidade, preco, edge, stake e risco." />
        <section
          id="fluxo-decisao"
          className="scroll-mt-28 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20"
        >
          <p className="text-[11px] uppercase tracking-[0.24em] text-white/45">Fluxo de decisao</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Probabilidade | Preco | Edge | Stake | Risco</h2>
          <p className="mt-2 text-white/60">
            Esta ancora recebe o CTA do Matchup. No proximo passo, podemos transformar este bloco no modulo completo de
            execucao.
          </p>
        </section>
      </PageShell>
    </>
  );
}
