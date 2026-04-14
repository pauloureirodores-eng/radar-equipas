import type { ReactNode } from "react";

export function PageShell({ children }: { children: ReactNode }) {
  return <main className="mx-auto max-w-7xl space-y-10 px-6 pb-16 md:px-8 lg:px-10">{children}</main>;
}
