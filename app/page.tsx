import { SiteHeader } from "@/components/layout/site-header";
import { PageShell } from "@/components/layout/page-shell";
import { DashboardHome } from "@/components/dashboard/dashboard-home";

export default function DashboardPage() {
  return (
    <>
      <SiteHeader activeTab="Dashboard" />
      <PageShell>
        <DashboardHome />
      </PageShell>
    </>
  );
}
