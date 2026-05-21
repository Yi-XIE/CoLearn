import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bot,
  ChevronDown,
  ChevronLeft,
  Check,
  Eye,
  EyeOff,
  Hexagon,
  Loader2,
  LogOut,
  Orbit,
  Pencil,
  RotateCcw,
  Sparkles,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  fetchSettings,
  updateProviderSettings,
  updateSettings,
  updateWebSearchSettings,
} from "@/lib/api";
import type { SettingsPayload, WebSearchSettingsUpdate } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useClient } from "@/providers/ClientProvider";

const CORE_PROVIDER_NAMES = new Set(["openai", "openrouter", "custom", "deepseek", "siliconflow"]);

function isCoreProvider(
  provider: { name: string; configured: boolean },
  resolvedProvider?: string | null,
) {
  return (
    provider.configured ||
    CORE_PROVIDER_NAMES.has(provider.name) ||
    provider.name === resolvedProvider
  );
}

interface SettingsViewProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onBackToChat: () => void;
  onModelNameChange: (modelName: string | null) => void;
  onLogout?: () => void;
  onRestart?: () => void;
  isRestarting?: boolean;
}

export function SettingsView({
  theme,
  onToggleTheme,
  onBackToChat,
  onModelNameChange,
  onLogout,
  onRestart,
  isRestarting = false,
}: SettingsViewProps) {
  const { t } = useTranslation();
  const { token } = useClient();
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providerSaving, setProviderSaving] = useState<string | null>(null);
  const [webSearchSaving, setWebSearchSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [providerForms, setProviderForms] = useState<Record<string, { apiKey: string; apiBase: string }>>({});
  const [visibleProviderKeys, setVisibleProviderKeys] = useState<Record<string, boolean>>({});
  const [editingProviderKeys, setEditingProviderKeys] = useState<Record<string, boolean>>({});
  const [webSearchKeyVisible, setWebSearchKeyVisible] = useState(false);
  const [webSearchKeyEditing, setWebSearchKeyEditing] = useState(false);
  const [webSearchForm, setWebSearchForm] = useState<WebSearchSettingsUpdate>({
    provider: "duckduckgo",
    apiKey: "",
    baseUrl: "",
  });
  const [form, setForm] = useState({ model: "", provider: "" });

  const applyPayload = useCallback((payload: SettingsPayload) => {
    setSettings(payload);
    setForm({
      model: payload.agent.model,
      provider: payload.agent.provider,
    });
    setWebSearchForm((prev) => ({
      provider: payload.web_search.provider || prev.provider || "duckduckgo",
      apiKey: prev.provider === payload.web_search.provider ? prev.apiKey ?? "" : "",
      baseUrl: payload.web_search.base_url ?? "",
    }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchSettings(token)
      .then((payload) => {
        if (!cancelled) {
          applyPayload(payload);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyPayload, token]);

  useEffect(() => {
    if (!settings) return;
    setProviderForms((prev) => {
      const next = { ...prev };
      for (const provider of settings.providers) {
        next[provider.name] = {
          apiKey: next[provider.name]?.apiKey ?? "",
          apiBase:
            next[provider.name]?.apiBase ??
            provider.api_base ??
            provider.default_api_base ??
            "",
        };
      }
      return next;
    });
  }, [settings]);

  const dirty = useMemo(() => {
    if (!settings) return false;
    return (
      form.model !== settings.agent.model ||
      form.provider !== settings.agent.provider
    );
  }, [form, settings]);

  const save = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const payload = await updateSettings(token, {
        model: form.model,
        ...(form.provider ? { provider: form.provider } : {}),
      });
      applyPayload(payload);
      onModelNameChange(payload.agent.model || null);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const saveProvider = async (providerName: string) => {
    if (!settings || providerSaving) return;
    const provider = settings.providers.find((item) => item.name === providerName);
    if (!provider) return;
    const providerForm = providerForms[providerName] ?? { apiKey: "", apiBase: "" };
    const apiKey = providerForm.apiKey.trim();
    if (!provider.configured && !apiKey) {
      setError("新增提供方时需要填写 API Key。");
      return;
    }
    setProviderSaving(providerName);
    try {
      const payload = await updateProviderSettings(token, {
        provider: providerName,
        apiKey: apiKey || undefined,
        apiBase: providerForm.apiBase.trim(),
      });
      applyPayload(payload);
      setProviderForms((prev) => ({
        ...prev,
        [providerName]: {
          apiKey: "",
          apiBase: providerForm.apiBase.trim(),
        },
      }));
      setVisibleProviderKeys((prev) => ({ ...prev, [providerName]: false }));
      setEditingProviderKeys((prev) => ({ ...prev, [providerName]: false }));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setProviderSaving(null);
    }
  };

  const saveWebSearch = async () => {
    if (!settings || webSearchSaving) return;
    const provider = settings.web_search.providers.find((item) => item.name === webSearchForm.provider);
    if (!provider) return;
    const apiKey = webSearchForm.apiKey?.trim() ?? "";
    const baseUrl = webSearchForm.baseUrl?.trim() ?? "";
    const hasExistingSecret =
      provider.credential === "api_key" &&
      webSearchForm.provider === settings.web_search.provider &&
      !!settings.web_search.api_key_hint;

    if (provider.credential === "api_key" && !apiKey && !hasExistingSecret) {
      setError(t("settings.byok.webSearch.apiKeyRequired"));
      return;
    }
    if (provider.credential === "base_url" && !baseUrl) {
      setError(t("settings.byok.webSearch.baseUrlRequired"));
      return;
    }

    setWebSearchSaving(true);
    try {
      const update: WebSearchSettingsUpdate = { provider: webSearchForm.provider };
      if (provider.credential === "api_key" && apiKey) update.apiKey = apiKey;
      if (provider.credential === "base_url") update.baseUrl = baseUrl;
      const payload = await updateWebSearchSettings(token, update);
      applyPayload(payload);
      setWebSearchForm({
        provider: payload.web_search.provider || webSearchForm.provider,
        apiKey: "",
        baseUrl: payload.web_search.base_url ?? "",
      });
      setWebSearchKeyVisible(false);
      setWebSearchKeyEditing(false);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWebSearchSaving(false);
    }
  };

  const preferredProviders = useMemo(
    () =>
      settings?.providers.filter((provider) =>
        isCoreProvider(provider, settings.agent.resolved_provider),
      ) ?? [],
    [settings],
  );

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_50%_0%,hsl(var(--muted))_0%,hsl(var(--background))_42%)]">
      <main className="min-w-0 flex-1 overflow-y-auto [scrollbar-gutter:stable]">
        <div className="mx-auto w-full max-w-[840px] px-6 py-10 sm:px-10 lg:py-14">
          <button
            type="button"
            onClick={onBackToChat}
            className="mb-4 inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
            {t("settings.backToChat")}
          </button>

          <div className="mb-8">
            <h1 className="text-[32px] font-bold leading-tight tracking-[-0.03em] text-black dark:text-white sm:text-[40px]">
              设置
            </h1>
          </div>

          {loading ? (
            <div className="flex h-48 items-center justify-center rounded-[24px] border border-border/50 bg-card/75 text-sm text-muted-foreground shadow-[0_20px_70px_rgba(15,23,42,0.07)]">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t("settings.status.loading")}
            </div>
          ) : error && !settings ? (
            <SettingsGroup>
              <SettingsRow title={t("settings.status.loadError")}>
                <span className="max-w-[520px] text-sm text-muted-foreground">
                  {error}
                </span>
              </SettingsRow>
            </SettingsGroup>
          ) : settings ? (
            <div className="space-y-5">
              {error ? (
                <div className="rounded-[18px] border border-destructive/20 bg-destructive/5 px-4 py-3 text-[13px] text-destructive">
                  {error}
                </div>
              ) : null}

              <section className="space-y-2">
                <SettingsSectionTitle>{t("settings.sections.ai")}</SettingsSectionTitle>
                <SettingsGroup>
                  <SettingsRow
                    title={t("settings.rows.provider")}
                    description={t("settings.help.provider")}
                  >
                    <ProviderPicker
                      providers={preferredProviders}
                      value={preferredProviders.some((p) => p.name === form.provider) ? form.provider : ""}
                      emptyLabel={t("settings.values.notAvailable")}
                      onChange={(provider) =>
                        setForm((prev) => ({ ...prev, provider }))
                      }
                    />
                  </SettingsRow>
                  <SettingsRow
                    title={t("settings.rows.model")}
                    description={t("settings.help.model")}
                  >
                    <Input
                      value={form.model}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, model: event.target.value }))
                      }
                      className="h-8 w-[280px] rounded-full text-[13px]"
                    />
                  </SettingsRow>
                  {(dirty || saving || settings.requires_restart) ? (
                    <SettingsFooter
                      dirty={dirty}
                      saving={saving}
                      saved={settings.requires_restart && !dirty}
                      onSave={save}
                    />
                  ) : null}
                </SettingsGroup>
              </section>

              <section className="space-y-3">
                <SettingsSectionTitle>{t("settings.byok.tabs.webSearch")}</SettingsSectionTitle>
                <WebSearchSettingsPanel
                  settings={settings}
                  form={webSearchForm}
                  keyVisible={webSearchKeyVisible}
                  keyEditing={webSearchKeyEditing}
                  saving={webSearchSaving}
                  onChangeProvider={(provider) =>
                    setWebSearchForm((prev) => ({
                      provider,
                      apiKey: "",
                      baseUrl: provider === settings.web_search.provider ? settings.web_search.base_url ?? "" : "",
                    }))
                  }
                  onChangeApiKey={(apiKey) =>
                    setWebSearchForm((prev) => ({ ...prev, apiKey }))
                  }
                  onChangeBaseUrl={(baseUrl) =>
                    setWebSearchForm((prev) => ({ ...prev, baseUrl }))
                  }
                  onToggleKey={() => setWebSearchKeyVisible((prev) => !prev)}
                  onToggleKeyEditing={() => setWebSearchKeyEditing((prev) => !prev)}
                  onSave={saveWebSearch}
                />
              </section>

              <section className="space-y-3">
                <SettingsSectionTitle>连接</SettingsSectionTitle>
                <div className="px-1 text-[12px] leading-5 text-muted-foreground">
                  当前只保留与本地学习工作流直接相关的模型连接。
                </div>
                <ProviderConnectionsPanel
                  providers={preferredProviders}
                  expandedProvider={expandedProvider}
                  providerForms={providerForms}
                  visibleProviderKeys={visibleProviderKeys}
                  editingProviderKeys={editingProviderKeys}
                  providerSaving={providerSaving}
                  onToggleProvider={(providerName) =>
                    setExpandedProvider((current) =>
                      current === providerName ? null : providerName,
                    )
                  }
                  onToggleProviderKey={(providerName) =>
                    setVisibleProviderKeys((prev) => ({
                      ...prev,
                      [providerName]: !prev[providerName],
                    }))
                  }
                  onToggleProviderKeyEditing={(providerName) =>
                    setEditingProviderKeys((prev) => ({
                      ...prev,
                      [providerName]: !prev[providerName],
                    }))
                  }
                  onChangeProviderForm={(providerName, value) =>
                    setProviderForms((prev) => ({
                      ...prev,
                      [providerName]: {
                        apiKey: prev[providerName]?.apiKey ?? "",
                        apiBase: prev[providerName]?.apiBase ?? "",
                        ...value,
                      },
                    }))
                  }
                  onSaveProvider={saveProvider}
                />
              </section>

              <section className="space-y-2">
                <SettingsSectionTitle>{t("settings.sections.system")}</SettingsSectionTitle>
                <SettingsGroup>
                  <SettingsRow
                    title={t("settings.rows.configPath")}
                    description={t("settings.help.configPath")}
                  >
                    <code className="max-w-[320px] overflow-hidden text-ellipsis whitespace-nowrap rounded-full bg-muted px-3 py-1.5 text-[12px] text-muted-foreground">
                      {settings.runtime.config_path || t("settings.values.notAvailable")}
                    </code>
                  </SettingsRow>
                  {onRestart ? (
                    <SettingsRow
                      title={t("app.system.restart")}
                      description={t("app.system.restartHint")}
                    >
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={onRestart}
                        disabled={isRestarting}
                        className="rounded-full"
                      >
                        {isRestarting ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                        ) : (
                          <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                        )}
                        {isRestarting ? t("app.system.restarting") : t("app.system.restart")}
                      </Button>
                    </SettingsRow>
                  ) : null}
                </SettingsGroup>
              </section>

              {onLogout ? (
                <section className="space-y-2">
                  <SettingsSectionTitle>账户</SettingsSectionTitle>
                  <SettingsGroup>
                    <SettingsRow
                      title={t("app.account.logout")}
                      description="将当前浏览器与当前 CoLearn 会话断开。"
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={onLogout}
                        className="h-9 rounded-full px-3 text-[13px] font-medium text-muted-foreground hover:bg-destructive/8 hover:text-destructive"
                      >
                        <LogOut className="mr-1.5 h-4 w-4" aria-hidden />
                        {t("app.account.logout")}
                      </Button>
                    </SettingsRow>
                  </SettingsGroup>
                </section>
              ) : null}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}

