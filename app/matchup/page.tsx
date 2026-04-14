import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { PageIntro } from "@/components/layout/page-intro";

export default function MatchupPage() {
  return (
    <>
      <SiteHeader activeTab="Matchup" />
      <PageShell>
        <PageIntro title="Matchup" description="Leitura Base + Contexto Avançado para análise profunda do confronto." />
      </PageShell>
    </>
  );
}
