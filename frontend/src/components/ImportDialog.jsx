import { useState, useRef } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Upload, FileSpreadsheet, Download, AlertTriangle, CheckCircle2 } from "lucide-react";
import { downloadCsv } from "@/components/ExportButton";
import { toast } from "sonner";

export default function ImportDialog({ resource, label, onImported, testidPrefix = "import" }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  const downloadTemplate = async () => {
    try {
      await downloadCsv(`/import/${resource}/template`, `sablon-${resource}.xlsx`);
    } catch {
      toast.error("Şablon indirilemedi");
    }
  };

  const submit = async () => {
    if (!file) return toast.error("Dosya seçin");
    setUploading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/import/${resource}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      if (data.inserted > 0) {
        toast.success(`${data.inserted} kayıt eklendi`);
        onImported?.();
      } else {
        toast.warning("Hiç kayıt eklenmedi");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Yükleme başarısız");
    } finally {
      setUploading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setResult(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          data-testid={`${testidPrefix}-btn`}
          className="border-slate-300 text-slate-700 hover:bg-slate-50 hover:text-slate-900 font-medium"
        >
          <Upload className="h-4 w-4 mr-2" strokeWidth={1.75} /> İçe Aktar
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{label || "Toplu İçe Aktarma"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-md flex items-start gap-3">
            <FileSpreadsheet className="h-5 w-5 text-slate-600 mt-0.5 shrink-0" strokeWidth={1.75} />
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-900">Şablonu indirin</p>
              <p className="text-xs text-slate-600 mt-0.5">Doğru kolon isimleri için önce şablonu indirip doldurun. Excel (.xlsx) veya CSV desteklenir.</p>
              <Button
                variant="link"
                onClick={downloadTemplate}
                data-testid={`${testidPrefix}-template-btn`}
                className="h-auto p-0 text-slate-900 mt-1"
              >
                <Download className="h-3 w-3 mr-1" /> Şablonu İndir (.xlsx)
              </Button>
            </div>
          </div>

          <div>
            <label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Dosya</label>
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xlsm,.csv"
              onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }}
              data-testid={`${testidPrefix}-file-input`}
              className="mt-2 block w-full text-sm text-slate-700 file:mr-3 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-slate-900 file:text-white hover:file:bg-slate-800 file:cursor-pointer"
            />
            {file && <p className="text-xs text-slate-500 mt-2">{file.name} · {(file.size / 1024).toFixed(1)} KB</p>}
          </div>

          {result && (
            <div className="space-y-2">
              {result.inserted > 0 && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-700 mt-0.5 shrink-0" />
                  <p className="text-sm text-emerald-900">
                    <strong>{result.inserted}</strong> / {result.total_rows} kayıt başarıyla eklendi
                  </p>
                </div>
              )}
              {result.errors?.length > 0 && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <div className="flex items-center gap-2 mb-1">
                    <AlertTriangle className="h-4 w-4 text-red-700" />
                    <p className="text-sm font-semibold text-red-900">{result.errors.length} satırda hata</p>
                  </div>
                  <div className="max-h-40 overflow-y-auto text-xs text-red-800 space-y-1 mt-2">
                    {result.errors.slice(0, 10).map((e, i) => (
                      <div key={i}>Satır {e.row}: {e.message}</div>
                    ))}
                    {result.errors.length > 10 && <div>ve {result.errors.length - 10} tane daha…</div>}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Kapat</Button>
          <Button
            onClick={submit}
            disabled={!file || uploading}
            data-testid={`${testidPrefix}-submit-btn`}
            className="bg-slate-900 hover:bg-slate-800 text-white"
          >
            <Upload className="h-4 w-4 mr-2" /> {uploading ? "Yükleniyor..." : "İçe Aktar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