function ProviderPicker({
  providers,
  value,
  emptyLabel,
  onChange,
}: {
  providers: Array<{ name: string; label: string }>;
  value: string;
  emptyLabel: string;
  onChange: (provider: string) => void;
}) {
  const selectedProvider = providers.find((provider) => provider.name === value) ?? null;
  const disabled = providers.length === 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled}>
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          className={cn(
            "h-8 w-[210px] justify-between rounded-full border-input bg-background px-3 text-[13px] font-normal shadow-none",
            "hover:bg-accent/55 focus-visible:ring-2 focus-visible:ring-ring",
            disabled && "text-muted-foreground",
          )}
        >
          <span className="truncate">{selectedProvider?.label ?? emptyLabel}</span>
          <ChevronDown className="ml-2 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="max-h-[18rem] w-[240px] overflow-y-auto rounded-[18px] border-border/65 bg-popover p-1.5 text-popover-foreground shadow-[0_18px_55px_rgba(15,23,42,0.18)]"
      >
        {providers.map((provider) => {
          const selected = provider.name === value;
          return (
            <DropdownMenuItem
              key={provider.name}
              onSelect={() => onChange(provider.name)}
              className={cn(
                "flex cursor-default items-center justify-between gap-2 rounded-[12px] px-3 py-2 text-[13px]",
                "focus:bg-muted focus:text-foreground",
                selected && "bg-primary/10 text-primary focus:bg-primary/12 focus:text-primary",
              )}
            >
              <span className="truncate">{provider.label}</span>
              {selected ? <Check className="h-3.5 w-3.5 shrink-0" aria-hidden /> : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ProviderConnectionsPanel({
  providers,
  expandedProvider,
  providerForms,
  visibleProviderKeys,
  editingProviderKeys,
  providerSaving,
  onToggleProvider,
  onToggleProviderKey,
  onToggleProviderKeyEditing,
  onChangeProviderForm,
  onSaveProvider,
}: {
  providers: SettingsPayload["providers"];
  expandedProvider: string | null;
  providerForms: Record<string, { apiKey: string; apiBase: string }>;
  visibleProviderKeys: Record<string, boolean>;
  editingProviderKeys: Record<string, boolean>;
  providerSaving: string | null;
  onToggleProvider: (provider: string) => void;
  onToggleProviderKey: (provider: string) => void;
  onToggleProviderKeyEditing: (provider: string) => void;
  onChangeProviderForm: (provider: string, value: Partial<{ apiKey: string; apiBase: string }>) => void;
  onSaveProvider: (provider: string) => void;
}) {
  const { t } = useTranslation();
  const configuredProviders = providers.filter((provider) => provider.configured);
  const secondaryProviders = providers.filter((provider) => !provider.configured);

  const renderProviderRow = (provider: SettingsPayload["providers"][number]) => {
    const expanded = expandedProvider === provider.name;
    const form = providerForms[provider.name] ?? {
      apiKey: "",
      apiBase: provider.api_base ?? provider.default_api_base ?? "",
    };
    const saving = providerSaving === provider.name;
    const keyVisible = !!visibleProviderKeys[provider.name];
    const editingKey = !provider.configured || !!editingProviderKeys[provider.name];

    return (
      <div key={provider.name} className="divide-y divide-border/45">
        <button
          type="button"
          onClick={() => onToggleProvider(provider.name)}
          className="flex min-h-[70px] w-full items-center justify-between gap-4 px-4 py-3 text-left transition-colors hover:bg-muted/35 sm:px-5"
        >
          <span className="flex min-w-0 items-center gap-3">
            <ProviderIcon provider={provider.name} />
            <span className="block truncate text-[15px] font-semibold leading-5 text-foreground">
              {provider.label}
            </span>
          </span>
          <span
            className={cn(
              "rounded-full px-2.5 py-1 text-[12px] font-medium",
              provider.configured
                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                : "bg-muted text-muted-foreground",
            )}
          >
            {provider.configured ? t("settings.byok.configured") : t("settings.byok.notConfigured")}
          </span>
        </button>

        {expanded ? (
          <div className="space-y-3 bg-muted/18 px-4 py-4 sm:px-5">
            <label className="block space-y-1.5">
              <span className="text-[12px] font-medium text-muted-foreground">
                {t("settings.byok.apiKey")}
              </span>
              <div className="relative">
                {editingKey ? (
                  <>
                    <Input
                      type={keyVisible ? "text" : "password"}
                      value={form.apiKey}
                      onChange={(event) =>
                        onChangeProviderForm(provider.name, { apiKey: event.target.value })
                      }
                      placeholder={
                        provider.configured
                          ? t("settings.byok.apiKeyConfiguredPlaceholder")
                          : t("settings.byok.apiKeyPlaceholder")
                      }
                      className="h-9 rounded-full pr-11 text-[13px]"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => onToggleProviderKey(provider.name)}
                      aria-label={
                        keyVisible
                          ? t("settings.byok.hideApiKey")
                          : t("settings.byok.showApiKey")
                      }
                      className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      {keyVisible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </Button>
                  </>
                ) : (
                  <>
                    <div className="flex h-9 items-center rounded-full border border-input bg-background px-3 pr-11 text-[13px] text-muted-foreground">
                      {provider.api_key_hint ?? t("settings.byok.configuredKeyHint")}
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => onToggleProviderKeyEditing(provider.name)}
                      aria-label={t("settings.actions.edit")}
                      className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  </>
                )}
              </div>
            </label>

            <label className="block space-y-1.5">
              <span className="text-[12px] font-medium text-muted-foreground">
                {t("settings.byok.apiBase")}
              </span>
              <Input
                value={form.apiBase}
                onChange={(event) =>
                  onChangeProviderForm(provider.name, { apiBase: event.target.value })
                }
                placeholder={provider.default_api_base ?? t("settings.byok.apiBasePlaceholder")}
                className="h-9 rounded-full text-[13px]"
              />
            </label>

            <div className="flex items-center justify-end">
              <Button
                size="sm"
                variant="outline"
                onClick={() => onSaveProvider(provider.name)}
                disabled={saving || (!provider.configured && !form.apiKey.trim())}
                className="rounded-full"
              >
                {saving ? t("settings.actions.saving") : t("settings.actions.save")}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <ByokSectionHeader title="已配置提供方" count={configuredProviders.length} />
        <div className="overflow-hidden rounded-[22px] border border-border/45 bg-card/86 shadow-[0_18px_65px_rgba(15,23,42,0.07)]">
          {configuredProviders.length > 0 ? (
            <div className="divide-y divide-border/45">
              {configuredProviders.map(renderProviderRow)}
            </div>
          ) : (
            <ByokEmptyState>当前还没有保存的提供方凭据。</ByokEmptyState>
          )}
        </div>
      </section>

      {secondaryProviders.length > 0 ? (
        <section className="space-y-3">
          <ByokSectionHeader title="可用预设" count={secondaryProviders.length} />
          <div className="overflow-hidden rounded-[22px] border border-border/45 bg-card/86 shadow-[0_18px_65px_rgba(15,23,42,0.07)]">
            <div className="divide-y divide-border/45">
              {secondaryProviders.map(renderProviderRow)}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function WebSearchSettingsPanel({
  settings,
  form,
  keyVisible,
  keyEditing,
  saving,
  onChangeProvider,
  onChangeApiKey,
  onChangeBaseUrl,
  onToggleKey,
  onToggleKeyEditing,
  onSave,
}: {
  settings: SettingsPayload;
  form: WebSearchSettingsUpdate;
  keyVisible: boolean;
  keyEditing: boolean;
  saving: boolean;
  onChangeProvider: (provider: string) => void;
  onChangeApiKey: (apiKey: string) => void;
  onChangeBaseUrl: (baseUrl: string) => void;
  onToggleKey: () => void;
  onToggleKeyEditing: () => void;
  onSave: () => void;
}) {
  const { t } = useTranslation();
  const selectedProvider =
    settings.web_search.providers.find((provider) => provider.name === form.provider)
    ?? settings.web_search.providers[0]
    ?? null;
  const hasExistingSecret =
    selectedProvider?.credential === "api_key"
    && form.provider === settings.web_search.provider
    && !!settings.web_search.api_key_hint;
  const showKeyInput = selectedProvider?.credential === "api_key" && (!hasExistingSecret || keyEditing);
  const apiKey = form.apiKey?.trim() ?? "";
  const baseUrl = form.baseUrl?.trim() ?? "";
  const dirty =
    form.provider !== settings.web_search.provider
    || apiKey.length > 0
    || baseUrl !== (settings.web_search.base_url ?? "");
  const missingCredential =
    selectedProvider?.credential === "api_key"
      ? !apiKey && !hasExistingSecret
      : selectedProvider?.credential === "base_url"
        ? !baseUrl
        : false;

  return (
    <SettingsGroup>
      <SettingsRow
        title={t("settings.byok.webSearch.provider")}
        description={t("settings.byok.webSearch.providerHelp")}
      >
        <ProviderPicker
          providers={settings.web_search.providers}
          value={form.provider}
          emptyLabel={t("settings.byok.webSearch.selectProvider")}
          onChange={onChangeProvider}
        />
      </SettingsRow>

      {selectedProvider?.credential === "none" ? (
        <SettingsRow
          title={t("settings.byok.webSearch.credentials")}
          description={t("settings.byok.webSearch.noCredentialHelp")}
        >
          <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[12px] font-medium text-emerald-700 dark:text-emerald-300">
            {t("settings.byok.webSearch.noCredentialRequired")}
          </span>
        </SettingsRow>
      ) : null}

      {selectedProvider?.credential === "api_key" ? (
        <SettingsRow
          title={t("settings.byok.apiKey")}
          description={t("settings.byok.webSearch.apiKeyHelp")}
        >
          <div className="relative w-[280px] max-w-full">
            {showKeyInput ? (
              <>
                <Input
                  type={keyVisible ? "text" : "password"}
                  value={form.apiKey ?? ""}
                  onChange={(event) => onChangeApiKey(event.target.value)}
                  placeholder={
                    hasExistingSecret
                      ? t("settings.byok.apiKeyConfiguredPlaceholder")
                      : t("settings.byok.apiKeyPlaceholder")
                  }
                  className="h-9 rounded-full pr-11 text-[13px]"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={onToggleKey}
                  aria-label={
                    keyVisible ? t("settings.byok.hideApiKey") : t("settings.byok.showApiKey")
                  }
                  className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  {keyVisible ? (
                    <EyeOff className="h-3.5 w-3.5" aria-hidden />
                  ) : (
                    <Eye className="h-3.5 w-3.5" aria-hidden />
                  )}
                </Button>
              </>
            ) : (
              <>
                <div className="flex h-9 items-center rounded-full border border-input bg-background px-3 pr-11 text-[13px] text-muted-foreground">
                  {settings.web_search.api_key_hint ?? t("settings.byok.configuredKeyHint")}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={onToggleKeyEditing}
                  aria-label={t("settings.actions.edit")}
                  className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden />
                </Button>
              </>
            )}
          </div>
        </SettingsRow>
      ) : null}

      {selectedProvider?.credential === "base_url" ? (
        <SettingsRow
          title={t("settings.byok.webSearch.baseUrl")}
          description={t("settings.byok.webSearch.baseUrlHelp")}
        >
          <Input
            value={form.baseUrl ?? ""}
            onChange={(event) => onChangeBaseUrl(event.target.value)}
            placeholder={t("settings.byok.webSearch.baseUrlPlaceholder")}
            className="h-9 w-[280px] rounded-full text-[13px]"
          />
        </SettingsRow>
      ) : null}

      <div className="flex min-h-[58px] items-center justify-between gap-4 px-4 py-3 sm:px-5">
        <div className="text-[13px] text-muted-foreground">
          {missingCredential
            ? t("settings.byok.webSearch.missingCredential")
            : t("settings.byok.webSearch.saveHint")}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={onSave}
          disabled={!dirty || missingCredential || saving}
          className="rounded-full"
        >
          {saving ? t("settings.actions.saving") : t("settings.actions.save")}
        </Button>
      </div>
    </SettingsGroup>
  );
}

function ByokSectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="flex items-center justify-between px-1">
      <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-foreground/85">
        {title}
      </h2>
      <span className="rounded-full bg-muted px-2 py-0.5 text-[11.5px] font-medium text-muted-foreground">
        {count}
      </span>
    </div>
  );
}

function ByokEmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[18px] border border-dashed border-border/65 bg-card/45 px-4 py-5 text-[13px] text-muted-foreground">
      {children}
    </div>
  );
}

const PROVIDER_ICONS: Record<string, LucideIcon> = {
  custom: Hexagon,
  openrouter: Sparkles,
  openai: Bot,
  deepseek: Waves,
  siliconflow: Orbit,
};

function ProviderIcon({ provider }: { provider: string }) {
  const Icon = PROVIDER_ICONS[provider] ?? Hexagon;
  return (
    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-muted text-foreground/82 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.025)]">
      <Icon className="h-5 w-5" strokeWidth={2} aria-hidden />
    </span>
  );
}

function SettingsSectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="px-1 text-[13px] font-semibold tracking-[-0.01em] text-foreground/85">
      {children}
    </h2>
  );
}

function SettingsGroup({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-[22px] border border-border/45 bg-card/86 shadow-[0_18px_65px_rgba(15,23,42,0.075)]">
      <div className="divide-y divide-border/45">{children}</div>
    </div>
  );
}

function SettingsRow({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-[62px] flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="min-w-0">
        <div className="text-[14px] font-medium leading-5 text-foreground">{title}</div>
        {description ? (
          <div className="mt-0.5 max-w-[28rem] text-[12px] leading-5 text-muted-foreground">
            {description}
          </div>
        ) : null}
      </div>
      {children ? <div className="shrink-0 sm:ml-6">{children}</div> : null}
    </div>
  );
}

function SettingsFooter({
  dirty,
  saving,
  saved,
  onSave,
}: {
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  onSave: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-[58px] items-center justify-between gap-4 px-4 py-3 sm:px-5">
      <div className="text-[13px] text-muted-foreground">
        {saved ? t("settings.status.savedRestart") : t("settings.status.unsaved")}
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={onSave}
        disabled={!dirty || saving}
        className="rounded-full"
      >
        {saving ? t("settings.actions.saving") : t("settings.actions.save")}
      </Button>
    </div>
  );
}
