type MatchupHeaderProps = {
  data: {
    homeTeam: string;
    awayTeam: string;
    summary: string;
    confidence: string;
    avgEdge: string;
    availabilityRisk: string;
    contextStrength: string;
  };
};

function StatPill({
  label,
  value,
  tone = "default"
}: {
  label: string;
  value: string;
  tone?: "default" | "good" | "warn";
}) {
  const toneClass =
    tone === "good"
      ? "bg-emerald-400/15 text-emerald-200"
      : tone === "warn"
        ? "bg-amber-400/15 text-amber-200"
        : "bg-white/5 text-white/85";

  return (
    <div className={`rounded-2xl border border-white/10 px-4 py-3 ${toneClass}`}>
      <div className="text-[11px] uppercase tracking-[0.22em] text-white/45">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

export function MatchupHeader({ data }: MatchupHeaderProps) {
  return (
    <section id="resumo" className="scroll-mt-28 h-full">
      <div className="h-full overflow-hidden rounded-[2rem] border border-white/10 bg-gradient-to-br from-[#10233c] to-[#0a1321] shadow-2xl shadow-black/20">
        <div className="flex h-full flex-col p-8 md:p-10">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-cyan-400/15 px-3 py-1 text-sm text-cyan-200">Flagship matchup</span>
            <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-white/70">
              {data.homeTeam} vs {data.awayTeam}
            </span>
          </div>

          <div className="space-y-5">
            <div className="text-[11px] uppercase tracking-[0.28em] text-white/45">Resumo executivo</div>
            <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-white md:text-5xl">
              {data.summary}
            </h1>
            <p className="max-w-2xl text-base leading-7 text-white/65 md:text-lg">
              A pagina Matchup deve dar primeiro a conclusao, e so depois abrir a explicacao detalhada do cenario.
            </p>
          </div>

          <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatPill label="Confianca" value={data.confidence} tone="good" />
            <StatPill label="Edge medio" value={data.avgEdge} tone="good" />
            <StatPill label="Risco disponibilidade" value={data.availabilityRisk} tone="warn" />
            <StatPill label="Contexto" value={data.contextStrength} />
          </div>
        </div>
      </div>
    </section>
  );
}
