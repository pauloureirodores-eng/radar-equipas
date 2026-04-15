import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { MatchupPremium } from "@/components/matchup/matchup-premium";

export default function MatchupPage() {
  return (
    <>
      <SiteHeader activeTab="Matchup" />
      <PageShell>
        <MatchupPremium />
      </PageShell>
    </>
  );
}
