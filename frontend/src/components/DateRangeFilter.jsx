import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

export const DateRangeFilter = ({ startDate, endDate, onChange, testidPrefix = "date" }) => {
  const clear = () => onChange({ startDate: "", endDate: "" });
  const active = startDate || endDate;

  const setPreset = (days) => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - days + 1);
    onChange({
      startDate: start.toISOString().slice(0, 10),
      endDate: end.toISOString().slice(0, 10),
    });
  };

  const setThisMonth = () => {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    onChange({
      startDate: first.toISOString().slice(0, 10),
      endDate: now.toISOString().slice(0, 10),
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4 p-3 bg-white border border-slate-200 rounded-md">
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Tarih:</span>
        <Input
          data-testid={`${testidPrefix}-start`}
          type="date"
          value={startDate}
          onChange={(e) => onChange({ startDate: e.target.value, endDate })}
          className="h-9 w-40"
        />
        <span className="text-slate-400 text-sm">—</span>
        <Input
          data-testid={`${testidPrefix}-end`}
          type="date"
          value={endDate}
          onChange={(e) => onChange({ startDate, endDate: e.target.value })}
          className="h-9 w-40"
        />
      </div>
      <div className="flex items-center gap-1 ml-auto">
        <Button variant="ghost" size="sm" onClick={setThisMonth} data-testid={`${testidPrefix}-this-month`} className="h-8 text-xs">
          Bu Ay
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setPreset(30)} className="h-8 text-xs">
          Son 30 Gün
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setPreset(90)} className="h-8 text-xs">
          Son 90 Gün
        </Button>
        {active && (
          <Button variant="ghost" size="sm" onClick={clear} data-testid={`${testidPrefix}-clear`} className="h-8 text-xs text-slate-500">
            <X className="h-3 w-3 mr-1" /> Temizle
          </Button>
        )}
      </div>
    </div>
  );
};
