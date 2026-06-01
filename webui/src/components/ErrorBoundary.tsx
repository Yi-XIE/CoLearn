import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional custom fallback. Receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render-time errors in its subtree so a single broken component does
 * not blank the whole app. React only surfaces these to class components, so
 * this stays a class on purpose.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Uncaught error in component tree", error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      if (this.props.fallback) {
        return this.props.fallback(error, this.reset);
      }
      return <DefaultErrorFallback error={error} onReset={this.reset} />;
    }
    return this.props.children;
  }
}

function DefaultErrorFallback({ error, onReset }: { error: Error; onReset: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center"
    >
      <p className="text-sm font-medium text-foreground">
        {t("errors.boundary.title", { defaultValue: "Something went wrong." })}
      </p>
      <p className="max-w-md text-xs text-muted-foreground break-words">
        {error.message}
      </p>
      <button
        type="button"
        onClick={onReset}
        className="rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-opacity hover:opacity-90"
      >
        {t("errors.boundary.retry", { defaultValue: "Try again" })}
      </button>
    </div>
  );
}
