"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Loader2, Send } from "lucide-react";

import { api } from "@/lib/api";
import type { AlertSeverity, NotificationSettings } from "@/lib/types";
import { alertLabel } from "@/lib/alerts";
import { EmptyState } from "@/components/ui/EmptyState";

const SEVERITIES: AlertSeverity[] = ["info", "watch", "warning", "critical"];

const EVENT_TYPES = [
  "xray_flare",
  "radio_burst",
  "proton_event",
  "geomagnetic_storm_kp",
  "geomagnetic_storm_dst",
  "geomagnetic_storm_prediction",
  "cme",
];

type Draft = Omit<NotificationSettings, "telegram_token_configured" | "updated_at">;

const inputCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1.5 text-sm text-slate-300 outline-none focus:border-accent-blue";

function Toggle({
  checked,
  onChange,
  disabled,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
  hint?: string;
}) {
  return (
    <label
      className={clsx(
        "flex items-start gap-3",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-[var(--accent-blue,#3b82f6)]"
      />
      <span>
        <span className="block text-sm text-slate-200">{label}</span>
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </span>
    </label>
  );
}

/**
 * Alert delivery preferences: push qualifying alerts to Telegram / a webhook.
 * The Telegram bot token is server-side (.env); this card stores only routing
 * (chat id / URL) and filtering, and can fire a test message.
 */
export function NotificationSettingsCard() {
  const { data, mutate, error } = useSWR("notification-settings", api.notificationSettings);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  // Success and failure used to render through one neutral grey span, so
  // "Saved." and "Save failed: connection refused" looked identical.
  const [statusTone, setStatusTone] = useState<"ok" | "error" | "neutral">("neutral");

  useEffect(() => {
    if (data && draft === null) {
      setDraft({
        telegram_enabled: data.telegram_enabled,
        telegram_chat_id: data.telegram_chat_id,
        webhook_enabled: data.webhook_enabled,
        webhook_url: data.webhook_url,
        min_severity: data.min_severity,
        event_types: data.event_types,
      });
    }
  }, [data, draft]);

  // `error` was previously unread, so a failed settings fetch left this card
  // pulsing forever with no explanation.
  if (error) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-200">Alert Notifications</h2>
        <EmptyState
          tone="error"
          message="Couldn't load notification settings. Your saved preferences are unchanged."
        />
      </section>
    );
  }

  if (!data || !draft) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="text-sm font-semibold text-slate-200">Alert Notifications</h2>
        <div className="mt-4 h-24 animate-pulse rounded bg-surface-muted" />
      </section>
    );
  }

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));

  const toggleType = (t: string) =>
    set(
      "event_types",
      draft.event_types.includes(t)
        ? draft.event_types.filter((x) => x !== t)
        : [...draft.event_types, t]
    );

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const updated = await api.saveNotificationSettings(draft);
      await mutate(updated, { revalidate: false });
      setStatus("Saved.");
      setStatusTone("ok");
    } catch (e) {
      setStatus(`Save failed: ${e instanceof Error ? e.message : e}`);
      setStatusTone("error");
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setStatus(null);
    try {
      const res = await api.testNotifications();
      const parts: string[] = [];
      if (res.telegram) parts.push(`Telegram: ${res.telegram.ok ? "OK ✓" : res.telegram.error}`);
      if (res.webhook) parts.push(`Webhook: ${res.webhook.ok ? "OK ✓" : res.webhook.error}`);
      setStatus(parts.length ? parts.join(" · ") : "No channel enabled — save first.");
      // A channel that reported an error is a failure even though the request
      // itself succeeded, so tone follows the per-channel results.
      const anyFailed =
        (res.telegram && !res.telegram.ok) || (res.webhook && !res.webhook.ok);
      setStatusTone(!parts.length ? "neutral" : anyFailed ? "error" : "ok");
    } catch (e) {
      setStatus(`Test failed: ${e instanceof Error ? e.message : e}`);
      setStatusTone("error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-5">
      <h2 className="text-sm font-semibold text-slate-200">Alert Notifications</h2>
      <p className="mt-1 text-xs text-slate-500">
        Push qualifying alerts to your phone or another service. Only events that
        occur <em>after</em> enabling are delivered.
      </p>

      <div className="mt-4 space-y-4">
        {/* Telegram */}
        <div className="rounded border border-surface-border bg-surface-muted/30 p-3">
          <Toggle
            checked={draft.telegram_enabled}
            onChange={(v) => set("telegram_enabled", v)}
            disabled={!data.telegram_token_configured}
            label="Telegram"
            hint={
              data.telegram_token_configured
                ? "Message a bot you created with @BotFather."
                : "Set TELEGRAM_BOT_TOKEN in the backend .env to enable this channel."
            }
          />
          {draft.telegram_enabled && (
            <div className="mt-2 pl-7">
              <label className="text-xs text-slate-500">
                Chat ID
                <input
                  value={draft.telegram_chat_id}
                  onChange={(e) => set("telegram_chat_id", e.target.value)}
                  placeholder="e.g. 123456789 (send /start to @userinfobot)"
                  className={clsx(inputCls, "mt-1")}
                />
              </label>
            </div>
          )}
        </div>

        {/* Webhook */}
        <div className="rounded border border-surface-border bg-surface-muted/30 p-3">
          <Toggle
            checked={draft.webhook_enabled}
            onChange={(v) => set("webhook_enabled", v)}
            label="Webhook"
            hint="POST each alert as JSON — works with Discord/Slack bridges, ntfy, Home Assistant, or anything custom."
          />
          {draft.webhook_enabled && (
            <div className="mt-2 pl-7">
              <label className="text-xs text-slate-500">
                URL
                <input
                  value={draft.webhook_url}
                  onChange={(e) => set("webhook_url", e.target.value)}
                  placeholder="https://…"
                  className={clsx(inputCls, "mt-1")}
                />
              </label>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="text-xs text-slate-500">
            Minimum severity
            <select
              value={draft.min_severity}
              onChange={(e) => set("min_severity", e.target.value as AlertSeverity)}
              className={clsx(inputCls, "mt-1 capitalize")}
            >
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="text-xs text-slate-500">
            Event types ({draft.event_types.length === 0 ? "all" : draft.event_types.length})
            <div className="mt-1 grid grid-cols-1 gap-1 rounded border border-surface-border bg-surface-muted/30 p-2 sm:grid-cols-2">
              {EVENT_TYPES.map((t) => (
                <label key={t} className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
                  <input
                    type="checkbox"
                    checked={draft.event_types.length === 0 || draft.event_types.includes(t)}
                    onChange={() =>
                      draft.event_types.length === 0
                        ? set("event_types", EVENT_TYPES.filter((x) => x !== t))
                        : toggleType(t)
                    }
                    className="h-3.5 w-3.5"
                  />
                  {alertLabel(t)}
                </label>
              ))}
            </div>
            <p className="mt-1 text-[10px] text-slate-600">
              Unchecking everything re-enables all types.
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 rounded bg-accent-blue px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-blue/80 disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save
          </button>
          <button
            onClick={test}
            disabled={testing || (!data.telegram_enabled && !data.webhook_enabled)}
            title="Sends to the last *saved* settings"
            className="flex items-center gap-2 rounded border border-surface-border px-4 py-1.5 text-sm text-slate-300 hover:bg-surface-muted disabled:opacity-50"
          >
            {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            Send test
          </button>
          {status && (
            <span
              role="status"
              aria-live="polite"
              className={clsx(
                "text-xs",
                statusTone === "ok"
                  ? "text-accent-green"
                  : statusTone === "error"
                    ? "text-accent-red"
                    : "text-slate-400"
              )}
            >
              {status}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
