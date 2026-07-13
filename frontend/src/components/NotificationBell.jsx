import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Bell, Check, RefreshCw } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function NotificationBell() {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    try {
      const [{ data: list }, { data: c }] = await Promise.all([
        api.get("/notifications"),
        api.get("/notifications/unread-count"),
      ]);
      setItems(list);
      setUnread(c.count);
    } catch {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const markAll = async () => {
    await api.post("/notifications/mark-all-read");
    load();
  };

  const markOne = async (id) => {
    await api.post(`/notifications/${id}/read`);
    load();
  };

  const runCheckNow = async () => {
    setChecking(true);
    try {
      const { data } = await api.post("/notifications/check-reminders");
      if (data.created > 0) {
        toast.success(`${data.created} yeni hatırlatma oluşturuldu${data.email_sent ? " · Email gönderildi" : ""}`);
      } else {
        toast.info("Yaklaşan hatırlatma bulunamadı");
      }
      await load();
    } catch {
      toast.error("Kontrol sırasında hata oluştu");
    } finally {
      setChecking(false);
    }
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          data-testid="notification-bell"
          className="relative p-2 rounded-md hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition-colors"
          aria-label="Bildirimler"
        >
          <Bell className="h-4 w-4" strokeWidth={1.75} />
          {unread > 0 && (
            <span
              data-testid="notification-badge"
              className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-600 text-white text-[10px] font-semibold flex items-center justify-center"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-96 p-0 border-slate-200 rounded-md">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
          <div>
            <p className="font-heading font-semibold text-sm">Bildirimler</p>
            <p className="text-xs text-slate-500">{unread} okunmamış</p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={runCheckNow}
              disabled={checking}
              data-testid="check-reminders-btn"
              className="text-xs h-8"
            >
              <RefreshCw className={`h-3 w-3 mr-1 ${checking ? "animate-spin" : ""}`} />
              Kontrol Et
            </Button>
            {unread > 0 && (
              <Button size="sm" variant="ghost" onClick={markAll} data-testid="mark-all-read-btn" className="text-xs h-8">
                <Check className="h-3 w-3 mr-1" /> Tümünü Oku
              </Button>
            )}
          </div>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 ? (
            <div className="p-8 text-center">
              <Bell className="h-8 w-8 text-slate-300 mx-auto mb-2" strokeWidth={1.5} />
              <p className="text-sm text-slate-500">Henüz bildirim yok</p>
              <p className="text-xs text-slate-400 mt-1">Vade tarihleri yaklaştığında burada görünecek.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-200">
              {items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => !n.read && markOne(n.id)}
                  data-testid={`notification-item-${n.id}`}
                  className={`w-full text-left px-4 py-3 transition-colors ${n.read ? "bg-white hover:bg-slate-50" : "bg-blue-50/50 hover:bg-blue-50"}`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`mt-1 h-2 w-2 rounded-full shrink-0 ${n.read ? "bg-slate-300" : "bg-blue-600"}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-900">{n.title}</p>
                      <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{n.body}</p>
                      <p className="text-[11px] text-slate-400 mt-1">
                        {formatDate(n.created_at)}
                        {n.email_sent && <span className="ml-2 text-emerald-700">· Email gönderildi</span>}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
