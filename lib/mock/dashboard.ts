export const dashboardKpis = [
  { label: "Oportunidades activas", value: "12", sub: "+3 vs ontem" },
  { label: "Alertas criticos", value: "4", sub: "2 por disponibilidade" },
  { label: "Matchups premium", value: "6", sub: "alta convergencia" },
  { label: "Confianca media", value: "78%", sub: "scanner curado" }
];

export const weeklyAlerts = [
  "Movimento forte nas odds do Over 2.5 em Benfica vs Braga",
  "Duvida no ponta-de-lanca titular do Napoli",
  "Equipa visitante com 3.o jogo em 8 dias"
];

export const featuredMarkets = [
  { market: "Over 2.5", game: "Benfica vs Braga", edge: "+7.2%" },
  { market: "BTTS", game: "Atalanta vs Napoli", edge: "+5.8%" },
  { market: "Casa DNB", game: "Lille vs Rennes", edge: "+4.6%" }
];

export const topOpportunities = [
  {
    market: "Over 2.5",
    game: "Benfica vs Braga",
    edge: "+7.2%",
    confidence: "Alta",
    note: "Ritmo alto + processo ofensivo"
  },
  {
    market: "BTTS",
    game: "Atalanta vs Napoli",
    edge: "+5.8%",
    confidence: "Alta",
    note: "Mismatch defensivo dos dois lados"
  },
  {
    market: "Casa DNB",
    game: "Lille vs Rennes",
    edge: "+4.6%",
    confidence: "Media",
    note: "Contexto competitivo favoravel"
  },
  {
    market: "Over Cantos",
    game: "Leeds vs Norwich",
    edge: "+4.1%",
    confidence: "Media",
    note: "Perfil de cruzamento e volume"
  }
];

export const scannerSummaryRows = [
  { team: "Benfica", league: "POR1", market: "Over 2.5", edge: "+7.2%", status: "Forte" },
  { team: "Atalanta", league: "ITA1", market: "BTTS", edge: "+5.8%", status: "Forte" },
  { team: "Lille", league: "FRA1", market: "Casa DNB", edge: "+4.6%", status: "Boa" },
  { team: "Leeds", league: "ENG2", market: "Over Cantos", edge: "+4.1%", status: "Boa" }
];

export const compactWatchlist = ["Sporting", "Brighton", "Bologna", "Feyenoord", "Leverkusen"];
