import type { ErrorInfo, ReactNode } from "react";
import { Component } from "react";

import type { BackendErrorPayload } from "../../types/pipeline";
import { ErrorPanel } from "./ErrorPanel";

interface ResumeGenerationErrorBoundaryProps {
  children: ReactNode;
}

interface ResumeGenerationErrorBoundaryState {
  error: BackendErrorPayload | null;
}

export class ResumeGenerationErrorBoundary extends Component<
  ResumeGenerationErrorBoundaryProps,
  ResumeGenerationErrorBoundaryState
> {
  state: ResumeGenerationErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): ResumeGenerationErrorBoundaryState {
    return {
      error: {
        message: error.message || "Unexpected frontend exception.",
        failure_type: "frontend_exception",
        failure_category: "unexpected_ui_error",
        error_source: "frontend",
        metadata: {
          name: error.name,
          stack: error.stack,
        },
      },
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState((current) => ({
      error: current.error
        ? {
            ...current.error,
            metadata: {
              ...(current.error.metadata ?? {}),
              component_stack: errorInfo.componentStack,
            },
          }
        : {
            message: error.message,
            error_source: "frontend",
            metadata: {
              stack: error.stack,
              component_stack: errorInfo.componentStack,
            },
          },
    }));
  }

  render() {
    if (this.state.error) {
      return (
        <main style={{ maxWidth: 1080, margin: "0 auto", padding: "24px 16px 48px" }}>
          <ErrorPanel
            error={this.state.error}
            run={null}
            progress={null}
            result={null}
            onRetry={undefined}
            onStartNewRun={() => window.location.reload()}
            onReturnToEditor={() => window.location.reload()}
            debug={false}
          />
        </main>
      );
    }

    return this.props.children;
  }
}
