import { useState, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";

interface IntakeQuestion {
  id: string;
  question: string;
  options: string[];
  placeholder: string;
}

const INTAKE_QUESTIONS: IntakeQuestion[] = [
  {
    id: "background",
    question: "你目前的背景是什么？",
    options: ["有编程基础（Python/数学等）", "有统计学/线性代数基础", "在校学生/刚入门"],
    placeholder: "其他背景...",
  },
  {
    id: "goal",
    question: "你的学习目标是什么？",
    options: ["了解基础概念", "实际项目应用", "工作/转行准备"],
    placeholder: "具体目标...",
  },
  {
    id: "style",
    question: "你更倾向于哪种学习方式？",
    options: ["理论 + 数学推导", "动手实践 + 项目驱动", "两者结合"],
    placeholder: "其他偏好...",
  },
];

interface IntakeQuestionnaireCardProps {
  onComplete: (answers: Record<string, string>) => void;
}

export function IntakeQuestionnaireCard({ onComplete }: IntakeQuestionnaireCardProps) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [customInput, setCustomInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const current = INTAKE_QUESTIONS[step];

  const handleSelect = useCallback((value: string) => {
    const updated = { ...answers, [current.id]: value };
    setAnswers(updated);
    setCustomInput("");
    if (step < INTAKE_QUESTIONS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete(updated);
    }
  }, [answers, current, step, onComplete]);

  const handleCustomSubmit = useCallback(() => {
    const value = customInput.trim();
    if (!value) return;
    handleSelect(value);
  }, [customInput, handleSelect]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleCustomSubmit();
    }
  }, [handleCustomSubmit]);

  return (
    <div className="border-b border-border/40 px-4 py-3">
      {/* Header: question left, progress right */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-foreground">
          {current.question}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {step + 1}/{INTAKE_QUESTIONS.length}
        </span>
      </div>

      {/* Options separated by dividers */}
      <div className="divide-y divide-border/40">
        {current.options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => handleSelect(option)}
            className={cn(
              "w-full px-1 py-2.5 text-left text-sm text-foreground",
              "transition-colors hover:bg-accent/30",
            )}
          >
            {option}
          </button>
        ))}
        {/* Custom input as last row */}
        <div className="relative py-2">
          <input
            ref={inputRef}
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={current.placeholder}
            className={cn(
              "w-full bg-transparent px-1 py-1 text-sm text-foreground",
              "placeholder:text-muted-foreground/50 focus:outline-none",
            )}
          />
          {customInput.trim() && (
            <button
              type="button"
              onClick={handleCustomSubmit}
              className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md bg-foreground px-2 py-0.5 text-xs font-medium text-background"
            >
              确定
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
