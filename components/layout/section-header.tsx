import type { ReactNode } from "react";

type SectionHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
};

export function SectionHeader({ eyebrow, title, description, action }: SectionHeaderProps) {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div className="space-y-2">
        {eyebrow ? <div className="text-[11px] uppercase tracking-[0.3em] text-white/45">{eyebrow}</div> : null}
        <h2 className="text-2xl font-semibold tracking-tight text-white md:text-3xl">{title}</h2>
        {description ? <p className="max-w-3xl text-sm leading-6 text-white/60 md:text-base">{description}</p> : null}
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}
