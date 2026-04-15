"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { ComponentPropsWithoutRef } from "react";
import { SectionHeader } from "@/components/layout/section-header";

type NavSection = {
  id: string;
  label: string;
};

const SIDE_NAV: NavSection[] = [
  { id: "matchup-resumo", label: "Resumo" },
  { id: "matchup-base", label: "Leitura Base" },
  { id: "matchup-contexto", label: "Contexto" },
  { id: "matchup-mercados", label: "Mercados" }
];

type CardShellProps = ComponentPropsWithoutRef<"section"> & {
  children: ReactNode;
  className?: string;
};

function CardShell({ children, className = "", ...rest }: CardShellProps) {
  return (
    <section
      {...rest}
      className={`rounded-[2rem] border border-white/10 bg-white/5 shadow-2xl shadow-black/20 transition duration-300 hover:-translate-y-0.5 hover:border-white/20 ${className}`}
    >
      {children}
    </section>
  );
}

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
      <p className="text-[11px] uppercase tracking-[0.22em] text-white/45">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function MiniInsight({ title, text }: { title: string; text: string }) {
  return (
    <article className="rounded-2xl border border-white/10 bg-black/15 p-4">
      <p className="text-sm font-medium text-white">{title}</p>
      <p className="mt-2 text-sm leading-6 text-white/60">{text}</p>
    </article>
  );
}

