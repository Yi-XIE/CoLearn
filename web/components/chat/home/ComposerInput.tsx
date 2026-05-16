"use client";

import {
  forwardRef,
  memo,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useTranslation } from "react-i18next";
import ChatProjectMenu, {
  type ChatProjectSelectionCounts,
} from "@/components/chat/project/ChatProjectMenu";
import { shouldSubmitOnEnter } from "@/lib/composer-keyboard";

interface ComposerInputProps {
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  // When true, parent has attachments/references queued and will accept a
  // send even if the text body is empty. Without this, Enter would silently
  // do nothing for an attachment-only message.
  canSendEmpty: boolean;
  onSend: (content: string) => void;
  onInputChange: (content: string) => void;
  onPaste: (e: React.ClipboardEvent) => void;
  selectedCounts: ChatProjectSelectionCounts;
  onSelectMemoryPicker: () => void;
}

export interface ComposerInputHandle {
  clear: () => void;
  getValue: () => string;
}

export function shouldOpenAtPopup(value: string, cursorPos: number): boolean {
  const prefix = value.slice(0, cursorPos);
  return /(^|\s)@[^\s]*$/.test(prefix);
}

export function stripTrailingAtMention(value: string): string {
  return value.replace(/(^|\s)@[^\s]*$/, "$1").replace(/\s+$/, "");
}

export const ComposerInput = memo(
  forwardRef<ComposerInputHandle, ComposerInputProps>(function ComposerInput(
    {
      textareaRef,
      canSendEmpty,
      onSend,
      onInputChange,
      onPaste,
      selectedCounts,
      onSelectMemoryPicker,
    },
    ref,
  ) {
    const { t } = useTranslation();
    const [input, setInput] = useState("");
    const [showAtPopup, setShowAtPopup] = useState(false);

    // Latest text mirrored into a ref by the change handlers (never updated
    // during render). The @project handlers and the imperative handle read
    // from this ref so their identities stay stable across keystrokes,
    // letting `memo` on ChatProjectMenu actually skip re-renders when
    // `showAtPopup` doesn't change.
    const inputRef = useRef("");
    const isComposingRef = useRef(false);
    // Helper that always updates state and ref together so they can't drift.
    const setInputBoth = useCallback((value: string) => {
      inputRef.current = value;
      setInput(value);
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        clear: () => {
          setInputBoth("");
          onInputChange("");
        },
        getValue: () => inputRef.current,
      }),
      [setInputBoth, onInputChange],
    );

    useLayoutEffect(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      const next = Math.max(el.scrollHeight, 28);
      const bounded = Math.min(next, 200);
      el.style.height = `${bounded}px`;
      el.style.overflowY = next > 200 ? "auto" : "hidden";
    }, [input, textareaRef]);

    const handleInputChange = useCallback(
      (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const value = e.target.value;
        const cursorPos = e.target.selectionStart ?? value.length;
        setInputBoth(value);
        onInputChange(value);
        setShowAtPopup(shouldOpenAtPopup(value, cursorPos));
      },
      [setInputBoth, onInputChange],
    );

    const handleTextareaClick = useCallback(
      (e: React.MouseEvent<HTMLTextAreaElement>) => {
        const target = e.currentTarget;
        setShowAtPopup(
          shouldOpenAtPopup(
            target.value,
            target.selectionStart ?? target.value.length,
          ),
        );
      },
      [],
    );

    const doSend = useCallback(() => {
      const content = inputRef.current.trim();
      // Allow sending when text is empty but the parent has attachments or
      // references queued (canSendEmpty). This matches the send-button's
      // own enablement logic in ChatComposer (`canSend`).
      if (!content && !canSendEmpty) return;
      onSend(content);
      setInputBoth("");
      onInputChange("");
      setShowAtPopup(false);
    }, [canSendEmpty, onSend, setInputBoth, onInputChange]);

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (shouldSubmitOnEnter(e, isComposingRef.current)) {
          e.preventDefault();
          doSend();
        } else if (e.key === "Escape") {
          setShowAtPopup(false);
        }
      },
      [doSend],
    );

    const handleCompositionStart = useCallback(() => {
      isComposingRef.current = true;
    }, []);

    const handleCompositionEnd = useCallback(() => {
      // Some IMEs fire compositionend before the Enter keydown that confirms
      // a candidate, so keep the guard through the current event turn.
      setTimeout(() => {
        isComposingRef.current = false;
      }, 0);
    }, []);

    const clearTrailingMention = useCallback(() => {
      const next = stripTrailingAtMention(inputRef.current);
      setInputBoth(next);
      onInputChange(next);
    }, [setInputBoth, onInputChange]);

    const handleSelectProjectItem = useCallback(
      (key: "memory") => {
        clearTrailingMention();
        setShowAtPopup(false);
        if (key === "memory") onSelectMemoryPicker();
      },
      [clearTrailingMention, onSelectMemoryPicker],
    );

    return (
      <div className="px-4 pt-3.5 pb-2">
        {showAtPopup && (
          <div className="absolute bottom-full left-0 z-[70] mb-2">
            <ChatProjectMenu
              variant="mention"
              selectedCounts={selectedCounts}
              onSelectItem={handleSelectProjectItem}
            />
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onCompositionStart={handleCompositionStart}
          onCompositionEnd={handleCompositionEnd}
          onClick={handleTextareaClick}
          onPaste={onPaste}
          rows={1}
          suppressHydrationWarning
          placeholder={t("How can I help you today?")}
          className="w-full resize-none overflow-hidden bg-transparent text-[15px] leading-relaxed text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
          style={{ transition: "height 0.15s ease-out", minHeight: 28 }}
        />
      </div>
    );
  }),
);
