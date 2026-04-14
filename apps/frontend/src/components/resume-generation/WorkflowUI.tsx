import { useEffect, useId, useRef } from "react";
import type { CSSProperties, JSX, KeyboardEvent, PropsWithChildren, ReactNode } from "react";

type Tone = "default" | "muted" | "success" | "warning" | "danger";

const panelToneStyles: Record<Tone, CSSProperties> = {
  default: {
    border: "1px solid var(--rg-border)",
    background: "var(--rg-surface)",
  },
  muted: {
    border: "1px solid var(--rg-border)",
    background: "var(--rg-surface-muted)",
  },
  success: {
    border: "1px solid var(--rg-success-border)",
    background: "var(--rg-success-surface)",
  },
  warning: {
    border: "1px solid var(--rg-warning-border)",
    background: "var(--rg-warning-surface)",
  },
  danger: {
    border: "1px solid var(--rg-danger-border)",
    background: "var(--rg-danger-surface)",
  },
};

const badgeToneStyles: Record<Tone, CSSProperties> = {
  default: {
    color: "var(--rg-text-strong)",
    background: "var(--rg-surface-muted)",
    border: "1px solid var(--rg-border)",
  },
  muted: {
    color: "var(--rg-text-subtle)",
    background: "var(--rg-background)",
    border: "1px solid var(--rg-border)",
  },
  success: {
    color: "var(--rg-success-text)",
    background: "var(--rg-success-surface)",
    border: "1px solid var(--rg-success-border)",
  },
  warning: {
    color: "var(--rg-warning-text)",
    background: "var(--rg-warning-surface)",
    border: "1px solid var(--rg-warning-border)",
  },
  danger: {
    color: "var(--rg-danger-text)",
    background: "var(--rg-danger-surface)",
    border: "1px solid var(--rg-danger-border)",
  },
};

