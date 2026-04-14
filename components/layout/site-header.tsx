import Link from "next/link";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/" },
  { label: "Scanner", href: "/scanner" },
  { label: "Matchup", href: "/matchup" },
  { label: "Modelos", href: "/modelos" },
  { label: "Estrategia", href: "/estrategia" }
];

type SiteHeaderProps = {
  activeTab?: string;
};

export function SiteHeader({ activeTab = "Dashboard" }: SiteHeaderProps) {
  return (
    <header className="sticky top-4 z-30 mx-auto mb-8 max-w-7xl px-6 pt-6 md:px-8 lg:px-10">
      <div className="rounded-3xl border border-white/10 bg-[#081324]/82 px-5 py-4 shadow-2xl shadow-black/20 backdrop-blur-xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.35em] text-white/40">Analista de Futebol</div>
            <div className="mt-1 text-xl font-semibold tracking-tight text-white">Radar de Equipas & Mercados</div>
          </div>

          <nav className="flex flex-wrap items-center gap-2 text-sm">
            {NAV_ITEMS.map((item) => {
              const isActive = activeTab === item.label;
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={[
                    "rounded-full px-4 py-2 transition",
                    isActive
                      ? "bg-white text-slate-950"
                      : "border border-white/10 bg-white/5 text-white/75 hover:bg-white/10"
                  ].join(" ")}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </header>
  );
}
