type AdvancedItem = { title: string; text: string };

export function AdvancedContextSection({ items }: { items: AdvancedItem[] }) {
  return (
    <section id="advanced-context" className="scroll-mt-28 space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-[0.3em] text-white/45">Camada 2</div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white md:text-3xl">Contexto Avancado</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60 md:text-base">
          Depois da leitura base, entram os fatores que podem confirmar ou alterar o cenario.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {items.map((item) => (
          <div key={item.title} className="rounded-[2rem] border border-white/10 bg-white/5 p-5 shadow-2xl shadow-black/20">
            <div className="text-sm font-medium text-white">{item.title}</div>
            <div className="mt-2 text-sm leading-6 text-white/55">{item.text}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
