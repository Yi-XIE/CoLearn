import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  BrainCircuit,
  Check,
  ChevronDown,
  Clock3,
  Database,
  Github,
  Image,
  Loader2,
  PenTool,
  Search,
  Sparkle,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { fetchSkillDetail, listSkills } from "@/lib/api";
import type { SkillDetail, SkillSummary } from "@/lib/types";

import { PanelView, type PanelShellProps } from "./PanelView";

type SkillWithMeta = SkillSummary & {
  category: "system" | "personal";
  recommended: boolean;
};

function SkillLibraryNotice({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card/90 px-4 py-5 text-sm text-muted-foreground">
      {text}
    </div>
  );
}

function toTitle(value: string) {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getSkillIcon(skill: SkillSummary) {
  const haystack = `${skill.name} ${skill.description} ${(skill.tags ?? []).join(" ")}`.toLowerCase();
  if (haystack.includes("colearn") || haystack.includes("data")) return Database;
  if (haystack.includes("image") || haystack.includes("图片") || haystack.includes("图像")) return Image;
  if (haystack.includes("github")) return Github;
  if (haystack.includes("cron") || haystack.includes("schedule") || haystack.includes("reminder")) return Clock3;
  if (haystack.includes("feynman") || haystack.includes("socratic") || haystack.includes("pedagogy")) return BrainCircuit;
  if (haystack.includes("create") || haystack.includes("creator") || haystack.includes("edit")) return PenTool;
  if (haystack.includes("doc") || haystack.includes("markdown") || haystack.includes("pdf")) return BookOpen;
  if (haystack.includes("tool") || haystack.includes("install")) return Wrench;
  return Sparkle;
}

function skillPreview(content: string) {
  return content
    .replace(/^---[\s\S]*?---\s*/m, "")
    .replace(/^#\s+.+\n+/, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function SkillRow({
  skill,
  onOpen,
}: {
  skill: SkillWithMeta;
  onOpen: (skill: SkillWithMeta) => void;
}) {
  const Icon = getSkillIcon(skill);
  const description = skill.description || "这个技能已接入运行时，可在学习对话里被调用。";

  return (
    <button
      type="button"
      onClick={() => onOpen(skill)}
      className="group flex min-h-[76px] w-full items-center gap-3 rounded-lg border border-transparent px-3 py-3 text-left transition hover:border-border/70 hover:bg-[#F7F7F6] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-white text-slate-950 shadow-[0_1px_4px_rgba(15,23,42,0.05)]">
        <Icon className="h-5 w-5" strokeWidth={1.8} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold leading-5 text-foreground">
          {toTitle(skill.name)}
          <span className="sr-only">{skill.name}</span>
        </div>
        <div className="mt-0.5 line-clamp-1 text-sm leading-5 text-muted-foreground">
          {description}
        </div>
      </div>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-foreground transition group-hover:bg-white group-hover:text-foreground">
        <Check className="h-4 w-4" aria-hidden />
      </div>
    </button>
  );
}

interface SkillsPanelProps extends PanelShellProps {
  token: string;
}

export function SkillsPanel({ token, ...panelProps }: SkillsPanelProps) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "recommended" | "system" | "personal">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillWithMeta | null>(null);
  const [skillDetail, setSkillDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const filterOptions = [
    { value: "all", label: "全部" },
    { value: "recommended", label: "推荐" },
    { value: "system", label: "系统" },
    { value: "personal", label: "个人" },
  ] as const;
  const activeFilterLabel = filterOptions.find((option) => option.value === filter)?.label ?? "全部";

  const enrichedSkills = useMemo(
    () =>
      skills.map((skill, index) => {
        const tags = (skill.tags ?? []).map((tag) => tag.toLowerCase());
        const category =
          tags.some((tag) => ["system", "builtin", "系统"].includes(tag)) || skill.always
            ? "system"
            : "personal";
        const recommended =
          tags.some((tag) => ["recommended", "recommend", "推荐"].includes(tag)) || index < 2;
        return { ...skill, category, recommended } satisfies SkillWithMeta;
      }),
    [skills],
  );

  const filteredSkills = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return enrichedSkills.filter((skill) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "recommended" && skill.recommended) ||
        (filter === "system" && skill.category === "system") ||
        (filter === "personal" && skill.category === "personal");
      const matchesQuery =
        !normalizedQuery ||
        skill.name.toLowerCase().includes(normalizedQuery) ||
        skill.description.toLowerCase().includes(normalizedQuery) ||
        (skill.tags ?? []).some((tag) => tag.toLowerCase().includes(normalizedQuery));
      return matchesFilter && matchesQuery;
    });
  }, [enrichedSkills, filter, query]);

  const sections = [
    {
      key: "recommended",
      title: "推荐",
      skills: filteredSkills.filter((skill) => skill.recommended),
    },
    {
      key: "system",
      title: "系统",
      skills: filteredSkills.filter((skill) => !skill.recommended && skill.category === "system"),
    },
    {
      key: "personal",
      title: "个人",
      skills: filteredSkills.filter((skill) => !skill.recommended && skill.category === "personal"),
    },
  ].filter((section) => section.skills.length);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listSkills(token)
      .then((result) => {
        if (!cancelled) {
          setSkills(result);
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
  }, [token]);

  useEffect(() => {
    if (!selectedSkill) {
      setSkillDetail(null);
      setDetailError(null);
      return;
    }

    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    fetchSkillDetail(token, selectedSkill.name)
      .then((detail) => {
        if (!cancelled) setSkillDetail(detail);
      })
      .catch((err) => {
        if (!cancelled) setDetailError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSkill, token]);

  const detailContent = skillDetail ? skillPreview(skillDetail.content) : "";
  const DetailIcon = selectedSkill ? getSkillIcon(selectedSkill) : Sparkle;

  return (
    <PanelView
      title="技能"
      subtitle="把可复用能力、学习助手和工作流动作收进同一个地方。"
      {...panelProps}
    >
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索技能"
              className="h-11 rounded-xl border-slate-200 bg-white pl-10 text-sm shadow-[0_1px_3px_rgba(15,23,42,0.04)] focus-visible:ring-1 focus-visible:ring-slate-300 focus-visible:ring-offset-0"
            />
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="secondary"
                className="h-11 min-w-[92px] justify-between rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-800 shadow-[0_1px_3px_rgba(15,23,42,0.04)] hover:bg-slate-50"
              >
                {activeFilterLabel}
                <ChevronDown className="ml-2 h-4 w-4 text-slate-500" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[116px] rounded-lg p-1">
              {filterOptions.map((option) => (
                <DropdownMenuItem
                  key={option.value}
                  onClick={() => setFilter(option.value)}
                  className="flex cursor-pointer items-center justify-between rounded-md text-sm"
                >
                  {option.label}
                  {filter === option.value ? (
                    <Check className="ml-3 h-4 w-4 text-muted-foreground" aria-hidden />
                  ) : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {loading ? (
          <SkillLibraryNotice text="正在加载技能..." />
        ) : error ? (
          <SkillLibraryNotice text={error} />
        ) : skills.length && sections.length ? (
          <div className="flex flex-col gap-8">
            {sections.map((section) => (
              <section key={section.key} className="flex flex-col gap-3">
                <div className="border-b border-border/50 pb-3 text-sm font-semibold text-foreground">
                  {section.title}
                </div>
                <div className="grid gap-x-10 gap-y-3 md:grid-cols-2">
                  {section.skills.map((skill) => (
                    <SkillRow key={skill.name} skill={skill} onOpen={setSelectedSkill} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : skills.length ? (
          <SkillLibraryNotice text="没有匹配的技能。" />
        ) : (
          <SkillLibraryNotice text="当前还没有技能卡。后面接入学习助手和工作流技能后，这里会变成真实能力面板。" />
        )}
      </div>

      <Dialog open={!!selectedSkill} onOpenChange={(open) => !open && setSelectedSkill(null)}>
        <DialogContent className="max-h-[78vh] max-w-[640px] overflow-hidden rounded-xl border-slate-200 bg-white p-0 shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:rounded-xl">
          <div className="border-b border-slate-100 px-6 pb-5 pt-6">
            <DialogHeader className="space-y-3 text-left">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-950 shadow-[0_1px_4px_rgba(15,23,42,0.05)]">
                  <DetailIcon className="h-5 w-5" strokeWidth={1.8} aria-hidden />
                </div>
                <div className="min-w-0">
                  <DialogTitle className="truncate text-2xl leading-7 text-slate-950">
                    {selectedSkill ? toTitle(selectedSkill.name) : "技能"}
                  </DialogTitle>
                  <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                    {selectedSkill?.category === "system" ? "System Skill" : "Workspace Skill"}
                  </div>
                </div>
              </div>
              <DialogDescription className="text-sm leading-6 text-slate-600">
                {skillDetail?.description || selectedSkill?.description || "这个技能已接入运行时，可在学习对话里被调用。"}
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="scrollbar-none max-h-[52vh] overflow-y-auto px-6 py-5">
            {detailLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                正在读取技能说明...
              </div>
            ) : detailError ? (
              <div className="rounded-lg border border-border/60 bg-muted/30 px-3 py-3 text-sm text-muted-foreground">
                {detailError}
              </div>
            ) : detailContent ? (
              <div className="whitespace-pre-wrap text-[14px] leading-7 text-slate-700">
                {detailContent}
              </div>
            ) : (
              <div className="text-sm leading-6 text-slate-500">
                这个技能目前只有简短说明，完整文档还没有写入详情页。
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </PanelView>
  );
}
