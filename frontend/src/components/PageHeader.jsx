export const PageHeader = ({ label, title, description, actions, testid }) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8" data-testid={testid}>
      <div>
        {label && (
          <p className="text-xs uppercase tracking-[0.15em] font-semibold text-slate-500">{label}</p>
        )}
        <h1 className="mt-2 font-heading text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-sm sm:text-base text-slate-600 leading-relaxed max-w-2xl">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
};
