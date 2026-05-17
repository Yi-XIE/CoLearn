import { Menu, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ThreadHeaderProps {
  title: string;
  subtitle?: string | null;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
  minimal?: boolean;
  titleStyle?: "chat" | "page";
}

export function ThreadHeader({
  title,
  subtitle = null,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideSidebarToggleOnDesktop = false,
  minimal = false,
  titleStyle = "page",
}: ThreadHeaderProps) {
  const { t } = useTranslation();
  if (minimal) {
    return (
      <div className="relative z-10 flex h-11 items-center justify-between gap-3 px-3 py-2">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          onClick={onToggleSidebar}
          className={cn(
            "h-7 w-7 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            hideSidebarToggleOnDesktop && "lg:pointer-events-none lg:opacity-0",
          )}
        >
          <Menu className="h-3.5 w-3.5" />
        </Button>
        <ThemeButton theme={theme} onToggleTheme={onToggleTheme} label={t("thread.header.toggleTheme")} />
      </div>
    );
  }

  return (
    <div className="relative z-10 flex items-start justify-between gap-3 px-6 pt-3 pb-4">
      <div className="relative flex min-w-0 items-start gap-3">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          onClick={onToggleSidebar}
          className={cn(
            "mt-0.5 h-8 w-8 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            hideSidebarToggleOnDesktop && "lg:pointer-events-none lg:opacity-0",
          )}
        >
          <Menu className="h-3.5 w-3.5" />
        </Button>
        <div className="flex min-w-0 flex-col rounded-md py-0">
          <span
            className={cn(
              "max-w-[min(60vw,32rem)] truncate leading-tight",
              titleStyle === "page"
                ? "text-[22px] font-bold text-black dark:text-white sm:text-[26px]"
                : "text-[14px] font-medium text-foreground/78 sm:text-[15px]",
            )}
          >
            {title}
          </span>
          {subtitle ? (
            <span className="mt-1 max-w-[min(70vw,42rem)] truncate text-[12px] text-foreground/68">
              {subtitle}
            </span>
          ) : null}
        </div>
      </div>

      <ThemeButton theme={theme} onToggleTheme={onToggleTheme} label={t("thread.header.toggleTheme")} />

      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-full h-4" />
    </div>
  );
}

function ThemeButton({
  theme,
  onToggleTheme,
  label,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  label: string;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      onClick={onToggleTheme}
      className="h-8 w-8 rounded-full text-muted-foreground/85 hover:bg-accent/40 hover:text-foreground"
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </Button>
  );
}
