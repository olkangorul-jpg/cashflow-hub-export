import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate, daysUntil } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { ExportButton } from "@/components/ExportButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const empty = { type: "received", party: "", amount: 0, due_date: "", bank_name: "", check_number: "", status: "pending", notes: "" };

const statusMap = {
  pending: { label: "Bekliyor", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  cleared: { label: "Tahsil Edildi", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  bounced: { label: "Karşılıksız", cls: "bg-red-50 text-red-800 border-red-200" },
};

export default function Checks() {
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState("all");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);

  const load = async () => { const { data } = await api.get("/checks"); setItems(data); };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.party || !form.due_date || !form.amount) return toast.error("Zorunlu alanları doldurun");
    const payload = { ...form, amount: Number(form.amount) };
    if (editing) { await api.put(`/checks/${editing.id}`, payload); toast.success("Çek güncellendi"); }
    else { await api.post("/checks", payload); toast.success("Çek eklendi"); }
    setOpen(false); setEditing(null); setForm(empty); load();
  };

  const remove = async (id) => { await api.delete(`/checks/${id}`); toast.success("Silindi"); load(); };
  const openEdit = (row) => { setEditing(row); setForm(row); setOpen(true); };

  const filtered = tab === "all" ? items : items.filter((c) => c.type === tab);
  const totalIn = items.filter((c) => c.type === "received" && c.status === "pending").reduce((s, c) => s + c.amount, 0);
  const totalOut = items.filter((c) => c.type === "issued" && c.status === "pending").reduce((s, c) => s + c.amount, 0);

  return (
    <div data-testid="checks-page">
      <PageHeader
        label="Çekler"
        title="Çek Yönetimi"
        description="Alınan ve verilen çekleri vade tarihlerine göre takip edin."
        actions={
          <>
            <ExportButton path="/export/checks" filename="cekler.csv" testid="export-checks-btn" />
            <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(empty); } }}>
              <DialogTrigger asChild>
                <Button data-testid="add-check-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
                  <Plus className="h-4 w-4 mr-2" /> Çek Ekle
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>{editing ? "Çek Düzenle" : "Yeni Çek"}</DialogTitle></DialogHeader>
                <div className="grid gap-3 py-2">
                  <div>
                    <Label>Tür</Label>
                    <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                      <SelectTrigger data-testid="check-type-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="received">Alınan Çek</SelectItem>
                        <SelectItem value="issued">Verilen Çek</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>{form.type === "received" ? "Keşideci (Ödeyen)" : "Lehtar (Alan)"}</Label>
                    <Input data-testid="check-party-input" value={form.party} onChange={(e) => setForm({ ...form, party: e.target.value })} /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Tutar (₺)</Label><Input data-testid="check-amount-input" type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                    <div><Label>Vade Tarihi</Label><Input data-testid="check-due-date-input" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Banka</Label><Input value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} /></div>
                    <div><Label>Çek No</Label><Input value={form.check_number} onChange={(e) => setForm({ ...form, check_number: e.target.value })} /></div>
                  </div>
                  <div>
                    <Label>Durum</Label>
                    <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pending">Bekliyor</SelectItem>
                        <SelectItem value="cleared">Tahsil Edildi</SelectItem>
                        <SelectItem value="bounced">Karşılıksız</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Notlar</Label><Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>İptal</Button>
                  <Button data-testid="save-check-btn" onClick={submit} className="bg-slate-900 hover:bg-slate-800 text-white">Kaydet</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Bekleyen Alınan Çekler</p>
            <p className="mt-2 font-heading text-2xl font-bold text-emerald-800 tabular-nums">{formatTRY(totalIn)}</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Bekleyen Verilen Çekler</p>
            <p className="mt-2 font-heading text-2xl font-bold text-red-800 tabular-nums">{formatTRY(totalOut)}</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="mb-4">
        <TabsList>
          <TabsTrigger value="all" data-testid="tab-all">Tümü</TabsTrigger>
          <TabsTrigger value="received" data-testid="tab-received">Alınan</TabsTrigger>
          <TabsTrigger value="issued" data-testid="tab-issued">Verilen</TabsTrigger>
        </TabsList>
      </Tabs>

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Tür</TableHead>
                <TableHead>Kişi/Firma</TableHead>
                <TableHead>Banka / Çek No</TableHead>
                <TableHead>Vade</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead className="text-right">Tutar</TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-12 text-slate-500">Kayıt bulunamadı.</TableCell></TableRow>
              ) : filtered.map((c) => {
                const days = daysUntil(c.due_date);
                return (
                  <TableRow key={c.id} data-testid={`check-row-${c.id}`}>
                    <TableCell>
                      <Badge variant="outline" className={c.type === "received" ? "border-emerald-200 text-emerald-800 bg-emerald-50" : "border-red-200 text-red-800 bg-red-50"}>
                        {c.type === "received" ? "Alınan" : "Verilen"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-medium">{c.party}</TableCell>
                    <TableCell className="text-slate-600 text-xs">{c.bank_name || "-"} · {c.check_number || "-"}</TableCell>
                    <TableCell>
                      <div className="text-sm">{formatDate(c.due_date)}</div>
                      {c.status === "pending" && <div className={`text-xs ${days < 0 ? "text-red-700" : days <= 3 ? "text-amber-700" : "text-slate-500"}`}>
                        {days < 0 ? `${Math.abs(days)} gün geçti` : days === 0 ? "Bugün" : `${days} gün kaldı`}
                      </div>}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={statusMap[c.status].cls}>{statusMap[c.status].label}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums font-semibold">{formatTRY(c.amount)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button size="icon" variant="ghost" onClick={() => openEdit(c)}><Pencil className="h-4 w-4" /></Button>
                        <Button size="icon" variant="ghost" onClick={() => remove(c.id)}><Trash2 className="h-4 w-4 text-red-600" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
