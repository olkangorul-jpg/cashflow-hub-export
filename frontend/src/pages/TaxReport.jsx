import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { downloadCsv } from "@/components/ExportButton";
import { FileDown, FileSpreadsheet, TrendingUp, TrendingDown, Scale } from "lucide-react";
import { toast } from "sonner";

const monthOptions = () => {
  const opts = [];
  const now = new Date();
  for (let i = 0; i < 24; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const label = d.toLocaleDateString("tr-TR", { year: "numeric", month: "long" });
    opts.push({ value: `${y}-${m}`, label });
  }
  return opts;
};

const quarterOptions = () => {
  const opts = [];
  const now = new Date();
  let y = now.getFullYear();
  let q = Math.floor(now.getMonth() / 3) + 1;
  for (let i = 0; i < 8; i++) {
    opts.push({ value: `${y}-Q${q}`, label: `${y} - ${q}. Çeyrek` });
    q -= 1;
    if (q < 1) { q = 4; y -= 1; }
  }
  return opts;
};

export default function TaxReport() {
  const [mode, setMode] = useState("month");
  const [period, setPeriod] = useState(monthOptions()[0].value);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (mode === "custom") {
        if (start) params.start_date = start;
        if (end) params.end_date = end;
      } else {
        params.period = period;
      }
      const { data } = await api.get("/reports/tax", { params });
      setData(data);
    } catch {
      toast.error("Rapor yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [mode, period]);

  const setPresetFromMode = (v) => {
    setMode(v);
    if (v === "month") setPeriod(monthOptions()[0].value);
    else if (v === "quarter") setPeriod(quarterOptions()[0].value);
  };

  const download = async (format) => {
    setDownloading(true);
    try {
      const params = new URLSearchParams();
      if (mode === "custom") {
        if (start) params.set("start_date", start);
        if (end) params.set("end_date", end);
      } else {
        params.set("period", period);
      }
      const ext = format === "pdf" ? "pdf" : "xlsx";
      await downloadCsv(`/reports/tax/${format}?${params.toString()}`, `kdv-raporu.${ext}`);
      toast.success("İndirildi");
    } catch {
      toast.error("İndirilemedi");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div data-testid="tax-report-page">
      <PageHeader
        label="Vergi"
        title="KDV Beyan Özeti"
        description="Aylık veya çeyreklik KDV özetinizi görüntüleyin ve indirin. Tutarlar KDV Dahil brüt kabul edilir."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => download("xlsx")}
              disabled={downloading}
              data-testid="tax-xlsx-btn"
              className="border-slate-300 text-slate-700 hover:bg-slate-50"
            >
              <FileSpreadsheet className="h-4 w-4 mr-2" /> Excel
            </Button>
            <Button
              onClick={() => download("pdf")}
              disabled={downloading}
              data-testid="tax-pdf-btn"
              className="bg-slate-900 hover:bg-slate-800 text-white"
            >
              <FileDown className="h-4 w-4 mr-2" /> PDF
            </Button>
          </>
        }
      />

      {/* Period selector */}
      <Card className="border-slate-200 rounded-md shadow-none mb-6">
        <CardContent className="p-4 flex flex-wrap items-end gap-3">
          <div>
            <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Dönem Türü</Label>
            <Select value={mode} onValueChange={setPresetFromMode}>
              <SelectTrigger className="w-40 mt-1" data-testid="tax-mode-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="month">Aylık</SelectItem>
                <SelectItem value="quarter">Çeyreklik</SelectItem>
                <SelectItem value="custom">Özel</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {mode === "month" && (
            <div>
              <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Ay</Label>
              <Select value={period} onValueChange={setPeriod}>
                <SelectTrigger className="w-56 mt-1" data-testid="tax-month-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {monthOptions().map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          {mode === "quarter" && (
            <div>
              <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Çeyrek</Label>
              <Select value={period} onValueChange={setPeriod}>
                <SelectTrigger className="w-56 mt-1" data-testid="tax-quarter-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {quarterOptions().map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          {mode === "custom" && (
            <>
              <div>
                <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Başlangıç</Label>
                <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-40 mt-1" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Bitiş</Label>
                <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-40 mt-1" />
              </div>
              <Button onClick={load} className="bg-slate-900 hover:bg-slate-800 text-white">Uygula</Button>
            </>
          )}
        </CardContent>
      </Card>

      {loading || !data ? (
        <div className="h-40 rounded-md border border-slate-200 bg-white animate-pulse" />
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card className="border-slate-200 rounded-md shadow-none">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Hesaplanan KDV</p>
                  <TrendingUp className="h-4 w-4 text-emerald-700" strokeWidth={1.75} />
                </div>
                <p className="font-heading text-2xl font-bold text-emerald-800 tabular-nums" data-testid="calc-vat">{formatTRY(data.income.total_vat)}</p>
                <p className="text-xs text-slate-500 mt-1">Gelir brüt: {formatTRY(data.income.total_gross)}</p>
              </CardContent>
            </Card>
            <Card className="border-slate-200 rounded-md shadow-none">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">İndirilecek KDV</p>
                  <TrendingDown className="h-4 w-4 text-red-700" strokeWidth={1.75} />
                </div>
                <p className="font-heading text-2xl font-bold text-red-800 tabular-nums" data-testid="deductible-vat">{formatTRY(data.expense.total_vat)}</p>
                <p className="text-xs text-slate-500 mt-1">Gider brüt: {formatTRY(data.expense.total_gross)}</p>
              </CardContent>
            </Card>
            <Card className={`border-2 rounded-md shadow-none ${data.vat_status === "pay" ? "border-red-300 bg-red-50/40" : data.vat_status === "refund" ? "border-emerald-300 bg-emerald-50/40" : "border-slate-300"}`}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-700">
                    {data.vat_status === "pay" ? "Ödenecek KDV" : data.vat_status === "refund" ? "İade Alınacak KDV" : "Denk"}
                  </p>
                  <Scale className="h-4 w-4 text-slate-700" strokeWidth={1.75} />
                </div>
                <p className={`font-heading text-3xl font-bold tabular-nums ${data.vat_status === "pay" ? "text-red-800" : data.vat_status === "refund" ? "text-emerald-800" : "text-slate-900"}`} data-testid="payable-vat">
                  {formatTRY(Math.abs(data.payable_vat))}
                </p>
                <p className="text-xs text-slate-600 mt-1">{data.start_date} — {data.end_date}</p>
              </CardContent>
            </Card>
          </div>

          {/* Breakdown tables */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="border-slate-200 rounded-md shadow-none">
              <CardContent className="p-0">
                <div className="px-6 py-4 border-b border-slate-200">
                  <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Gelir</p>
                  <p className="font-heading text-lg font-semibold mt-0.5">KDV Kırılımı</p>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Oran</TableHead>
                      <TableHead className="text-right">Matrah</TableHead>
                      <TableHead className="text-right">KDV</TableHead>
                      <TableHead className="text-right">Brüt</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.income.breakdown.length === 0 ? (
                      <TableRow><TableCell colSpan={4} className="text-center py-8 text-slate-500">Bu dönemde gelir yok</TableCell></TableRow>
                    ) : data.income.breakdown.map((b) => (
                      <TableRow key={b.rate}>
                        <TableCell><Badge variant="outline" className="bg-slate-50">%{b.rate}</Badge></TableCell>
                        <TableCell className="text-right tabular-nums">{formatTRY(b.net)}</TableCell>
                        <TableCell className="text-right tabular-nums font-semibold text-emerald-800">{formatTRY(b.vat)}</TableCell>
                        <TableCell className="text-right tabular-nums font-semibold">{formatTRY(b.gross)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card className="border-slate-200 rounded-md shadow-none">
              <CardContent className="p-0">
                <div className="px-6 py-4 border-b border-slate-200">
                  <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Gider</p>
                  <p className="font-heading text-lg font-semibold mt-0.5">KDV Kırılımı</p>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Oran</TableHead>
                      <TableHead className="text-right">Matrah</TableHead>
                      <TableHead className="text-right">KDV</TableHead>
                      <TableHead className="text-right">Brüt</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.expense.breakdown.length === 0 ? (
                      <TableRow><TableCell colSpan={4} className="text-center py-8 text-slate-500">Bu dönemde gider yok</TableCell></TableRow>
                    ) : data.expense.breakdown.map((b) => (
                      <TableRow key={b.rate}>
                        <TableCell><Badge variant="outline" className="bg-slate-50">%{b.rate}</Badge></TableCell>
                        <TableCell className="text-right tabular-nums">{formatTRY(b.net)}</TableCell>
                        <TableCell className="text-right tabular-nums font-semibold text-red-800">{formatTRY(b.vat)}</TableCell>
                        <TableCell className="text-right tabular-nums font-semibold">{formatTRY(b.gross)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <p className="mt-4 text-xs text-slate-500 italic">
            Not: Tutarlar KDV dahil (brüt) kabul edilmiştir. Bu rapor bilgi amaçlıdır ve resmi beyan yerine geçmez.
          </p>
        </>
      )}
    </div>
  );
}
