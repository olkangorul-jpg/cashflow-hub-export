import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import NotificationBell from "@/components/NotificationBell";
import WorkspaceSwitcher from "@/components/WorkspaceSwitcher";
import {
  LayoutDashboard,
  Landmark,
  FileText,
  ScrollText,
  Receipt,
  TrendingUp,
  CalendarClock,
  LogOut,
  Settings as SettingsIcon,
  Users,
} from "lucide-react";

const NAV = [
  { to: "/dashboard", label: "Genel Bakış", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/upcoming", label: "Yaklaşan Ödemeler", icon: CalendarClock, testid: "nav-upcoming" },
  { to: "/bank-accounts", label: "Banka Hesapları", icon: Landmark, testid: "nav-bank-accounts" },
  { to: "/checks", label: "Çekler", icon: FileText, testid: "nav-checks" },
  { to: "/notes", label: "Senetler", icon: ScrollText, testid: "nav-notes" },
  { to: "/expenses", label: "Giderler", icon: Receipt, testid: "nav-expenses" },
  { to: "/incomes", label: "Gelirler", icon: TrendingUp, testid: "nav-incomes" },
  { to: "/team", label: "Ekip", icon: Users, testid: "nav-team" },
  { to: "/settings", label: "Ayarlar", icon: SettingsIcon, testid: "nav-settings" },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F8F9FA] font-body text-slate-900">
      <div className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="hidden lg:flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
          <div className="px-6 py-6 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-md bg-[#0F172A] flex items-center justify-center">
                <TrendingUp className="h-4 w-4 text-white" strokeWidth={2} />
              </div>
              <span className="font-heading font-bold text-lg tracking-tight">Nakit Akış</span>
            </div>
          </div>

          <nav className="flex-1 px-3 py-4 space-y-0.5">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                data-testid={n.testid}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${
                    isActive
                      ? "bg-slate-900 text-white font-semibold"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`
                }
              >
                <n.icon className="h-4 w-4" strokeWidth={1.75} />
                <span>{n.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="border-t border-slate-200 p-4">
            <div className="flex items-center gap-3">
              {user?.picture ? (
                <img src={user.picture} alt={user.name} className="h-9 w-9 rounded-full object-cover border border-slate-200" />
              ) : (
                <div className="h-9 w-9 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-semibold">
                  {user?.name?.[0]?.toUpperCase() || "U"}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate" data-testid="user-name">{user?.name}</p>
                <p className="text-xs text-slate-500 truncate">{user?.email}</p>
              </div>
              <button
                onClick={logout}
                data-testid="logout-button"
                className="p-2 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-md transition-colors"
                title="Çıkış Yap"
              >
                <LogOut className="h-4 w-4" strokeWidth={1.75} />
              </button>
            </div>
          </div>
        </aside>

        {/* Mobile top bar */}
        <div className="flex-1 flex flex-col">
          <header className="lg:hidden flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-md bg-[#0F172A] flex items-center justify-center">
                <TrendingUp className="h-3.5 w-3.5 text-white" strokeWidth={2} />
              </div>
              <span className="font-heading font-bold tracking-tight">Nakit Akış</span>
            </div>
            <div className="flex items-center gap-1">
              <NotificationBell />
              <button onClick={logout} className="p-2 text-slate-500" data-testid="logout-button-mobile">
                <LogOut className="h-4 w-4" strokeWidth={1.75} />
              </button>
            </div>
          </header>

          {/* Desktop top bar */}
          <header className="hidden lg:flex items-center justify-end px-8 py-4 border-b border-slate-200 bg-white gap-3">
            <WorkspaceSwitcher />
            <NotificationBell />
          </header>

          {/* Mobile bottom nav */}
          <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-20 bg-white border-t border-slate-200 flex overflow-x-auto">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `flex-1 min-w-[80px] flex flex-col items-center gap-1 py-2 text-[10px] ${
                    isActive ? "text-slate-900 font-semibold" : "text-slate-500"
                  }`
                }
              >
                <n.icon className="h-4 w-4" strokeWidth={1.75} />
                <span>{n.label}</span>
              </NavLink>
            ))}
          </nav>

          <main className="flex-1 p-4 sm:p-6 lg:p-10 pb-24 lg:pb-10 max-w-[1400px] w-full">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
