import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { ExportButton } from "@/components/ExportButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const empty = { source: "", description: "", amount: 0, date: new Date().toISOString().slice(0, 10) };

export default function Incomes() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);

  const load = async () => { const { data } = await api.get("/incomes"); setItems(data); };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.source || !form.amount) return toast.error("Zorunlu alanları doldurun");
    const payload = { ...form, amount: Number(form.amount) };
    if (editing) { await api.put(`/incomes/${editing.id}`, payload); toast.success("Gelir güncellendi"); }
    else { await api.post("/incomes", payload); toast.success("Gelir eklendi"); }
    setOpen(false); setEditing(null); setForm(empty); load();
  };
  const remove = async (id) => { await api.delete(`/incomes/${id}`); toast.success("Silindi"); load(); };
  const openEdit = (row) => { setEditing(row); setForm(row); setOpen(true); };

  const total = items.reduce((s, i) => s + i.amount, 0);

  return (
    <div data-testid="incomes-page">
      <PageHeader
        label="Gelirler"
        title="Gelir Takibi"
        description="Satış, tahsilat ve diğer gelir kayıtlarınız."
        actions={
          <>
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
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Tutar (₺)</Label><Input data-testid="income-amount-input" type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                    <div><Label>Tarih</Label><Input data-testid="income-date-input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></div>
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

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Kaynak</TableHead>
                <TableHead>Açıklama</TableHead>
                <TableHead>Tarih</TableHead>
                <TableHead className="text-right">Tutar</TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-12 text-slate-500">Henüz gelir eklenmedi.</TableCell></TableRow>
              ) : items.map((i) => (
                <TableRow key={i.id} data-testid={`income-row-${i.id}`}>
                  <TableCell className="font-medium">{i.source}</TableCell>
                  <TableCell className="text-slate-600">{i.description || "-"}</TableCell>
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
