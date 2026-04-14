import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

export default function EstrategiaPage() {
  return (
    <>
      <SiteHeader activeTab="Estrategia" />
      <PageShell>
        <PageIntro title="Estrategia" description="Fluxo executivo de decisao: probabilidade, preco, edge, stake e risco." />
      </PageShell>
    </>
  );
}