export function MatchupPremium() {
  const [active, setActive] = useState<string>(SIDE_NAV[0].id);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]?.target?.id) {
          setActive(visible[0].target.id);
        }
      },
      {
        root: null,
        rootMargin: "-20% 0px -55% 0px",
        threshold: [0.1, 0.25, 0.5]
      }
    );

    SIDE_NAV.forEach((section) => {
      const el = document.getElementById(section.id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  return (
    <div className="space-y-8">
      <section id="matchup-resumo" className="scroll-mt-28 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <CardShell className="overflow-hidden bg-gradient-to-br from-[#10233c] to-[#0a1321]">
          <div className="p-8 md:p-10">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="rounded-full bg-cyan-400/15 px-3 py-1 text-sm text-cyan-200">Flagship matchup</span>
              <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-white/70">Benfica vs Braga</span>
            </div>

            <div className="space-y-5">
              <p className="text-[11px] uppercase tracking-[0.28em] text-white/45">Resumo executivo</p>
              <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
                Convergencia ofensiva, espaco para golos e um contexto que reforca o sinal base.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-white/65 md:text-lg">
                A leitura combina producao ofensiva recente, choque de estilos favoravel, risco de transicao defensiva e
                enquadramento competitivo propicio para mercados de golos.
              </p>
            </div>

            <div className="mt-8 grid gap-3 md:grid-cols-4">
              <StatPill label="Confianca" value="Alta" tone="good" />
              <StatPill label="Edge medio" value="+5.6%" tone="good" />
              <StatPill label="Risco disponibilidade" value="Medio" tone="warn" />
              <StatPill label="Contexto" value="Forte" />
            </div>
          </div>
        </CardShell>

        <CardShell id="matchup-mercados">
          <div className="p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.28em] text-white/45">Decisao rapida</p>
                <h2 className="mt-2 text-2xl font-semibold text-white">Mercados alinhados</h2>
                <p className="mt-1 text-white/55">A tab Matchup deve entregar primeiro conclusao, depois detalhe.</p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">Top 3</span>
            </div>

            <div className="mt-5 space-y-4">
              {[
                ["Over 2.5", "+7.2% edge", "78%"],
                ["BTTS", "+5.8% edge", "71%"],
                ["Over Cantos", "+4.0% edge", "63%"]
              ].map(([market, edge, score]) => (
                <article key={market} className="rounded-2xl border border-white/10 bg-black/15 p-4 transition hover:bg-black/25">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{market}</p>
                      <p className="text-sm text-white/55">{edge}</p>
                    </div>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-sm text-white">{score}</span>
                  </div>
                </article>
              ))}
              <Link
                href="/estrategia#fluxo-decisao"
                className="block w-full rounded-full bg-white px-4 py-2 text-center text-sm font-medium text-slate-950 transition hover:bg-white/90"
              >
                Ir para Estrategia
              </Link>
            </div>
          </div>
        </CardShell>
      </section>

      <section className="grid gap-6 lg:grid-cols-[0.22fr_0.78fr]">
        <CardShell className="sticky top-28 h-fit p-4">
          <nav className="space-y-2">
            {SIDE_NAV.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className={`block rounded-2xl px-4 py-3 text-sm transition ${
                  active === section.id ? "bg-white text-slate-950" : "bg-white/5 text-white/75 hover:bg-white/10"
                }`}
              >
                {section.label}
              </a>
            ))}
          </nav>
        </CardShell>

        <div className="space-y-8">
          <section id="matchup-base" className="scroll-mt-28 space-y-5">
            <SectionHeader
              eyebrow="Camada 1"
              title="Leitura Base"
              description="Primeiro o retrato estatistico do confronto. Esta camada deve responder rapido ao que o jogo tende a ser."
              action={<span className="rounded-full bg-white/10 px-3 py-1 text-sm text-white">Nucleo da decisao</span>}
            />

            <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
              <CardShell>
                <div className="p-6">
                  <h3 className="text-xl font-semibold text-white">Confronto Casa vs Fora</h3>
                  <p className="mt-1 text-white/55">Overview imediato da forca relativa em contexto.</p>
                  <div className="mt-5 grid gap-3 sm:grid-cols-2">
                    <StatPill label="Golos / jogo" value="2.0 vs 1.5" />
                    <StatPill label="BTTS" value="62% vs 57%" />
                    <StatPill label="Cantos" value="6.4 vs 5.8" />
                    <StatPill label="Forma" value="Casa" tone="good" />
                  </div>
                  <p className="mt-4 rounded-2xl border border-white/10 bg-black/15 p-4 text-sm leading-6 text-white/65">
                    Em vez de uma tabela seca no topo, esta area sintetiza logo onde esta a vantagem estrutural do confronto.
                  </p>
                </div>
              </CardShell>

              <CardShell>
                <div className="p-6">
                  <h3 className="text-xl font-semibold text-white">Radar + Comparador</h3>
                  <p className="mt-1 text-white/55">Juntar estes dois blocos reduz friccao e melhora leitura visual.</p>
                  <div className="mt-5 grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
                    <div className="rounded-[1.5rem] border border-white/10 bg-black/15 p-5">
                      <p className="mb-4 text-sm font-medium text-white">Radar de Forcas e Fraquezas</p>
                      <div className="aspect-square rounded-full border border-dashed border-white/15 bg-[radial-gradient(circle,rgba(255,255,255,0.06),transparent_60%)]" />
                    </div>
                    <div className="space-y-3">
                      {[
                        ["Ataque", "Casa +0.24"],
                        ["Transicao", "Fora -0.18"],
                        ["Cantos", "Casa +0.12"],
                        ["BTTS", "Equilibrado"]
                      ].map(([metric, delta]) => (
                        <article key={metric} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                          <div className="flex items-center justify-between gap-3 text-sm">
                            <span className="text-white/75">{metric}</span>
                            <span className="font-medium text-white">{delta}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                </div>
              </CardShell>
            </div>

            <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
              <CardShell>
                <div className="p-6">
                  <h3 className="text-xl font-semibold text-white">Mercados Convergentes</h3>
                  <p className="mt-1 text-white/55">Este bloco deve ser mais visual e menos tabelar.</p>
                  <div className="mt-5 space-y-3">
                    {[
                      ["Over 2.5", "Casa +6.8%", "Fora +4.4%", "Media +5.6%"],
                      ["BTTS", "Casa +6.0%", "Fora +3.8%", "Media +4.9%"],
                      ["Over Cantos", "Casa +4.4%", "Fora +3.2%", "Media +3.8%"]
                    ].map(([market, home, away, avg]) => (
                      <article key={market} className="rounded-2xl border border-white/10 bg-black/15 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-medium text-white">{market}</p>
                          <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm text-emerald-200">{avg}</span>
                        </div>
                        <div className="mt-3 grid gap-2 text-sm text-white/60 sm:grid-cols-2">
                          <div>{home}</div>
                          <div>{away}</div>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              </CardShell>

              <CardShell>
                <div className="p-6">
                  <h3 className="text-xl font-semibold text-white">Insights + H2H</h3>
                  <p className="mt-1 text-white/55">Sintese editorial acima; historico direto como contexto secundario.</p>
                  <div className="mt-5 space-y-4">
                    <MiniInsight
                      title="Insight principal"
                      text="A combinacao entre forma ofensiva, ritmo e mismatch defensivo favorece mercados de golos acima da media da liga."
                    />
                    <MiniInsight
                      title="Risco principal"
                      text="Risco medio de alteracao do cenario se houver ausencia confirmada no ultimo terco ofensivo antes do jogo."
                    />
                    <article className="rounded-2xl border border-white/10 bg-black/15 p-4">
                      <p className="text-sm font-medium text-white">Historico Direto</p>
                      <p className="mt-2 text-sm leading-6 text-white/60">
                        Mostrar so 3 a 5 jogos em formato compacto, para nao distrair da leitura principal.
                      </p>
                    </article>
                  </div>
                </div>
              </CardShell>
            </div>
          </section>

          <section id="matchup-contexto" className="scroll-mt-28 space-y-5">
            <SectionHeader
              eyebrow="Camada 2"
              title="Contexto Avancado"
              description="Depois da leitura base, entram os fatores que podem confirmar ou alterar o cenario."
              action={<span className="rounded-full bg-amber-400/15 px-3 py-1 text-sm text-amber-200">Validacao contextual</span>}
            />

            <div className="grid gap-4 xl:grid-cols-3">
              {[
                ["Camada de Processo", "xG/xGA proxy para qualidade real de criacao e concessao."],
                ["Style Mismatch", "Leitura do choque de estilos e encaixe tatico."],
                ["Disponibilidade", "Lesionados, duvidas, castigados e XI provavel."],
                ["Fadiga e rotacao", "Calendario, viagens, rotacao e carga recente."],
                ["Bolas paradas", "Set pieces, cantos, cartoes e vantagens de detalhe."],
                ["Condicoes externas", "Espaco ideal para arbitro, weather e relvado."]
              ].map(([title, text]) => (
                <CardShell key={title} className="bg-black/10">
                  <div className="p-5">
                    <p className="text-sm font-medium text-white">{title}</p>
                    <p className="mt-2 text-sm leading-6 text-white/55">{text}</p>
                  </div>
                </CardShell>
              ))}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}
