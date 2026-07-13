import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate, daysUntil } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { downloadCsv } from "@/components/ExportButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Wallet,
  ArrowDownRight,
  ArrowUpRight,
  Landmark,
  AlertCircle,
  FileDown,
} from "lucide-react";
import { toast } from "sonner";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const PIE_COLORS = ["#0F172A", "#166534", "#2563EB", "#CA8A04", "#991B1B", "#7C3AED", "#0891B2", "#DB2777"];

const Kpi = ({ label, value, sub, icon: Icon, tone = "default", testid }) => {
  const tones = {
    default: "bg-white text-slate-900 border-slate-200",
    green: "bg-white text-slate-900 border-slate-200",
    red: "bg-white text-slate-900 border-slate-200",
  };
  const iconTone = {
    default: "text-slate-600 bg-slate-100",
    green: "text-emerald-800 bg-emerald-100",
    red: "text-red-800 bg-red-100",
    blue: "text-blue-800 bg-blue-100",
  };
  return (
    <div className={`border rounded-md p-6 transition-all hover:-translate-y-px hover:shadow-sm ${tones[tone] || tones.default}`} data-testid={testid}>
      <div className="flex items-start justify-between">
        <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">{label}</p>
        <div className={`h-8 w-8 rounded-md flex items-center justify-center ${iconTone[tone] || iconTone.default}`}>
          <Icon className="h-4 w-4" strokeWidth={1.75} />
        </div>
      </div>
      <p className="mt-4 font-heading text-2xl sm:text-3xl font-bold tracking-tight tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
};

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [range, setRange] = useState({ startDate: "", endDate: "" });
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    (async () => {
      const { data } = await api.get("/dashboard/summary");
      setData(data);
    })();
  }, []);

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const params = new URLSearchParams();
      if (range.startDate) params.set("start_date", range.startDate);
      if (range.endDate) params.set("end_date", range.endDate);
      const qs = params.toString();
      const filename = `nakit-akis-raporu-${range.startDate || "bu-ay"}-${range.endDate || "simdi"}.pdf`;
      await downloadCsv(`/reports/pdf${qs ? "?" + qs : ""}`, filename);
      toast.success("PDF raporu indirildi");
    } catch {
      toast.error("PDF indirilemedi");
    } finally {
      setDownloading(false);
    }
  };

  if (!data) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-32 rounded-md border border-slate-200 bg-white animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div data-testid="dashboard-page">
      <PageHeader
        label="Genel Bakış"
        title="Nakit Akış Kontrol Paneli"
        description="Tüm hesap, çek, senet ve yaklaşan ödemelerinizin özet görünümü."
        testid="dashboard-header"
        actions={
          <Button
            onClick={downloadPdf}
            disabled={downloading}
            data-testid="download-pdf-btn"
            className="bg-slate-900 hover:bg-slate-800 text-white"
          >
            <FileDown className="h-4 w-4 mr-2" strokeWidth={1.75} />
            {downloading ? "Hazırlanıyor..." : "PDF Rapor"}
          </Button>
        }
      />

      <DateRangeFilter
        startDate={range.startDate}
        endDate={range.endDate}
        onChange={setRange}
        testidPrefix="dashboard-date"
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Kpi label="Toplam Bakiye" value={formatTRY(data.total_balance)} sub={`${data.accounts_count} hesap`} icon={Wallet} testid="kpi-total-balance" />
        <Kpi label="Gelen (30 gün)" value={formatTRY(data.upcoming_incoming)} sub="Alacaklar" icon={ArrowDownRight} tone="green" testid="kpi-upcoming-in" />
        <Kpi label="Giden (30 gün)" value={formatTRY(data.upcoming_outgoing)} sub="Borçlar" icon={ArrowUpRight} tone="red" testid="kpi-upcoming-out" />
        <Kpi label="Bu Ay Net" value={formatTRY((data.month_income || 0) - (data.month_expense || 0))} sub={`Gelir ${formatTRY(data.month_income)} / Gider ${formatTRY(data.month_expense)}`} icon={Landmark} tone="blue" testid="kpi-month-net" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
        <Card className="lg:col-span-2 border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Aylık Nakit Akışı</p>
                <h3 className="font-heading text-lg font-semibold mt-1">Son 6 Ay - Gelir & Gider</h3>
              </div>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.monthly} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#E2E8F0" vertical={false} />
                  <XAxis dataKey="month" stroke="#64748B" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748B" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ borderRadius: 6, border: "1px solid #E2E8F0", fontSize: 12 }}
                    formatter={(v) => formatTRY(v)}
                  />
                  <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="gelir" name="Gelir" fill="#166534" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="gider" name="Gider" fill="#991B1B" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Gider Kategorileri</p>
            <h3 className="font-heading text-lg font-semibold mt-1">Bu Ay Dağılım</h3>
            <div className="h-56 mt-4">
              {data.categories.length === 0 ? (
                <div className="h-full flex items-center justify-center text-sm text-slate-500">Bu ay gider yok</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={data.categories} dataKey="value" nameKey="name" outerRadius={80} innerRadius={45}>
                      {data.categories.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => formatTRY(v)} contentStyle={{ borderRadius: 6, border: "1px solid #E2E8F0", fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="mt-3 space-y-1.5">
              {data.categories.slice(0, 5).map((c, i) => (
                <div key={c.name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                    <span className="text-slate-700">{c.name}</span>
                  </div>
                  <span className="tabular-nums font-medium text-slate-900">{formatTRY(c.value)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Yaklaşan Ödemeler</p>
              <h3 className="font-heading text-lg font-semibold mt-1">Sonraki 30 gün</h3>
            </div>
          </div>
          {data.upcoming.length === 0 ? (
            <div className="border border-dashed border-slate-300 rounded-md p-8 text-center text-sm text-slate-500">
              Yaklaşan 30 gün içinde ödeme bulunmuyor.
            </div>
          ) : (
            <div className="divide-y divide-slate-200">
              {data.upcoming.map((u) => {
                const days = daysUntil(u.due_date);
                const isOut = u.type === "issued";
                return (
                  <div key={u.id} className="flex items-center justify-between py-3 gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`h-8 w-8 rounded-md flex items-center justify-center ${isOut ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}>
                        {isOut ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold truncate">{u.party}</p>
                        <p className="text-xs text-slate-500">
                          {u.kind === "check" ? "Çek" : "Senet"} · {formatDate(u.due_date)}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-semibold tabular-nums ${isOut ? "text-red-800" : "text-emerald-800"}`}>
                        {isOut ? "-" : "+"}
                        {formatTRY(u.amount)}
                      </p>
                      <p className={`text-xs mt-0.5 flex items-center justify-end gap-1 ${days <= 3 ? "text-amber-700" : "text-slate-500"}`}>
                        {days <= 3 && <AlertCircle className="h-3 w-3" />}
                        {days === 0 ? "Bugün" : days === 1 ? "Yarın" : `${days} gün kaldı`}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
