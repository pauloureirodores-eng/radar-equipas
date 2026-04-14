type PageIntroProps = {
  title: string;
  description: string;
};

export function PageIntro({ title, description }: PageIntroProps) {
  return (
    <section className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20">
      <h1 className="text-3xl font-semibold tracking-tight text-white">{title}</h1>
      <p className="mt-2 max-w-3xl text-white/65">{description}</p>
    </section>
  );
}
