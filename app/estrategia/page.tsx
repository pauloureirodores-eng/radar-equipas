import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

export default function EstrategiaPage() {
  return (
    <>
      <SiteHeader activeTab="Estratégia" />
      <PageShell>
        <PageIntro title="Estratégia" description="Fluxo executivo de decisão: probabilidade, preço, edge, stake e risco." />
      </PageShell>
    </>
  );
}
