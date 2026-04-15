import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { MatchupPage } from "@/components/matchup/matchup-page";
import { getMatchupData } from "@/lib/mock/matchup";

export default async function Page() {
  const data = await getMatchupData();

  return (
    <>
      <SiteHeader activeTab="Matchup" />
      <PageShell>
        <MatchupPage data={data} />
      </PageShell>
    </>
  );
}
