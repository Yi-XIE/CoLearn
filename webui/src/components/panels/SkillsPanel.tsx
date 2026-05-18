import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  Image,
  Pencil,
  Plus,
  Puzzle,
  Search,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { listSkills } from "@/lib/api";
import type { SkillSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

import { PanelView, type PanelShellProps } from "./PanelView";

function SkillLibraryNotice({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border/50 bg-card/70 px-4 py-5 text-sm text-muted-foreground">
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
  const name = skill.name.toLowerCase();
  const haystack = `${skill.name} ${skill.description} ${skill.tags.join(" ")}`.toLowerCase();
  if (haystack.includes("image") || haystack.includes("图片") || haystack.includes("图像")) return Image;
  if (haystack.includes("doc") || haystack.includes("markdown") || haystack.includes("pdf")) return BookOpen;
  if (haystack.includes("create") || haystack.includes("creator") || haystack.includes("edit")) return Pencil;
  if (name.includes("plugin") || name.includes("install")) return Puzzle;
  return Sparkles;
}

function getSkillIconTone(name: string) {
  const tones = [
    "text-rose-500",
    "text-sky-500",
    "text-amber-500",
    "text-emerald-500",
    "text-violet-500",
  ];
  return tones[name.length % tones.length];
}

function SkillCard({
  skill,
  installed,
}: {
  skill: SkillSummary & { category: string; recommended: boolean };
  installed: boolean;
}) {
  const Icon = getSkillIcon(skill);
  const description = skill.description || "这张技能卡已经接入运行时，可以在学习会话里被调用。";

  return (
    <article className="group flex min-h-[74px] items-center gap-3 rounded-lg border border-transparent px-3 py-3 transition hover:border-border/60 hover:bg-muted/40">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground shadow-sm">
        <Icon className={cn("h-5 w-5", getSkillIconTone(skill.name))} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold leading-5 text-foreground">
          {toTitle(skill.name)}
          <span className="sr-only">{skill.name}</span>
        </div>
        <div className="mt-0.5 line-clamp-1 text-[13px] leading-5 text-muted-foreground">
          {description}
        </div>
      </div>
      <button
        type="button"
        aria-label={installed ? `${skill.name} 已安装` : `添加 ${skill.name}`}
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition",
          installed
            ? "text-muted-foreground/75"
            : "bg-muted text-foreground hover:bg-foreground hover:text-background",
        )}
      >
        {installed ? <Check className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
      </button>
    </article>
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
  const filterOptions = [
    { value: "all", label: "全部" },
    { value: "recommended", label: "推荐" },
    { value: "system", label: "系统" },
    { value: "personal", label: "个人" },
  ] as const;
  const activeFilterLabel =
    filterOptions.find((option) => option.value === filter)?.label ?? "全部";

  const enrichedSkills = useMemo(
    () =>
      skills.map((skill, index) => {
        const tags = skill.tags.map((tag) => tag.toLowerCase());
        const category = tags.some((tag) => ["system", "builtin", "系统"].includes(tag))
          ? "system"
          : "personal";
        const recommended =
          tags.some((tag) => ["recommended", "recommend", "推荐"].includes(tag)) || index < 2;
        return { ...skill, category, recommended };
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
        skill.tags.some((tag) => tag.toLowerCase().includes(normalizedQuery));
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

  return (
    <PanelView
      title="技能"
      subtitle="把可复用能力、学习助手和工作流动作收进同一个地方。"
      {...panelProps}
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索技能"
              className="h-10 rounded-full border-border/70 bg-muted/45 pl-9 text-sm shadow-inner"
            />
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="secondary"
                className="h-10 min-w-[84px] justify-between rounded-full border border-border/60 bg-muted/55 px-4 text-sm font-medium shadow-none hover:bg-muted"
              >
                {activeFilterLabel}
                <ChevronDown className="ml-2 h-4 w-4 text-muted-foreground" aria-hidden />
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
                <div className="border-b border-border/45 pb-3 text-base font-semibold text-foreground">
                  {section.title}
                </div>
                <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
                  {section.skills.map((skill) => (
                    <SkillCard key={skill.name} skill={skill} installed />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : skills.length ? (
          <SkillLibraryNotice text="没有匹配的技能。" />
        ) : (
          <SkillLibraryNotice text="当前还没有技能卡。后面接入学习助手和工作流技能后，这里会变成真实能力面。" />
        )}
      </div>
    </PanelView>
  );
}
