import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent } from "@/components/ui/card";
import { Mail, Bell, Calendar, Save } from "lucide-react";
import { toast } from "sonner";

const DAY_OPTIONS = [1, 3, 7, 14, 30];

export default function Settings() {
  const [prefs, setPrefs] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const { data } = await api.get("/preferences");
      setPrefs(data);
    })();
  }, []);

  const toggleDay = (d) => {
    const days = prefs.reminder_days.includes(d)
      ? prefs.reminder_days.filter((x) => x !== d)
      : [...prefs.reminder_days, d].sort((a, b) => a - b);
    setPrefs({ ...prefs, reminder_days: days });
  };

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/preferences", prefs);
      setPrefs(data);
      toast.success("Tercihler kaydedildi");
    } catch {
      toast.error("Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  if (!prefs) {
    return <div className="h-64 rounded-md border border-slate-200 bg-white animate-pulse" />;
  }

  return (
    <div data-testid="settings-page">
      <PageHeader
        label="Ayarlar"
        title="Bildirim Tercihleri"
        description="Hatırlatma kanallarını ve zamanlamayı buradan yönetin."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="border-slate-200 rounded-md shadow-none lg:col-span-2">
          <CardContent className="p-6 space-y-6">
            {/* Channel toggles */}
            <div>
              <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500 mb-4">Kanallar</p>

              <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-200">
                <div className="flex items-start gap-3">
                  <div className="h-9 w-9 rounded-md bg-blue-100 text-blue-800 flex items-center justify-center shrink-0">
                    <Bell className="h-4 w-4" strokeWidth={1.75} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Uygulama İçi Bildirim</p>
                    <p className="text-xs text-slate-500 mt-0.5">Sağ üstteki zil ikonunda görünür</p>
                  </div>
                </div>
                <Switch
                  data-testid="in-app-toggle"
                  checked={prefs.in_app_enabled}
                  onCheckedChange={(v) => setPrefs({ ...prefs, in_app_enabled: v })}
                />
              </div>

              <div className="flex items-start justify-between gap-4 py-3">
                <div className="flex items-start gap-3">
                  <div className="h-9 w-9 rounded-md bg-emerald-100 text-emerald-800 flex items-center justify-center shrink-0">
                    <Mail className="h-4 w-4" strokeWidth={1.75} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Email Bildirimi</p>
                    <p className="text-xs text-slate-500 mt-0.5">Vade yaklaştığında HTML formatlı özet email gönderilir</p>
                  </div>
                </div>
                <Switch
                  data-testid="email-toggle"
                  checked={prefs.email_enabled}
                  onCheckedChange={(v) => setPrefs({ ...prefs, email_enabled: v })}
                />
              </div>
            </div>

            {/* Custom email override */}
            {prefs.email_enabled && (
              <div>
                <Label className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">
                  Bildirim Email Adresi (opsiyonel)
                </Label>
                <Input
                  data-testid="notification-email-input"
                  type="email"
                  placeholder="Google hesabı emaili kullanılır (boş bırakın)"
                  value={prefs.notification_email || ""}
                  onChange={(e) => setPrefs({ ...prefs, notification_email: e.target.value })}
                  className="mt-2"
                />
                <p className="text-xs text-slate-500 mt-1.5">
                  Farklı bir adrese göndermek isterseniz buraya yazın. Boş bırakırsanız Google hesap emailinize gider.
                </p>
              </div>
            )}

            {/* Reminder days */}
            <div>
              <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500 mb-3">
                Hatırlatma Zamanlaması
              </p>
              <p className="text-sm text-slate-600 mb-3">
                Vadeden kaç gün önce hatırlatılsın? Birden fazla seçebilirsiniz.
              </p>
              <div className="flex flex-wrap gap-2">
                {DAY_OPTIONS.map((d) => {
                  const active = prefs.reminder_days.includes(d);
                  return (
                    <button
                      key={d}
                      onClick={() => toggleDay(d)}
                      data-testid={`day-chip-${d}`}
                      className={`px-4 py-2 rounded-md border text-sm font-medium transition-colors ${
                        active
                          ? "bg-slate-900 text-white border-slate-900"
                          : "bg-white text-slate-700 border-slate-300 hover:border-slate-500"
                      }`}
                    >
                      {d} gün önce
                    </button>
                  );
                })}
              </div>
              {prefs.reminder_days.length === 0 && (
                <p className="text-xs text-red-700 mt-2">En az bir hatırlatma günü seçin.</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 rounded-md shadow-none">
          <CardContent className="p-6">
            <div className="flex items-center gap-2 mb-3">
              <Calendar className="h-4 w-4 text-slate-600" strokeWidth={1.75} />
              <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Otomatik Zamanlama</p>
            </div>
            <p className="text-sm text-slate-700 leading-relaxed">
              Sistem her gün <strong>09:00 Türkiye saatinde</strong> tüm bekleyen çek ve senetlerinizi tarar, seçtiğiniz günlere denk gelenler için bildirim ve/veya email gönderir.
            </p>
            <div className="mt-4 p-3 bg-slate-50 border border-slate-200 rounded-md">
              <p className="text-xs text-slate-600">
                💡 Anlık kontrol için sağ üst köşedeki <strong>zil ikonu → "Kontrol Et"</strong> butonunu kullanabilirsiniz.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 flex justify-end">
        <Button
          onClick={save}
          disabled={saving || prefs.reminder_days.length === 0}
          data-testid="save-preferences-btn"
          className="bg-slate-900 hover:bg-slate-800 text-white"
        >
          <Save className="h-4 w-4 mr-2" strokeWidth={1.75} />
          {saving ? "Kaydediliyor..." : "Kaydet"}
        </Button>
      </div>
    </div>
  );
}
