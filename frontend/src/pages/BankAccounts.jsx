import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Plus, Landmark, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const empty = { name: "", bank_name: "", account_number: "", balance: 0, currency: "TRY" };

export default function BankAccounts() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    const { data } = await api.get("/bank-accounts");
    setItems(data);
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.name || !form.bank_name) return toast.error("Ad ve banka zorunlu");
    const payload = { ...form, balance: Number(form.balance) || 0 };
    if (editing) {
      await api.put(`/bank-accounts/${editing.id}`, payload);
      toast.success("Hesap güncellendi");
    } else {
      await api.post("/bank-accounts", payload);
      toast.success("Hesap eklendi");
    }
    setOpen(false); setEditing(null); setForm(empty); load();
  };

  const remove = async (id) => {
    await api.delete(`/bank-accounts/${id}`);
    toast.success("Hesap silindi");
    load();
  };

  const openEdit = (row) => { setEditing(row); setForm(row); setOpen(true); };

  const total = items.reduce((s, i) => s + (i.balance || 0), 0);

  return (
    <div data-testid="bank-accounts-page">
      <PageHeader
        label="Hesaplar"
        title="Banka Hesapları"
        description="Tüm banka hesaplarınız ve güncel bakiyeleri."
        actions={
          <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(empty); } }}>
            <DialogTrigger asChild>
              <Button data-testid="add-account-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
                <Plus className="h-4 w-4 mr-2" /> Hesap Ekle
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>{editing ? "Hesap Düzenle" : "Yeni Banka Hesabı"}</DialogTitle></DialogHeader>
              <div className="grid gap-3 py-2">
                <div><Label>Hesap Adı</Label><Input data-testid="account-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Örn: Vadesiz TL" /></div>
                <div><Label>Banka</Label><Input data-testid="account-bank-input" value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} placeholder="Örn: Garanti BBVA" /></div>
                <div><Label>Hesap Numarası / IBAN</Label><Input value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} placeholder="TR..." /></div>
                <div><Label>Bakiye (₺)</Label><Input data-testid="account-balance-input" type="number" step="0.01" value={form.balance} onChange={(e) => setForm({ ...form, balance: e.target.value })} /></div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>İptal</Button>
                <Button data-testid="save-account-btn" onClick={submit} className="bg-slate-900 hover:bg-slate-800 text-white">Kaydet</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="border-slate-200 rounded-md shadow-none mb-6">
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Toplam Bakiye</p>
          <p className="mt-2 font-heading text-3xl font-bold tabular-nums" data-testid="total-balance">{formatTRY(total)}</p>
          <p className="text-xs text-slate-500 mt-1">{items.length} hesap</p>
        </CardContent>
      </Card>

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Hesap</TableHead>
                <TableHead>Banka</TableHead>
                <TableHead>IBAN / No</TableHead>
                <TableHead className="text-right">Bakiye</TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-12 text-slate-500">Henüz hesap eklenmedi.</TableCell></TableRow>
              ) : items.map((a) => (
                <TableRow key={a.id} data-testid={`account-row-${a.id}`}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="h-8 w-8 rounded-md bg-slate-100 flex items-center justify-center"><Landmark className="h-4 w-4 text-slate-700" /></div>
                      <span className="font-medium">{a.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-slate-600">{a.bank_name}</TableCell>
                  <TableCell className="text-slate-500 font-mono text-xs">{a.account_number || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">{formatTRY(a.balance)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button size="icon" variant="ghost" onClick={() => openEdit(a)} data-testid={`edit-account-${a.id}`}><Pencil className="h-4 w-4" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => remove(a.id)} data-testid={`delete-account-${a.id}`}><Trash2 className="h-4 w-4 text-red-600" /></Button>
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
