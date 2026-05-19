import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

type ErrorBoundaryProps = {
  children: ReactNode;
  /** Optional fallback override. Receives the error + a reset function. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /** Optional callback fired when an error is caught — wire to logging here. */
  onError?: (error: Error, info: ErrorInfo) => void;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info);
    if (typeof window !== 'undefined') {
      console.error('[ErrorBoundary]', error, info.componentStack);
    }
  }

  reset = () => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <div className="grid min-h-[60vh] place-items-center px-4">
        <div className="ec-card w-full max-w-lg p-6">
          <div className="mb-3 flex items-center gap-3 text-rose-600">
            <AlertTriangle size={22} />
            <p className="text-lg font-semibold">Something went wrong</p>
          </div>
          <p className="text-sm text-ink-muted">
            A part of EnterpriseCore crashed. The error is logged to the dev console. You can try
            reloading the panel, or refresh the whole page if the problem persists.
          </p>
          <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-surface-muted p-3 font-mono text-xs text-ink-muted">
            {error.message}
            {error.stack ? '\n\n' + error.stack.split('\n').slice(0, 6).join('\n') : ''}
          </pre>
          <div className="mt-4 flex gap-2">
            <button className="ec-btn-primary" onClick={this.reset}>
              <RotateCcw size={15} /> Try again
            </button>
            <button className="ec-btn-secondary" onClick={() => window.location.reload()}>
              Reload page
            </button>
          </div>
        </div>
      </div>
    );
  }
}
