"use client";

import { useEffect, useState } from "react";

const items = [
  { id: "resumo", label: "Resumo" },
  { id: "base-read", label: "Leitura Base" },
  { id: "advanced-context", label: "Contexto" },
  { id: "mercados", label: "Mercados" }
];

export function MatchupSectionsNav() {
  const [activeId, setActiveId] = useState("resumo");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]?.target?.id) {
          setActiveId(visible[0].target.id);
        }
      },
      {
        root: null,
        rootMargin: "-20% 0px -55% 0px",
        threshold: [0.1, 0.25, 0.5]
      }
    );

    items.forEach((item) => {
      const el = document.getElementById(item.id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  return (
    <div className="rounded-[2rem] border border-white/10 bg-white/5 p-4 shadow-2xl shadow-black/20">
      <div className="space-y-2">
        {items.map((item) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            className={`block rounded-2xl px-4 py-3 text-sm transition ${
              activeId === item.id ? "bg-white text-slate-950" : "bg-white/5 text-white/75 hover:bg-white/10"
            }`}
          >
            {item.label}
          </a>
        ))}
      </div>
    </div>
  );
}
