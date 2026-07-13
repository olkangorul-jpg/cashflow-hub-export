import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { UserPlus, Trash2, Crown, Edit3, Eye, Mail, Pencil } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const ROLE_META = {
  owner: { label: "Sahibi", icon: Crown, cls: "bg-amber-50 text-amber-800 border-amber-200" },
  editor: { label: "Editör", icon: Edit3, cls: "bg-blue-50 text-blue-800 border-blue-200" },
  viewer: { label: "Görüntüleyici", icon: Eye, cls: "bg-slate-50 text-slate-700 border-slate-200" },
};

export default function Team() {
  const { user, refreshUser } = useAuth();
  const [members, setMembers] = useState([]);
  const [wsName, setWsName] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState({ email: "", role: "editor" });
  const [saving, setSaving] = useState(false);

  const isOwner = user?.role === "owner";

  const load = async () => {
    if (!user?.workspace_id) return;
    const { data } = await api.get(`/workspaces/${user.workspace_id}/members`);
    setMembers(data);
    setWsName(user.workspace_name || "");
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [user?.workspace_id]);

  const submitInvite = async () => {
    if (!invite.email || !invite.email.includes("@")) return toast.error("Geçerli bir email girin");
    setSaving(true);
    try {
      const { data } = await api.post(`/workspaces/${user.workspace_id}/invite`, invite);
      if (data.status === "pending") {
        toast.success("Davet gönderildi (email ile ulaşacak)");
      } else {
        toast.success("Üye eklendi");
      }
      setInviteOpen(false);
      setInvite({ email: "", role: "editor" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Davet gönderilemedi");
    } finally {
      setSaving(false);
    }
  };

  const removeMember = async (id) => {
    if (!confirm("Bu üyeyi workspace'ten çıkarmak istediğinize emin misiniz?")) return;
    try {
      await api.delete(`/workspaces/${user.workspace_id}/members/${id}`);
      toast.success("Üye çıkarıldı");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kaldırılamadı");
    }
  };

  const saveName = async () => {
    if (!wsName.trim()) return;
    try {
      await api.put(`/workspaces/${user.workspace_id}/rename`, { name: wsName.trim() });
      toast.success("Workspace adı güncellendi");
      setEditingName(false);
      refreshUser?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Güncellenemedi");
    }
  };

  return (
    <div data-testid="team-page">
      <PageHeader
        label="Ekip"
        title="Workspace & Üyeler"
        description="Muhasebecinizi veya ekip arkadaşınızı davet edin, rol bazlı erişim atayın."
        actions={
          isOwner && (
            <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
              <DialogTrigger asChild>
                <Button data-testid="invite-btn" className="bg-slate-900 hover:bg-slate-800 text-white">
                  <UserPlus className="h-4 w-4 mr-2" strokeWidth={1.75} /> Üye Davet Et
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Yeni Üye Davet Et</DialogTitle></DialogHeader>
                <div className="grid gap-3 py-2">
                  <div>
                    <Label>Email Adresi</Label>
                    <Input
                      data-testid="invite-email-input"
                      type="email"
                      placeholder="muhasebe@sirket.com"
                      value={invite.email}
                      onChange={(e) => setInvite({ ...invite, email: e.target.value })}
                    />
                    <p className="text-xs text-slate-500 mt-1.5">Kullanıcı bu email ile Google giriş yaptığında workspace'e otomatik katılır.</p>
                  </div>
                  <div>
                    <Label>Rol</Label>
                    <Select value={invite.role} onValueChange={(v) => setInvite({ ...invite, role: v })}>
                      <SelectTrigger data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="editor">Editör — Ekleme, düzenleme, silme yetkisi</SelectItem>
                        <SelectItem value="viewer">Görüntüleyici — Sadece okuma</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setInviteOpen(false)}>İptal</Button>
                  <Button data-testid="send-invite-btn" onClick={submitInvite} disabled={saving} className="bg-slate-900 hover:bg-slate-800 text-white">
                    <Mail className="h-4 w-4 mr-2" /> {saving ? "Gönderiliyor..." : "Davet Gönder"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )
        }
      />

      <Card className="border-slate-200 rounded-md shadow-none mb-6">
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500 mb-2">Aktif Workspace</p>
          {editingName ? (
            <div className="flex items-center gap-2">
              <Input value={wsName} onChange={(e) => setWsName(e.target.value)} className="max-w-md" />
              <Button size="sm" onClick={saveName} className="bg-slate-900 hover:bg-slate-800 text-white">Kaydet</Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditingName(false); setWsName(user.workspace_name); }}>İptal</Button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <p className="font-heading text-2xl font-bold" data-testid="workspace-name">{user?.workspace_name}</p>
              {isOwner && (
                <Button variant="ghost" size="icon" onClick={() => setEditingName(true)} data-testid="edit-workspace-name-btn">
                  <Pencil className="h-4 w-4" />
                </Button>
              )}
              <Badge variant="outline" className={ROLE_META[user?.role || "owner"].cls}>
                {ROLE_META[user?.role || "owner"].label}
              </Badge>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-slate-200 rounded-md shadow-none">
        <CardContent className="p-0">
          <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.12em] font-semibold text-slate-500">Üyeler</p>
              <p className="font-heading text-lg font-semibold mt-0.5">{members.length} kişi</p>
            </div>
          </div>
          <div className="divide-y divide-slate-200">
            {members.map((m) => {
              const meta = ROLE_META[m.role] || ROLE_META.viewer;
              const Icon = meta.icon;
              return (
                <div key={m.id} className="px-6 py-4 flex items-center gap-4" data-testid={`member-${m.id}`}>
                  <div className="h-10 w-10 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-semibold shrink-0">
                    {(m.name || m.email)[0]?.toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-900">{m.name || m.email}</p>
                    <p className="text-sm text-slate-500 truncate">{m.email}</p>
                  </div>
                  <Badge variant="outline" className={meta.cls}>
                    <Icon className="h-3 w-3 mr-1" strokeWidth={2} /> {meta.label}
                  </Badge>
                  {m.status === "pending" && (
                    <Badge variant="outline" className="bg-amber-50 text-amber-800 border-amber-200">Bekliyor</Badge>
                  )}
                  {isOwner && m.role !== "owner" && (
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => removeMember(m.id)}
                      data-testid={`remove-member-${m.id}`}
                    >
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
