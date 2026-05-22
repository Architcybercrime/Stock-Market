import clsx from "clsx";

export function Panel({
  title,
  subtitle,
  className,
  children,
}: {
  title: string;
  subtitle?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={clsx("rounded-lg border border-border bg-panel p-5", className)}>
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-wider text-muted">{title}</h2>
        {subtitle && <span className="text-xs text-muted">{subtitle}</span>}
      </header>
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "neutral";
}) {
  const toneClass =
    tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : "text-text";
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className={clsx("mt-1 text-2xl font-semibold", toneClass)}>{value}</div>
    </div>
  );
}
