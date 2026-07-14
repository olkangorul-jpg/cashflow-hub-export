import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { downloadCsv } from "@/components/ExportButton";
import { formatDate } from "@/lib/format";
import { Database, Download, Trash2, Upload, RotateCcw, Loader2, Clock, HardDriveDownload } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const formatBytes = (b) => {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(2)} MB`;
};

export default function Backups() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [creating, setCreating] = useState(false);
  const [restoreDialog, setRestoreDialog] = useState(null); // {backup, mode}
  const [uploadDialog, setUploadDialog] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadMode, setUploadMode] = useState("merge");
  const [restoring, setRestoring] = useState(false);
  const fileRef = useRef(null);

  const canWrite = user?.role !== "viewer";

  const load = async () => {
    try {
      const { data } = await api.get("/backups");
      setItems(data);
    } catch {}
  };
  useEffect(() => { load(); }, []);

  const createBackup = async () => {
    setCreating(true);
    try {
      await api.post("/backups");
      toast.success("Yedek oluşturuldu");
      load();
    } catch {
      toast.error("Yedek oluşturulamadı");
    } finally {
      setCreating(false);
    }
  };

  const download = async (id, date) => {
    try {
      await downloadCsv(`/backups/${id}/download`, `nakit-akis-yedek-${date.slice(0,10)}.json`);
    } catch {
      toast.error("İndirilemedi");
    }
  };

  const remove = async (id) => {
    if (!confirm("Bu yedeği silmek istediğinize emin misiniz?")) return;
    try {
      await api.delete(`/backups/${id}`);
      toast.success("Silindi");
      load();
    } catch {
      toast.error("Silinemedi");
    }
  };

  const doRestore = async () => {
    setRestoring(true);
    try {
      const { data } = await api.post(`/backups/${restoreDialog.backup.id}/restore?mode=${restoreDialog.mode}`);
      toast.success(`${data.restored} kayıt geri yüklendi`);
      setRestoreDialog(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Geri yüklenemedi");
    } finally {
      setRestoring(false);
    }
  };

  const doUploadRestore = async () => {
    if (!uploadFile) return toast.error("Dosya seçin");
    setRestoring(true);
    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      const { data } = await api.post(`/backups/restore-file?mode=${uploadMode}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`${data.restored} kayıt geri yüklendi`);
      setUploadDialog(false);
      setUploadFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Yüklenemedi");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div data-testid="backups-page">
      <PageHeader
        label="Yedekleme"
        title="Veri Yedekleri"
        description="Workspace verilerinizin JSON snapshot'larını manuel oluşturun veya haftalık otomatik yedeklemeleri yönetin."
        actions={
          canWrite && (
            <>
              <Button
                variant="outline"
                onClick={() => setUploadDialog(true)}
                data-testid="upload-restore-btn"
                className="border-slate-300 text-slate-700 hover:bg-slate-50"
              >
                <Upload className="h-4 w-4 mr-2" strokeWidth={1.75} /> Dosyadan Geri Yükle
              </Button>
              <Button
                onClick={createBackup}
                disabled={creating}
                data-testid="create-backup-btn"
                className="bg-slate-900 hover:bg-slate-800 text-white"
              >
                {creating ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Database className="h-4 w-4 mr-2" strokeWidth={1.75} />}
                {creating ? "Oluşturuluyor..." : "Yedek Oluştur"}
              </Button>
            </>
          )
        }
      />

      <Card className="border-slate-200 rounded-md shadow-none mb-6">
        <CardContent className="p-6 flex items-start gap-3">
          <Clock className="h-5 w-5 text-slate-600 mt-0.5" strokeWidth={1.75} />
          <div className="text-sm text-slate-700 leading-relaxed">
            <strong>Otomatik yedekleme:</strong> Her Pazar 03:00 UTC (Pazar sabahı 06:00 Türkiye) tüm workspace'ler için otomatik yedek alınır. Sistem workspace başına son <strong>10</strong> yedeği saklar; eski yedekler otomatik silinir.
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <div className="px-6 py-4 border-b border-slate-200">
            <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Yedekler</p>
            <p className="font-heading text-lg font-semibold mt-0.5">{items.length} kayıt</p>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Tarih</TableHead>
                <TableHead>Tür</TableHead>
                <TableHead className="text-right">Kayıt</TableHead>
                <TableHead className="text-right">Boyut</TableHead>
                <TableHead className="w-40 text-right">İşlemler</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-12 text-slate-500">
                    Henüz yedek yok. "Yedek Oluştur" butonuna basın.
                  </TableCell>
                </TableRow>
              ) : items.map((b) => (
                <TableRow key={b.id} data-testid={`backup-row-${b.id}`}>
                  <TableCell>
                    <div className="text-sm font-medium">{formatDate(b.created_at)}</div>
                    <div className="text-xs text-slate-500">{new Date(b.created_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={b.kind === "auto" ? "border-blue-200 text-blue-800 bg-blue-50" : "border-slate-200 text-slate-700 bg-slate-50"}>
                      {b.kind === "auto" ? "Otomatik" : "Manuel"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">{b.total_records}</TableCell>
                  <TableCell className="text-right tabular-nums text-slate-600 text-sm">{formatBytes(b.size_bytes)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button size="icon" variant="ghost" onClick={() => download(b.id, b.created_at)} data-testid={`download-backup-${b.id}`} title="İndir">
                        <HardDriveDownload className="h-4 w-4" />
                      </Button>
                      {canWrite && (
                        <Button size="icon" variant="ghost" onClick={() => setRestoreDialog({ backup: b, mode: "merge" })} data-testid={`restore-backup-${b.id}`} title="Geri Yükle">
                          <RotateCcw className="h-4 w-4 text-blue-700" />
                        </Button>
                      )}
                      {canWrite && (
                        <Button size="icon" variant="ghost" onClick={() => remove(b.id)} data-testid={`delete-backup-${b.id}`} title="Sil">
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Restore dialog (from existing backup) */}
      <Dialog open={!!restoreDialog} onOpenChange={(v) => !v && setRestoreDialog(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Yedeği Geri Yükle</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-sm">
              <div className="text-slate-700">
                <strong>Tarih:</strong> {restoreDialog && formatDate(restoreDialog.backup.created_at)}
              </div>
              <div className="text-slate-700"><strong>Kayıt sayısı:</strong> {restoreDialog?.backup.total_records}</div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Mod</Label>
              <RadioGroup
                value={restoreDialog?.mode || "merge"}
                onValueChange={(v) => setRestoreDialog({ ...restoreDialog, mode: v })}
                className="mt-2 space-y-2"
              >
                <div className="flex items-start gap-2 p-3 border border-slate-200 rounded-md cursor-pointer" onClick={() => setRestoreDialog({ ...restoreDialog, mode: "merge" })}>
                  <RadioGroupItem value="merge" id="merge" className="mt-0.5" />
                  <div className="flex-1">
                    <Label htmlFor="merge" className="text-sm font-semibold cursor-pointer">Birleştir</Label>
                    <p className="text-xs text-slate-500 mt-0.5">Mevcut verilere ek olarak yedekteki kayıtları yeni ID'lerle ekler. Hiçbir şey silinmez.</p>
                  </div>
                </div>
                <div className="flex items-start gap-2 p-3 border border-red-200 bg-red-50/30 rounded-md cursor-pointer" onClick={() => setRestoreDialog({ ...restoreDialog, mode: "replace" })}>
                  <RadioGroupItem value="replace" id="replace" className="mt-0.5" />
                  <div className="flex-1">
                    <Label htmlFor="replace" className="text-sm font-semibold cursor-pointer">Değiştir (dikkat!)</Label>
                    <p className="text-xs text-red-700 mt-0.5">Mevcut tüm banka hesabı, çek, senet, gelir ve gider kayıtlarınız silinir; yedekteki veriler yerine geçer.</p>
                  </div>
                </div>
              </RadioGroup>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRestoreDialog(null)}>İptal</Button>
            <Button onClick={doRestore} disabled={restoring} data-testid="confirm-restore-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
              <RotateCcw className="h-4 w-4 mr-2" />
              {restoring ? "Geri yükleniyor..." : "Geri Yükle"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload restore dialog */}
      <Dialog open={uploadDialog} onOpenChange={(v) => { setUploadDialog(v); if (!v) { setUploadFile(null); if (fileRef.current) fileRef.current.value = ""; } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Dosyadan Geri Yükle</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Yedek Dosyası (.json)</Label>
              <input
                ref={fileRef}
                type="file"
                accept=".json,application/json"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                data-testid="restore-file-input"
                className="mt-2 block w-full text-sm text-slate-700 file:mr-3 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-slate-900 file:text-white hover:file:bg-slate-800 file:cursor-pointer"
              />
              {uploadFile && <p className="text-xs text-slate-500 mt-2">{uploadFile.name} · {(uploadFile.size / 1024).toFixed(1)} KB</p>}
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Mod</Label>
              <RadioGroup value={uploadMode} onValueChange={setUploadMode} className="mt-2 space-y-2">
                <div className="flex items-start gap-2 p-3 border border-slate-200 rounded-md">
                  <RadioGroupItem value="merge" id="u-merge" className="mt-0.5" />
                  <div><Label htmlFor="u-merge" className="text-sm font-semibold">Birleştir</Label></div>
                </div>
                <div className="flex items-start gap-2 p-3 border border-red-200 bg-red-50/30 rounded-md">
                  <RadioGroupItem value="replace" id="u-replace" className="mt-0.5" />
                  <div><Label htmlFor="u-replace" className="text-sm font-semibold">Değiştir</Label></div>
                </div>
              </RadioGroup>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadDialog(false)}>İptal</Button>
            <Button onClick={doUploadRestore} disabled={!uploadFile || restoring} data-testid="confirm-upload-restore-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
              <Upload className="h-4 w-4 mr-2" />
              {restoring ? "Yükleniyor..." : "Geri Yükle"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
