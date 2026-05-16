"use client";

import {
  Brain,
  History,
  type LucideIcon,
} from "lucide-react";

export type SpaceItemKey =
  | "chat_history"
  | "memory";

export type SpaceMemoryFile = "summary" | "profile";

export interface SpaceItem {
  key: SpaceItemKey;
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export const SPACE_ITEMS: SpaceItem[] = [
  {
    key: "chat_history",
    href: "/space/chat-history",
    label: "Chat History",
    description: "Review and reopen previous conversations.",
    icon: History,
  },
  {
    key: "memory",
    href: "/space/memory",
    label: "Memory",
    description: "Long-form memory the assistant carries across sessions.",
    icon: Brain,
  },
];