export function WorkflowGlobalStyles() {
  return (
    <style>{`
      .resume-workflow {
        --rg-background: #f4f6f8;
        --rg-surface: #ffffff;
        --rg-surface-muted: #f8fafc;
        --rg-border: #d5dbe3;
        --rg-border-strong: #b7c0cb;
        --rg-text: #18212b;
        --rg-text-strong: #0f1720;
        --rg-text-subtle: #4f5d6c;
        --rg-focus: #0f5cc0;
        --rg-success-text: #155a2c;
        --rg-success-surface: #f2fbf5;
        --rg-success-border: #b7dfc0;
        --rg-warning-text: #855300;
        --rg-warning-surface: #fff8eb;
        --rg-warning-border: #ead29d;
        --rg-danger-text: #99231f;
        --rg-danger-surface: #fff5f4;
        --rg-danger-border: #efc4c1;
        color: var(--rg-text);
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        line-height: 1.5;
      }

      .resume-workflow * {
        box-sizing: border-box;
      }

      .resume-workflow h1,
      .resume-workflow h2,
      .resume-workflow h3,
      .resume-workflow h4,
      .resume-workflow p,
      .resume-workflow ul,
      .resume-workflow ol {
        margin-top: 0;
      }

      .resume-workflow h1 {
        font-size: clamp(1.9rem, 2.3vw, 2.6rem);
        line-height: 1.1;
        letter-spacing: -0.02em;
      }

      .resume-workflow h2 {
        font-size: clamp(1.25rem, 1.8vw, 1.65rem);
        line-height: 1.2;
        letter-spacing: -0.01em;
      }

      .resume-workflow h3 {
        font-size: clamp(1.02rem, 1.3vw, 1.2rem);
        line-height: 1.25;
      }

      .resume-workflow ul,
      .resume-workflow ol {
        padding-left: 1.15rem;
      }

      .resume-workflow .rg-card {
        border-radius: 18px;
        box-shadow: 0 8px 24px rgba(15, 23, 32, 0.05);
      }

      .resume-workflow .rg-section-header {
        display: grid;
        gap: 8px;
      }

      .resume-workflow .rg-muted {
        color: var(--rg-text-subtle);
      }

      .resume-workflow .rg-button,
      .resume-workflow .rg-input,
      .resume-workflow .rg-textarea,
      .resume-workflow .rg-select {
        font: inherit;
      }

      .resume-workflow .rg-button {
        min-height: 44px;
        border-radius: 12px;
        border: 1px solid var(--rg-border-strong);
        background: var(--rg-surface);
        color: var(--rg-text-strong);
        padding: 10px 16px;
        cursor: pointer;
        transition: border-color 120ms ease, box-shadow 120ms ease, background 120ms ease;
        font-weight: 600;
      }

      .resume-workflow .rg-button:hover:not(:disabled) {
        background: #f8fafc;
      }

      .resume-workflow .rg-button:disabled {
        opacity: 0.58;
        cursor: not-allowed;
      }

      .resume-workflow .rg-button-primary {
        background: #153a63;
        color: #ffffff;
        border-color: #153a63;
      }

      .resume-workflow .rg-button-primary:hover:not(:disabled) {
        background: #1b4677;
      }

      .resume-workflow .rg-button-danger {
        color: var(--rg-danger-text);
        border-color: var(--rg-danger-border);
        background: var(--rg-danger-surface);
      }

      .resume-workflow .rg-button-ghost {
        background: transparent;
      }

      .resume-workflow .rg-button:focus-visible,
      .resume-workflow .rg-input:focus-visible,
      .resume-workflow .rg-textarea:focus-visible,
      .resume-workflow .rg-select:focus-visible,
      .resume-workflow summary:focus-visible,
      .resume-workflow [role="tab"]:focus-visible {
        outline: 2px solid var(--rg-focus);
        outline-offset: 2px;
        box-shadow: 0 0 0 4px rgba(15, 92, 192, 0.12);
      }

      .resume-workflow .rg-input,
      .resume-workflow .rg-textarea,
      .resume-workflow .rg-select {
        width: 100%;
        border-radius: 14px;
        border: 1px solid var(--rg-border-strong);
        background: var(--rg-surface);
        color: var(--rg-text);
        padding: 12px 14px;
      }

      .resume-workflow .rg-textarea {
        min-height: 220px;
      }

      .resume-workflow .rg-input[aria-invalid="true"],
      .resume-workflow .rg-textarea[aria-invalid="true"] {
        border-color: var(--rg-danger-text);
      }

      .resume-workflow .rg-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }

      .resume-workflow .rg-meta-grid {
        display: grid;
        gap: 14px;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      }

      .resume-workflow .rg-stat {
        display: grid;
        gap: 4px;
        padding: 12px 14px;
        border-radius: 14px;
        background: var(--rg-surface-muted);
        border: 1px solid rgba(183, 192, 203, 0.5);
      }

      .resume-workflow .rg-empty-state {
        padding: 20px;
        border-radius: 14px;
        border: 1px dashed var(--rg-border-strong);
        background: var(--rg-surface-muted);
      }

      .resume-workflow .rg-skeleton {
        min-height: 16px;
        border-radius: 8px;
        background:
          linear-gradient(
            90deg,
            rgba(209, 218, 228, 0.65) 0%,
            rgba(229, 235, 241, 0.95) 50%,
            rgba(209, 218, 228, 0.65) 100%
          );
        background-size: 200% 100%;
        animation: rg-pulse 1.4s ease infinite;
      }

      .resume-workflow .rg-tablist {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }

      .resume-workflow .rg-tab {
        min-height: 42px;
        border-radius: 999px;
        border: 1px solid var(--rg-border);
        background: var(--rg-surface);
        color: var(--rg-text-strong);
        padding: 8px 14px;
        cursor: pointer;
        font-weight: 600;
      }

      .resume-workflow .rg-tab[aria-selected="true"] {
        border-color: #153a63;
        background: #eef4fb;
        color: #153a63;
      }

      .resume-workflow .rg-dialog-overlay {
        position: fixed;
        inset: 0;
        background: rgba(17, 24, 39, 0.45);
        display: grid;
        place-items: center;
        padding: 16px;
        z-index: 20;
      }

      .resume-workflow .rg-dialog {
        width: min(960px, 100%);
        max-height: 88vh;
        overflow: hidden;
        background: var(--rg-surface);
        border-radius: 18px;
        border: 1px solid var(--rg-border);
        display: grid;
        grid-template-rows: auto 1fr;
        box-shadow: 0 20px 40px rgba(15, 23, 32, 0.18);
      }

      .resume-workflow .rg-dialog-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        padding: 18px;
        border-bottom: 1px solid var(--rg-border);
      }

      .resume-workflow .rg-dialog-body {
        overflow: auto;
        background: var(--rg-surface-muted);
      }

      .resume-workflow .rg-sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      }

      @keyframes rg-pulse {
        from { background-position: 200% 0; }
        to { background-position: -200% 0; }
      }

      @media (max-width: 720px) {
        .resume-workflow {
          font-size: 15px;
        }

        .resume-workflow .rg-card {
          border-radius: 16px;
        }

        .resume-workflow .rg-button {
          width: 100%;
        }

        .resume-workflow .rg-actions {
          display: grid;
          grid-template-columns: 1fr;
        }

        .resume-workflow .rg-meta-grid {
          grid-template-columns: 1fr;
        }

        .resume-workflow .rg-dialog-header {
          padding: 14px;
        }

        .resume-workflow .rg-dialog {
          width: 100%;
          height: min(92vh, 960px);
        }
      }

      @media (prefers-reduced-motion: reduce) {
        .resume-workflow .rg-button,
        .resume-workflow .rg-skeleton {
          transition: none;
          animation: none;
        }
      }
    `}</style>
  );
}

