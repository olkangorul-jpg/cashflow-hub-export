import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatTRY, formatDate, daysUntil } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { ExportButton } from "@/components/ExportButton";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import ImportDialog from "@/components/ImportDialog";
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

const empty = { type: "received", party: "", amount: 0, due_date: "", status: "pending", notes: "" };
const statusMap = {
  pending: { label: "Bekliyor", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  paid: { label: "Ödendi", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  overdue: { label: "Gecikmiş", cls: "bg-red-50 text-red-800 border-red-200" },
};

export default function PromissoryNotes() {
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState("all");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [range, setRange] = useState({ startDate: "", endDate: "" });

  const load = async () => {
    const params = {};
    if (range.startDate) params.start_date = range.startDate;
    if (range.endDate) params.end_date = range.endDate;
    const { data } = await api.get("/promissory-notes", { params });
    setItems(data);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [range.startDate, range.endDate]);

  const submit = async () => {
    if (!form.party || !form.due_date || !form.amount) return toast.error("Zorunlu alanları doldurun");
    const payload = { ...form, amount: Number(form.amount) };
    if (editing) { await api.put(`/promissory-notes/${editing.id}`, payload); toast.success("Senet güncellendi"); }
    else { await api.post("/promissory-notes", payload); toast.success("Senet eklendi"); }
    setOpen(false); setEditing(null); setForm(empty); load();
  };
  const remove = async (id) => { await api.delete(`/promissory-notes/${id}`); toast.success("Silindi"); load(); };
  const openEdit = (row) => { setEditing(row); setForm(row); setOpen(true); };

  const filtered = tab === "all" ? items : items.filter((c) => c.type === tab);

  return (
    <div data-testid="notes-page">
      <PageHeader
        label="Senetler"
        title="Senet Yönetimi"
        description="Alınan ve verilen senetleri (aşacaklar/borçlar) vadeleriyle takip edin."
        actions={
          <>
            <ImportDialog resource="promissory-notes" label="Senet İçe Aktar" onImported={load} testidPrefix="notes-import" />
            <ExportButton path="/export/promissory-notes" filename="senetler.csv" testid="export-notes-btn" />
            <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(empty); } }}>
              <DialogTrigger asChild>
                <Button data-testid="add-note-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
                  <Plus className="h-4 w-4 mr-2" /> Senet Ekle
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>{editing ? "Senet Düzenle" : "Yeni Senet"}</DialogTitle></DialogHeader>
                <div className="grid gap-3 py-2">
                  <div>
                    <Label>Tür</Label>
                    <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                      <SelectTrigger data-testid="note-type-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="received">Alacak Senedi</SelectItem>
                        <SelectItem value="issued">Borç Senedi</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>{form.type === "received" ? "Borçlu" : "Alacaklı"}</Label>
                    <Input data-testid="note-party-input" value={form.party} onChange={(e) => setForm({ ...form, party: e.target.value })} /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Tutar (₺)</Label><Input data-testid="note-amount-input" type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                    <div><Label>Vade Tarihi</Label><Input data-testid="note-due-date-input" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></div>
                  </div>
                  <div>
                    <Label>Durum</Label>
                    <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pending">Bekliyor</SelectItem>
                        <SelectItem value="paid">Ödendi</SelectItem>
                        <SelectItem value="overdue">Gecikmiş</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Notlar</Label><Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>İptal</Button>
                  <Button data-testid="save-note-btn" onClick={submit} className="bg-slate-900 hover:bg-slate-800 text-white">Kaydet</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <Tabs value={tab} onValueChange={setTab} className="mb-4">
        <TabsList>
          <TabsTrigger value="all">Tümü</TabsTrigger>
          <TabsTrigger value="received">Alacak</TabsTrigger>
          <TabsTrigger value="issued">Borç</TabsTrigger>
        </TabsList>
      </Tabs>

      <DateRangeFilter
        startDate={range.startDate}
        endDate={range.endDate}
        onChange={setRange}
        testidPrefix="notes-date"
      />

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Tür</TableHead>
                <TableHead>Karşı Taraf</TableHead>
                <TableHead>Vade</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead className="text-right">Tutar</TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-12 text-slate-500">Kayıt bulunamadı.</TableCell></TableRow>
              ) : filtered.map((c) => {
                const days = daysUntil(c.due_date);
                return (
                  <TableRow key={c.id} data-testid={`note-row-${c.id}`}>
                    <TableCell>
                      <Badge variant="outline" className={c.type === "received" ? "border-emerald-200 text-emerald-800 bg-emerald-50" : "border-red-200 text-red-800 bg-red-50"}>
                        {c.type === "received" ? "Alacak" : "Borç"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-medium">{c.party}</TableCell>
                    <TableCell>
                      <div className="text-sm">{formatDate(c.due_date)}</div>
                      {c.status === "pending" && <div className={`text-xs ${days < 0 ? "text-red-700" : days <= 3 ? "text-amber-700" : "text-slate-500"}`}>
                        {days < 0 ? `${Math.abs(days)} gün geçti` : days === 0 ? "Bugün" : `${days} gün kaldı`}
                      </div>}
                    </TableCell>
                    <TableCell><Badge variant="outline" className={statusMap[c.status].cls}>{statusMap[c.status].label}</Badge></TableCell>
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
