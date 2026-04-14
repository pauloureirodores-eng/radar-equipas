import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Radar de Equipas & Mercados",
  description: "Plataforma premium de analise desportiva pre-jogo, matchup e execucao."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-PT">
      <body className="bg-[#07111f] text-white antialiased">
        <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(54,88,158,0.28),transparent_28%),radial-gradient(circle_at_82%_10%,rgba(18,152,170,0.14),transparent_22%)]">
          {children}
        </div>
      </body>
    </html>
  );
}
