import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

export default function ModelosPage() {
  return (
    <>
      <SiteHeader activeTab="Modelos" />
      <PageShell>
        <PageIntro title="Modelos" description="Area tecnica Lab Pro para outputs modelados, calibracao e confiabilidade." />
      </PageShell>
    </>
  );
}
