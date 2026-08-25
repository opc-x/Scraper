import * as React from "react";
import { Plus, Trash2, Send, CheckCircle2, XCircle } from "lucide-react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import type { TelegramAccount } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";

type AccountStatus = "unknown" | "not_logged_in" | "logged_in" | "session_expired" | "error";

function LoginFlow({ accountId, onDone }: { accountId: number; onDone: () => void }) {
  const [stage, setStage] = React.useState<"idle" | "code_sent" | "need_2fa">("idle");
  const [code, setCode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const toast = useToast();

  const sendCode = async () => {
    setBusy(true);
    try {
      await apiPost(`/api/telegram/accounts/${accountId}/send-code`);
      setStage("code_sent");
      toast("验证码已发送");
    } catch {
      toast("发送验证码失败", "error");
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      const res = await apiPost<{ ok: boolean; need_2fa?: boolean }>(`/api/telegram/accounts/${accountId}/verify-code`, {
        code,
        password,
      });
      if (res.need_2fa) {
        setStage("need_2fa");
        return;
      }
      toast("登录成功");
      onDone();
    } catch {
      toast("验证失败", "error");
    } finally {
      setBusy(false);
    }
  };

  if (stage === "idle") {
    return (
      <Button variant="outline" size="sm" disabled={busy} onClick={sendCode} className="gap-1.5">
        <Send size={13} /> 发送验证码
      </Button>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <Input placeholder="验证码" value={code} onChange={(e) => setCode(e.target.value)} className="h-8 text-sm" />
      {stage === "need_2fa" && (
        <Input
          placeholder="两步验证密码"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-8 text-sm"
        />
      )}
      <Button size="sm" disabled={busy || !code} onClick={verify}>
        确认登录
      </Button>
    </div>
  );
}

function AccountRow({ account, onDeleted }: { account: TelegramAccount; onDeleted: () => void }) {
  const [status, setStatus] = React.useState<AccountStatus>("unknown");
  const [showLogin, setShowLogin] = React.useState(false);
  const toast = useToast();

  const checkStatus = React.useCallback(() => {
    apiGet<{ status: AccountStatus }>(`/api/telegram/accounts/${account.id}/status`).then((res) =>
      setStatus(res.status),
    );
  }, [account.id]);

  React.useEffect(() => checkStatus(), [checkStatus]);

  const remove = async () => {
    try {
      await apiDelete(`/api/telegram/accounts/${account.id}`);
      toast("已删除");
      onDeleted();
    } catch {
      toast("删除失败", "error");
    }
  };

  return (
    <div className="rounded-[var(--radius-md)] border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{account.label}</p>
          <p className="truncate text-xs text-muted-foreground">{account.phone}</p>
        </div>
        <div className="flex items-center gap-2">
          {status === "logged_in" ? (
            <Badge variant="default" className="gap-1">
              <CheckCircle2 size={12} /> 已登录
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1 text-muted-foreground">
              <XCircle size={12} /> 未登录
            </Badge>
          )}
          <Button variant="ghost" size="icon-sm" onClick={remove} aria-label="删除账号">
            <Trash2 size={14} />
          </Button>
        </div>
      </div>
      {status !== "logged_in" && (
        <div className="mt-2">
          {showLogin ? (
            <LoginFlow accountId={account.id} onDone={() => (checkStatus(), setShowLogin(false))} />
          ) : (
            <Button variant="outline" size="sm" onClick={() => setShowLogin(true)}>
              登录
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export function TelegramAccountManager() {
  const [accounts, setAccounts] = React.useState<TelegramAccount[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [showAdd, setShowAdd] = React.useState(false);
  const [form, setForm] = React.useState({ label: "", phone: "", api_id: "", api_hash: "" });
  const toast = useToast();

  const load = React.useCallback(() => {
    setLoading(true);
    apiGet<{ accounts: TelegramAccount[] }>("/api/telegram/accounts")
      .then((res) => setAccounts(res.accounts))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => load(), [load]);

  const addAccount = async () => {
    if (!form.label || !form.phone || !form.api_id || !form.api_hash) {
      toast("请填完整", "error");
      return;
    }
    try {
      await apiPost("/api/telegram/accounts", form);
      toast("账号已添加");
      setForm({ label: "", phone: "", api_id: "", api_hash: "" });
      setShowAdd(false);
      load();
    } catch {
      toast("添加失败", "error");
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Telegram 账号</h4>
      {!loading && accounts.map((a) => <AccountRow key={a.id} account={a} onDeleted={load} />)}
      {!loading && accounts.length === 0 && !showAdd && (
        <p className="text-sm text-muted-foreground">还没有 Telegram 账号</p>
      )}

      {showAdd ? (
        <div className="flex flex-col gap-2 rounded-[var(--radius-md)] border border-border bg-card p-3">
          <Input placeholder="标签，比如「主号」" value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} className="h-9 text-sm" />
          <Input placeholder="手机号，含区号，比如 +8613800001111" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} className="h-9 text-sm" />
          <Input placeholder="API ID" value={form.api_id} onChange={(e) => setForm((f) => ({ ...f, api_id: e.target.value }))} className="h-9 text-sm" />
          <Input placeholder="API Hash" value={form.api_hash} onChange={(e) => setForm((f) => ({ ...f, api_hash: e.target.value }))} className="h-9 text-sm" />
          <div className="flex gap-2">
            <Button size="sm" onClick={addAccount} className="flex-1">
              保存
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>
              取消
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="outline" size="sm" onClick={() => setShowAdd(true)} className="gap-1.5">
          <Plus size={14} /> 添加账号
        </Button>
      )}
    </div>
  );
}
