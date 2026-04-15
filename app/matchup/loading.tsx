export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="h-56 animate-pulse rounded-[2rem] border border-white/10 bg-white/5" />
      <div className="grid gap-6 lg:grid-cols-[0.22fr_0.78fr]">
        <div className="h-52 animate-pulse rounded-[2rem] border border-white/10 bg-white/5" />
        <div className="space-y-6">
          <div className="h-72 animate-pulse rounded-[2rem] border border-white/10 bg-white/5" />
          <div className="h-72 animate-pulse rounded-[2rem] border border-white/10 bg-white/5" />
        </div>
      </div>
    </div>
  );
}
