import { api, API } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

export const downloadCsv = async (path, filename) => {
  const res = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

export const ExportButton = ({ path, filename, testid }) => (
  <Button
    variant="outline"
    onClick={() => downloadCsv(path, filename)}
    data-testid={testid}
    className="border-slate-300 text-slate-700 hover:bg-slate-50 hover:text-slate-900 font-medium"
  >
    <Download className="h-4 w-4 mr-2" strokeWidth={1.75} /> CSV Dışa Aktar
  </Button>
);

export { API };
