import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

export default function ScannerPage() {
  return (
    <>
      <SiteHeader activeTab="Scanner" />
      <PageShell>
        <PageIntro title="Scanner" description="Página operacional para exploração multi-equipa, filtros detalhados e exportação." />
      </PageShell>
    </>
  );
}
