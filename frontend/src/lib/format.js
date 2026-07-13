export const formatTRY = (amount) => {
  const n = Number(amount) || 0;
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: "TRY",
    maximumFractionDigits: 2,
  }).format(n);
};

export const formatNumber = (amount) => {
  const n = Number(amount) || 0;
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(n);
};

export const formatDate = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
};

export const daysUntil = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  const now = new Date();
  d.setHours(0, 0, 0, 0);
  now.setHours(0, 0, 0, 0);
  return Math.round((d - now) / (1000 * 60 * 60 * 24));
};
