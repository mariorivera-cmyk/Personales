import { STATUS, STATUS_CLS, CO_STATUS, CO_CLS } from "@/lib/api";

export const PageHeader = ({ title, subtitle, action }) => (
  <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between fade-up">
    <div>
      <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl" data-testid="page-title">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-muted-foreground sm:text-base">{subtitle}</p>}
    </div>
    {action && <div className="flex flex-wrap gap-2">{action}</div>}
  </div>
);

export const Kpi = ({ label, value, hint, icon: Icon, testid, accent = "text-primary" }) => (
  <div className="rounded-2xl border bg-white p-5 transition-transform duration-200 hover:-translate-y-0.5 fade-up" data-testid={testid}>
    <div className="flex items-center justify-between">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      {Icon && <Icon className={`h-4 w-4 ${accent}`} />}
    </div>
    <div className="mt-2 font-heading text-2xl font-bold tracking-tight sm:text-3xl" data-testid={`${testid}-value`}>{value}</div>
    {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
  </div>
);

export const StatusBadge = ({ status }) => (
  <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_CLS[status] || ""}`} data-testid={`status-${status}`}>
    {STATUS[status] || status}
  </span>
);

export const CompanyBadge = ({ status }) => (
  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${CO_CLS[status] || ""}`} data-testid={`company-status-${status}`}>
    {CO_STATUS[status] || status}
  </span>
);

export const Panel = ({ title, action, children, className = "", testid }) => (
  <section className={`rounded-2xl border bg-white p-6 fade-up-2 ${className}`} data-testid={testid}>
    {(title || action) && (
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 className="font-heading text-lg font-semibold">{title}</h3>
        {action}
      </div>
    )}
    {children}
  </section>
);

export const EmptyState = ({ text }) => (
  <div className="rounded-2xl border border-dashed bg-white/60 p-10 text-center text-sm text-muted-foreground" data-testid="empty-state">{text}</div>
);

export const Label = ({ children }) => <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">{children}</label>;
