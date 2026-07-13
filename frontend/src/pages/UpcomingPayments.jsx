import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate, daysUntil } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowDownRight, ArrowUpRight, AlertCircle, CheckCircle2 } from "lucide-react";

export default function UpcomingPayments() {
  const [checks, setChecks] = useState([]);
  const [notes, setNotes] = useState([]);

  useEffect(() => {
    (async () => {
      const [c, n] = await Promise.all([api.get("/checks"), api.get("/promissory-notes")]);
      setChecks(c.data); setNotes(n.data);
    })();
  }, []);

  const all = [
    ...checks.filter((c) => c.status === "pending").map((c) => ({ ...c, kind: "check" })),
    ...notes.filter((n) => n.status === "pending").map((n) => ({ ...n, kind: "note" })),
  ].sort((a, b) => a.due_date.localeCompare(b.due_date));

  // Group by month
  const groups = {};
  all.forEach((it) => {
    const key = it.due_date.slice(0, 7);
    if (!groups[key]) groups[key] = [];
    groups[key].push(it);
  });
  const sortedKeys = Object.keys(groups).sort();

  const totalIn = all.filter((i) => i.type === "received").reduce((s, i) => s + i.amount, 0);
  const totalOut = all.filter((i) => i.type === "issued").reduce((s, i) => s + i.amount, 0);

  return (
    <div data-testid="upcoming-page">
      <PageHeader
        label="Ödeme Takvimi"
        title="Yaklaşan Ödemeler"
        description="Bekleyen tüm çek ve senetler vade tarihine göre gruplu görünümde."
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Toplam Alacak</p>
            <p className="mt-2 font-heading text-2xl font-bold text-emerald-800 tabular-nums">{formatTRY(totalIn)}</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Toplam Borç</p>
            <p className="mt-2 font-heading text-2xl font-bold text-red-800 tabular-nums">{formatTRY(totalOut)}</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Net Pozisyon</p>
            <p className={`mt-2 font-heading text-2xl font-bold tabular-nums ${totalIn - totalOut >= 0 ? "text-emerald-800" : "text-red-800"}`}>
              {formatTRY(totalIn - totalOut)}
            </p>
          </CardContent>
        </Card>
      </div>

      {all.length === 0 ? (
        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-12 text-center">
            <CheckCircle2 className="h-10 w-10 text-emerald-600 mx-auto mb-3" strokeWidth={1.5} />
            <p className="font-heading font-semibold">Bekleyen ödeme yok</p>
            <p className="text-sm text-slate-500 mt-1">Şu an için takvimde bekleyen çek veya senet bulunmuyor.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {sortedKeys.map((k) => {
            const [y, m] = k.split("-");
            const tr = new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("tr-TR", { month: "long", year: "numeric" });
            const groupTotal = groups[k].reduce((s, i) => s + (i.type === "issued" ? -i.amount : i.amount), 0);
            return (
              <Card key={k} className="border-slate-200 rounded-md shadow-none">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Ay</p>
                      <h3 className="font-heading text-lg font-semibold capitalize">{tr}</h3>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-500">Net</p>
                      <p className={`font-heading text-lg font-bold tabular-nums ${groupTotal >= 0 ? "text-emerald-800" : "text-red-800"}`}>{formatTRY(groupTotal)}</p>
                    </div>
                  </div>
                  <div className="divide-y divide-slate-200">
                    {groups[k].map((it) => {
                      const days = daysUntil(it.due_date);
                      const isOut = it.type === "issued";
                      return (
                        <div key={it.id} className="flex items-center justify-between py-3 gap-4">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className={`h-9 w-9 rounded-md flex items-center justify-center ${isOut ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}>
                              {isOut ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-semibold truncate">{it.party}</p>
                              <div className="flex items-center gap-2 mt-0.5">
                                <Badge variant="outline" className="border-slate-300 text-slate-600 bg-white text-[10px] font-normal">
                                  {it.kind === "check" ? "Çek" : "Senet"}
                                </Badge>
                                <span className="text-xs text-slate-500">{formatDate(it.due_date)}</span>
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className={`text-sm font-semibold tabular-nums ${isOut ? "text-red-800" : "text-emerald-800"}`}>
                              {isOut ? "-" : "+"}{formatTRY(it.amount)}
                            </p>
                            <p className={`text-xs mt-0.5 flex items-center justify-end gap-1 ${days < 0 ? "text-red-700" : days <= 3 ? "text-amber-700" : "text-slate-500"}`}>
                              {(days < 0 || days <= 3) && <AlertCircle className="h-3 w-3" />}
                              {days < 0 ? `${Math.abs(days)} gün geçti` : days === 0 ? "Bugün" : `${days} gün kaldı`}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
