import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { ExportButton } from "@/components/ExportButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const EXPENSE_CATEGORIES = ["Kira", "Personel", "Vergi", "Elektrik", "Su", "Doğalgaz", "İnternet", "Malzeme", "Nakliye", "Pazarlama", "Yakıt", "Diğer"];
const empty = { category: "Diğer", description: "", amount: 0, date: new Date().toISOString().slice(0, 10) };

export default function Expenses() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);

  const load = async () => { const { data } = await api.get("/expenses"); setItems(data); };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.description || !form.amount) return toast.error("Zorunlu alanları doldurun");
    const payload = { ...form, amount: Number(form.amount) };
    if (editing) { await api.put(`/expenses/${editing.id}`, payload); toast.success("Gider güncellendi"); }
    else { await api.post("/expenses", payload); toast.success("Gider eklendi"); }
    setOpen(false); setEditing(null); setForm(empty); load();
  };
  const remove = async (id) => { await api.delete(`/expenses/${id}`); toast.success("Silindi"); load(); };
  const openEdit = (row) => { setEditing(row); setForm(row); setOpen(true); };

  const total = items.reduce((s, i) => s + i.amount, 0);

  return (
    <div data-testid="expenses-page">
      <PageHeader
        label="Giderler"
        title="Gider Takibi"
        description="Tüm giderlerinizi kategoriye göre kaydedin ve dışa aktarın."
        actions={
          <>
            <ExportButton path="/export/expenses" filename="giderler.csv" testid="export-expenses-btn" />
            <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(empty); } }}>
              <DialogTrigger asChild>
                <Button data-testid="add-expense-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
                  <Plus className="h-4 w-4 mr-2" /> Gider Ekle
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>{editing ? "Gider Düzenle" : "Yeni Gider"}</DialogTitle></DialogHeader>
                <div className="grid gap-3 py-2">
                  <div>
                    <Label>Kategori</Label>
                    <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                      <SelectTrigger data-testid="expense-category-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {EXPENSE_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Açıklama</Label><Input data-testid="expense-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Tutar (₺)</Label><Input data-testid="expense-amount-input" type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                    <div><Label>Tarih</Label><Input data-testid="expense-date-input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></div>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>İptal</Button>
                  <Button data-testid="save-expense-btn" onClick={submit} className="bg-slate-900 hover:bg-slate-800 text-white">Kaydet</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <Card className="border-slate-200 rounded-md shadow-none mb-6">
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Toplam Gider</p>
          <p className="mt-2 font-heading text-3xl font-bold text-red-800 tabular-nums" data-testid="total-expense">{formatTRY(total)}</p>
          <p className="text-xs text-slate-500 mt-1">{items.length} kayıt</p>
        </CardContent>
      </Card>

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Kategori</TableHead>
                <TableHead>Açıklama</TableHead>
                <TableHead>Tarih</TableHead>
                <TableHead className="text-right">Tutar</TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-12 text-slate-500">Henüz gider eklenmedi.</TableCell></TableRow>
              ) : items.map((e) => (
                <TableRow key={e.id} data-testid={`expense-row-${e.id}`}>
                  <TableCell><Badge variant="outline" className="border-slate-300 text-slate-700 bg-slate-50">{e.category}</Badge></TableCell>
                  <TableCell className="font-medium">{e.description}</TableCell>
                  <TableCell className="text-slate-600 text-sm">{formatDate(e.date)}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold text-red-800">{formatTRY(e.amount)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button size="icon" variant="ghost" onClick={() => openEdit(e)}><Pencil className="h-4 w-4" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => remove(e.id)}><Trash2 className="h-4 w-4 text-red-600" /></Button>
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