export function SurfaceCard({
  children,
  tone = "default",
  className,
  style,
  ...props
}: PropsWithChildren<{
  tone?: Tone;
  className?: string;
  style?: CSSProperties;
}> &
  Omit<JSX.IntrinsicElements["section"], "className" | "style">) {
  return (
    <section
      {...props}
      className={className ? `rg-card ${className}` : "rg-card"}
      style={{
        padding: 16,
        ...panelToneStyles[tone],
        ...style,
      }}
    >
      {children}
    </section>
  );
}

export function StatusBadge({
  children,
  tone = "default",
}: PropsWithChildren<{ tone?: Tone }>) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        minHeight: 28,
        padding: "4px 10px",
        borderRadius: 999,
        fontSize: "0.875rem",
        fontWeight: 600,
        textTransform: "capitalize",
        ...badgeToneStyles[tone],
      }}
    >
      {children}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rg-empty-state">
      <h3 style={{ marginBottom: 6 }}>{title}</h3>
      <p className="rg-muted" style={{ marginBottom: action ? 14 : 0 }}>
        {description}
      </p>
      {action}
    </section>
  );
}

export function ModalShell({
  title,
  subtitle,
  open,
  onClose,
  width = "min(960px, 100%)",
  actions,
  children,
}: PropsWithChildren<{
  title: string;
  subtitle?: string;
  open: boolean;
  onClose: () => void;
  width?: string;
  actions?: ReactNode;
}>) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    dialogRef.current?.focus();
  }, [open]);

  if (!open) {
    return null;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  }

  return (
    <section className="rg-dialog-overlay" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        className="rg-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={subtitle ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        onMouseDown={(event) => event.stopPropagation()}
        style={{ width }}
      >
        <div className="rg-dialog-header">
          <div>
            <h2 id={titleId} style={{ marginBottom: subtitle ? 6 : 0 }}>
              {title}
            </h2>
            {subtitle ? (
              <p id={descriptionId} className="rg-muted" style={{ marginBottom: 0 }}>
                {subtitle}
              </p>
            ) : null}
          </div>
          <div className="rg-actions">
            {actions}
            <button type="button" className="rg-button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="rg-dialog-body">{children}</div>
      </div>
    </section>
  );
}
