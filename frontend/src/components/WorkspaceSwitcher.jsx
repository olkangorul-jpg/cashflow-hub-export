import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Building2, Check, ChevronDown, Crown, Edit3, Eye } from "lucide-react";
import { toast } from "sonner";

const ROLE_ICON = { owner: Crown, editor: Edit3, viewer: Eye };

export default function WorkspaceSwitcher() {
  const { user, refreshUser } = useAuth();
  const [workspaces, setWorkspaces] = useState([]);

  const load = async () => {
    try {
      const { data } = await api.get("/workspaces");
      setWorkspaces(data);
    } catch {}
  };

  useEffect(() => { load(); }, [user?.workspace_id]);

  const switchTo = async (wid) => {
    if (wid === user.workspace_id) return;
    try {
      await api.post("/workspaces/switch", { workspace_id: wid });
      toast.success("Workspace değiştirildi");
      await refreshUser();
      // Reload page data
      window.location.reload();
    } catch {
      toast.error("Değiştirilemedi");
    }
  };

  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          data-testid="workspace-switcher"
          className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-slate-200 hover:border-slate-400 bg-white transition-colors"
        >
          <Building2 className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
          <span className="text-sm font-medium text-slate-900 max-w-[180px] truncate">{user.workspace_name}</span>
          <ChevronDown className="h-3 w-3 text-slate-400" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">
          Workspace'ler
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {workspaces.map((w) => {
          const Icon = ROLE_ICON[w.role] || Building2;
          return (
            <DropdownMenuItem
              key={w.workspace_id}
              onClick={() => switchTo(w.workspace_id)}
              data-testid={`ws-item-${w.workspace_id}`}
              className="flex items-center gap-2 py-2.5 cursor-pointer"
            >
              <Icon className="h-4 w-4 text-slate-600 shrink-0" strokeWidth={1.75} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">{w.name}</p>
                <p className="text-xs text-slate-500 capitalize">{w.role}</p>
              </div>
              {w.is_active && <Check className="h-4 w-4 text-emerald-700" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
