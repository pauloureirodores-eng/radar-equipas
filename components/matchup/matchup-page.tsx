import { MatchupHeader } from "@/components/matchup/matchup-header";
import { MatchupSectionsNav } from "@/components/matchup/matchup-sections-nav";
import { MatchupMarketStack } from "@/components/matchup/matchup-market-stack";
import { BaseReadSection } from "@/components/matchup/base-read-section";
import { AdvancedContextSection } from "@/components/matchup/advanced-context-section";
import type { MatchupData } from "@/lib/mock/matchup";

export function MatchupPage({ data }: { data: MatchupData }) {
  return (
    <div className="space-y-8">
      <MatchupHeader data={data} />

      <div className="grid gap-6 lg:grid-cols-[0.22fr_0.78fr]">
        <aside className="lg:sticky lg:top-28 lg:h-fit">
          <MatchupSectionsNav />
        </aside>

        <div className="space-y-8">
          <MatchupMarketStack markets={data.markets} />
          <BaseReadSection data={data} />
          <AdvancedContextSection items={data.advancedContext} />
        </div>
      </div>
    </div>
  );
}
