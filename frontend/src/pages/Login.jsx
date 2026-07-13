import { Button } from "@/components/ui/button";
import { TrendingUp, Wallet, FileText, Bell } from "lucide-react";

export default function Login() {
  const handleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] font-body">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
        {/* Left panel */}
        <div className="hidden lg:flex flex-col justify-between p-12 bg-[#0F172A] text-white">
          <div className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-md bg-white flex items-center justify-center">
              <TrendingUp className="h-5 w-5 text-[#0F172A]" strokeWidth={2} />
            </div>
            <span className="font-heading font-bold text-xl tracking-tight">Nakit Akış</span>
          </div>

          <div className="space-y-8">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400 font-semibold">Finansal Kontrol Paneli</p>
              <h1 className="mt-4 font-heading text-4xl xl:text-5xl font-bold tracking-tight leading-tight">
                Çeklerinizi, senetlerinizi ve nakit akışınızı tek ekrandan yönetin.
              </h1>
              <p className="mt-6 text-slate-300 text-base leading-relaxed max-w-md">
                Yaklaşan ödemeleri kaçırmayın. Banka hesaplarınızı takip edin. Gerçek zamanlı raporlarla finansal geleceğinizi planlayın.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 max-w-md">
              {[
                { icon: Wallet, title: "Banka Hesapları", desc: "Tüm hesaplarınızın bakiyeleri tek yerde" },
                { icon: FileText, title: "Çek & Senet Yönetimi", desc: "Vade tarihlerini asla kaçırmayın" },
                { icon: Bell, title: "Ödeme Hatırlatmaları", desc: "30 gün önceden uyarı sistemi" },
              ].map((f, i) => (
                <div key={i} className="flex items-start gap-3 border border-slate-800 rounded-md p-4 bg-slate-900/40">
                  <f.icon className="h-5 w-5 text-emerald-400 mt-0.5" strokeWidth={1.75} />
                  <div>
                    <p className="text-sm font-semibold">{f.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{f.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <p className="text-xs text-slate-500">© {new Date().getFullYear()} Nakit Akış Yönetimi</p>
        </div>

        {/* Right panel */}
        <div className="flex items-center justify-center p-8 lg:p-16">
          <div className="w-full max-w-md">
            <div className="lg:hidden flex items-center gap-2 mb-8">
              <div className="h-9 w-9 rounded-md bg-[#0F172A] flex items-center justify-center">
                <TrendingUp className="h-5 w-5 text-white" strokeWidth={2} />
              </div>
              <span className="font-heading font-bold text-xl tracking-tight text-slate-900">Nakit Akış</span>
            </div>

            <p className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">Hoş Geldiniz</p>
            <h2 className="mt-3 font-heading text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
              Hesabınıza giriş yapın
            </h2>
            <p className="mt-3 text-slate-600 leading-relaxed">
              Google hesabınızla saniyeler içinde giriş yapın ve nakit akışınızı yönetmeye başlayın.
            </p>

            <Button
              data-testid="google-login-button"
              onClick={handleLogin}
              className="mt-8 h-12 w-full bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-md transition-colors"
            >
              <svg className="h-5 w-5 mr-2" viewBox="0 0 24 24">
                <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.4-1.7 4.2-5.5 4.2-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.9 1.5l2.6-2.6C16.9 3.5 14.7 2.5 12 2.5 6.8 2.5 2.6 6.7 2.6 12s4.2 9.5 9.4 9.5c5.5 0 9.1-3.8 9.1-9.3 0-.6-.1-1.1-.2-1.6H12z" />
              </svg>
              Google ile Giriş Yap
            </Button>

            <div className="mt-8 border-t border-slate-200 pt-6">
              <p className="text-xs text-slate-500 leading-relaxed">
                Giriş yaparak, verilerinizin güvenli şekilde saklanacağını ve sadece sizin tarafınızdan erişilebilir olacağını onaylıyorsunuz.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
