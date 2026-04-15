export type MatchupData = {
  homeTeam: string;
  awayTeam: string;
  summary: string;
  confidence: string;
  avgEdge: string;
  availabilityRisk: string;
  contextStrength: string;
  markets: Array<{ market: string; edge: string; score: number }>;
  overview: Array<{ label: string; value: string }>;
  comparator: Array<{ metric: string; delta: string }>;
  convergingMarkets: Array<{ market: string; home: string; away: string; avg: string }>;
  insights: Array<{ title: string; text: string }>;
  advancedContext: Array<{ title: string; text: string }>;
};

export async function getMatchupData(): Promise<MatchupData> {
  return {
    homeTeam: "Benfica",
    awayTeam: "Braga",
    summary: "Convergencia ofensiva, espaco para golos e contexto que reforca o sinal base do matchup.",
    confidence: "Alta",
    avgEdge: "+5.6%",
    availabilityRisk: "Medio",
    contextStrength: "Forte",
    markets: [
      { market: "Over 2.5", edge: "+7.2%", score: 78 },
      { market: "BTTS", edge: "+5.8%", score: 71 },
      { market: "Over Cantos", edge: "+4.0%", score: 63 }
    ],
    overview: [
      { label: "Golos por jogo", value: "2.0 vs 1.5" },
      { label: "BTTS", value: "62% vs 57%" },
      { label: "Cantos", value: "6.4 vs 5.8" },
      { label: "Forma", value: "Casa" }
    ],
    comparator: [
      { metric: "Ataque", delta: "Casa +0.24" },
      { metric: "Transicao", delta: "Fora -0.18" },
      { metric: "Cantos", delta: "Casa +0.12" },
      { metric: "BTTS", delta: "Equilibrado" }
    ],
    convergingMarkets: [
      { market: "Over 2.5", home: "Casa +6.8%", away: "Fora +4.4%", avg: "Media +5.6%" },
      { market: "BTTS", home: "Casa +6.0%", away: "Fora +3.8%", avg: "Media +4.9%" },
      { market: "Over Cantos", home: "Casa +4.4%", away: "Fora +3.2%", avg: "Media +3.8%" }
    ],
    insights: [
      {
        title: "Insight principal",
        text: "Combinacao de forma ofensiva, ritmo e mismatch defensivo favorece mercados de golos acima da media."
      },
      {
        title: "Risco principal",
        text: "Risco medio de mudanca do cenario se houver ausencia confirmada no ultimo terco ofensivo."
      }
    ],
    advancedContext: [
      { title: "Camada de Processo", text: "xG/xGA proxy para qualidade real de criacao e concessao." },
      { title: "Style Mismatch", text: "Leitura do choque de estilos e encaixe tatico." },
      { title: "Disponibilidade", text: "Lesionados, duvidas, castigados e XI provavel." },
      { title: "Fadiga e rotacao", text: "Calendario, viagens, rotacao e carga recente." },
      { title: "Bolas paradas", text: "Set pieces, cantos, cartoes e vantagens de detalhe." },
      { title: "Condicoes externas", text: "Espaco para arbitro, weather e relvado." }
    ]
  };
}
