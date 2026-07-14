import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { ExportButton } from "@/components/ExportButton";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import ImportDialog from "@/components/ImportDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const empty = { source: "", description: "", amount: 0, vat_rate: 20, date: new Date().toISOString().slice(0, 10), bank_account_id: null };
const VAT_RATES = [0, 1, 10, 20];
const NONE_ACCOUNT = "__none__";

export default function Incomes() {
  const [items, setItems] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [range, setRange] = useState({ startDate: "", endDate: "" });

  const load = async () => {
    const params = {};
    if (range.startDate) params.start_date = range.startDate;
    if (range.endDate) params.end_date = range.endDate;
    const [{ data }, { data: accts }] = await Promise.all([
      api.get("/incomes", { params }),
      api.get("/bank-accounts"),
    ]);
    setItems(data);
    setAccounts(accts);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [range.startDate, range.endDate]);

  const submit = async () => {
    if (!form.source || !form.amount) return toast.error("Zorunlu alanları doldurun");
    const payload = { ...form, amount: Number(form.amount), bank_account_id: form.bank_account_id || null };
    if (editing) { await api.put(`/incomes/${editing.id}`, payload); toast.success("Gelir güncellendi, banka bakiyesi işlendi"); }
    else { await api.post("/incomes", payload); toast.success("Gelir eklendi, banka bakiyesi güncellendi"); }
    setOpen(false); setEditing(null); setForm(empty); load();
  };
  const remove = async (id) => { await api.delete(`/incomes/${id}`); toast.success("Silindi, bakiye iade edildi"); load(); };
  const openEdit = (row) => { setEditing(row); setForm({ ...empty, ...row, bank_account_id: row.bank_account_id || null }); setOpen(true); };

  const accountName = (id) => accounts.find((a) => a.id === id)?.name || "-";

  const total = items.reduce((s, i) => s + i.amount, 0);

  return (
    <div data-testid="incomes-page">
      <PageHeader
        label="Gelirler"
        title="Gelir Takibi"
        description="Satış, tahsilat ve diğer gelir kayıtlarınız."
        actions={
          <>
            <ImportDialog resource="incomes" label="Gelir İçe Aktar" onImported={load} testidPrefix="incomes-import" />
            <ExportButton path="/export/incomes" filename="gelirler.csv" testid="export-incomes-btn" />
            <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(empty); } }}>
              <DialogTrigger asChild>
                <Button data-testid="add-income-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
                  <Plus className="h-4 w-4 mr-2" /> Gelir Ekle
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>{editing ? "Gelir Düzenle" : "Yeni Gelir"}</DialogTitle></DialogHeader>
                <div className="grid gap-3 py-2">
                  <div><Label>Kaynak</Label><Input data-testid="income-source-input" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="Örn: Satış, Tahsilat" /></div>
                  <div><Label>Açıklama</Label><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
                  <div className="grid grid-cols-3 gap-3">
                    <div><Label>Tutar (₺)</Label><Input data-testid="income-amount-input" type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                    <div>
                      <Label>KDV %</Label>
                      <Select value={String(form.vat_rate)} onValueChange={(v) => setForm({ ...form, vat_rate: Number(v) })}>
                        <SelectTrigger data-testid="income-vat-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {VAT_RATES.map((r) => <SelectItem key={r} value={String(r)}>{r === 0 ? "KDV'siz" : `%${r}`}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div><Label>Tarih</Label><Input data-testid="income-date-input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></div>
                  </div>
                  <div>
                    <Label>Banka Hesabı (opsiyonel)</Label>
                    <Select
                      value={form.bank_account_id || NONE_ACCOUNT}
                      onValueChange={(v) => setForm({ ...form, bank_account_id: v === NONE_ACCOUNT ? null : v })}
                    >
                      <SelectTrigger data-testid="income-bank-account-select"><SelectValue placeholder="Nakit / Hesap seçmedim" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE_ACCOUNT}>Nakit / Hesap seçmedim</SelectItem>
                        {accounts.map((a) => (
                          <SelectItem key={a.id} value={a.id}>{a.name} — {a.bank_name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-slate-500 mt-1">Seçerseniz tutar bu hesabın bakiyesine otomatik eklenir.</p>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>İptal</Button>
                  <Button data-testid="save-income-btn" onClick={submit} className="bg-slate-900 hover:bg-slate-800 text-white">Kaydet</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <Card className="border-slate-200 rounded-md shadow-none mb-6">
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Toplam Gelir</p>
          <p className="mt-2 font-heading text-3xl font-bold text-emerald-800 tabular-nums" data-testid="total-income">{formatTRY(total)}</p>
          <p className="text-xs text-slate-500 mt-1">{items.length} kayıt</p>
        </CardContent>
      </Card>

      <DateRangeFilter
        startDate={range.startDate}
        endDate={range.endDate}
        onChange={setRange}
        testidPrefix="incomes-date"
      />

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Kaynak</TableHead>
                <TableHead>Açıklama</TableHead>
                <TableHead>Banka Hesabı</TableHead>
                <TableHead>Tarih</TableHead>
                <TableHead className="text-right">Tutar</TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-12 text-slate-500">Henüz gelir eklenmedi.</TableCell></TableRow>
              ) : items.map((i) => (
                <TableRow key={i.id} data-testid={`income-row-${i.id}`}>
                  <TableCell className="font-medium">{i.source}</TableCell>
                  <TableCell className="text-slate-600">{i.description || "-"}</TableCell>
                  <TableCell className="text-slate-600 text-sm">{i.bank_account_id ? accountName(i.bank_account_id) : <span className="text-slate-400">Nakit</span>}</TableCell>
                  <TableCell className="text-slate-600 text-sm">{formatDate(i.date)}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold text-emerald-800">{formatTRY(i.amount)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button size="icon" variant="ghost" onClick={() => openEdit(i)}><Pencil className="h-4 w-4" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => remove(i.id)}><Trash2 className="h-4 w-4 text-red-600" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
