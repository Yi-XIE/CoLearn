import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

const INTAKE_QUESTION_IDS = ["background", "goal", "style"] as const;

interface IntakeQuestionnaireCardProps {
  onComplete: (answers: Record<string, string>) => void;
}

export function IntakeQuestionnaireCard({ onComplete }: IntakeQuestionnaireCardProps) {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [customInput, setCustomInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const currentId = INTAKE_QUESTION_IDS[step];
  const question = t(`learning.intake.questions.${currentId}.question`);
  const options = t(`learning.intake.questions.${currentId}.options`, {
    returnObjects: true,
  }) as string[];
  const placeholder = t(`learning.intake.questions.${currentId}.placeholder`);

  const handleSelect = useCallback((value: string) => {
    const updated = { ...answers, [currentId]: value };
    setAnswers(updated);
    setCustomInput("");
    if (step < INTAKE_QUESTION_IDS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete(updated);
    }
  }, [answers, currentId, step, onComplete]);

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
          {question}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {step + 1}/{INTAKE_QUESTION_IDS.length}
        </span>
      </div>

      {/* Options separated by dividers */}
      <div className="divide-y divide-border/40">
        {(Array.isArray(options) ? options : []).map((option) => (
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
            placeholder={placeholder}
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
              {t("learning.intake.confirm")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
