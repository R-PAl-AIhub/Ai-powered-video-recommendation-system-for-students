/** Small UI primitives shared by every screen.
 *  Shape rule: buttons and chips are pills, cards 20px, fields 12px. */
import { CircleNotch, Moon, Sun, X } from "@phosphor-icons/react";
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { cx } from "./format";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "outline" | "quiet" | "danger";
  size?: "sm" | "md" | "lg";
  busy?: boolean;
  icon?: ReactNode;
};

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap " +
  "transition-[transform,background-color,border-color,color,opacity] duration-200 ease-out-expo " +
  "active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 select-none";

const buttonVariants = {
  primary: "bg-accent text-on-accent hover:brightness-105",
  outline: "border border-line-strong text-ink hover:bg-ink/5",
  quiet: "text-soft hover:text-ink hover:bg-ink/5",
  danger: "border border-line-strong text-danger hover:bg-danger/10",
};

const buttonSizes = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

export function buttonClass(
  variant: keyof typeof buttonVariants = "primary",
  size: keyof typeof buttonSizes = "md",
  extra?: string,
): string {
  return cx(buttonBase, buttonVariants[variant], buttonSizes[size], extra);
}

export function Button({
  variant = "primary",
  size = "md",
  busy = false,
  icon,
  children,
  className,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClass(variant, size, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <CircleNotch size={16} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function IconButton({
  label,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "inline-grid size-9 place-items-center rounded-full text-soft transition-colors duration-200",
        "hover:bg-ink/5 hover:text-ink active:scale-95 disabled:opacity-40",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

type FieldShell = { label: string; hint?: string; error?: string };

function FieldFrame({
  id,
  label,
  hint,
  error,
  children,
}: FieldShell & { id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-[13px] text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="text-[13px] text-faint">{hint}</p>
      ) : null}
    </div>
  );
}

const fieldClass =
  "w-full rounded-field border border-line-strong bg-raised px-3.5 text-[15px] text-ink " +
  "placeholder:text-faint transition-colors duration-200 hover:border-ink/40 " +
  "focus:border-accent-ink focus:outline-none focus:ring-2 focus:ring-accent-ink/25";

export function Field({
  label,
  hint,
  error,
  className,
  ...rest
}: FieldShell & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <FieldFrame id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        className={cx(fieldClass, "h-11", className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        {...rest}
      />
    </FieldFrame>
  );
}

export function TextArea({
  label,
  hint,
  error,
  className,
  ...rest
}: FieldShell & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <FieldFrame id={id} label={label} hint={hint} error={error}>
      <textarea
        id={id}
        className={cx(fieldClass, "min-h-36 resize-y py-3 leading-relaxed", className)}
        aria-invalid={error ? true : undefined}
        {...rest}
      />
    </FieldFrame>
  );
}

export function Chip({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "warn";
  className?: string;
}) {
  const tones = {
    neutral: "border-line text-soft",
    accent: "border-accent-ink/40 text-accent-ink",
    warn: "border-warn/40 bg-warn-bg text-warn",
  };
  return (
    <span
      className={cx(
        "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("rounded-card border border-line bg-raised shadow-card", className)}>
      {children}
    </div>
  );
}

export function Notice({
  tone = "neutral",
  icon,
  children,
}: {
  tone?: "neutral" | "warn" | "danger";
  icon?: ReactNode;
  children: ReactNode;
}) {
  const tones = {
    neutral: "border-line bg-sunken text-soft",
    warn: "border-warn/30 bg-warn-bg text-warn",
    danger: "border-danger/30 bg-danger/10 text-danger",
  };
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cx("flex items-start gap-3 rounded-field border px-4 py-3 text-sm", tones[tone])}
    >
      {icon ? <span className="mt-0.5 shrink-0">{icon}</span> : null}
      <div className="min-w-0 leading-relaxed">{children}</div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("skeleton rounded-field", className)} />;
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-card border border-dashed border-line-strong px-6 py-10 md:px-10">
      <span className="grid size-11 place-items-center rounded-full bg-ink/5 text-ink">{icon}</span>
      <div className="flex max-w-[52ch] flex-col gap-1.5">
        <h3 className="text-lg font-semibold text-ink">{title}</h3>
        {children ? <p className="text-[15px] leading-relaxed text-soft">{children}</p> : null}
      </div>
      {action}
    </div>
  );
}

/** A modal built on the native <dialog>, which handles focus trapping and Escape. */
export function Dialog({
  open,
  onClose,
  title,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose(); // a click on the backdrop
      }}
      className={cx(
        "m-auto w-[calc(100vw-2rem)] rounded-card border border-line bg-raised p-0 text-ink shadow-card",
        "backdrop:bg-black/60 backdrop:backdrop-blur-sm",
        wide ? "max-w-5xl" : "max-w-lg",
      )}
    >
      {open ? (
        <div className="flex flex-col">
          <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3">
            <h2 className="truncate text-base font-semibold">{title}</h2>
            <IconButton label="Close" onClick={onClose}>
              <X size={18} />
            </IconButton>
          </div>
          <div className="p-5">{children}</div>
        </div>
      ) : null}
    </dialog>
  );
}

/** Light / dark switch. With no saved choice the page follows the system. */
export function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    const explicit = document.documentElement.getAttribute("data-theme");
    if (explicit) return explicit === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  function toggle() {
    const next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage unavailable; the choice lasts for this page only */
    }
    setDark(!dark);
    window.dispatchEvent(new Event("themechange"));
  }

  return (
    <IconButton label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={toggle}>
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </IconButton>
  );
}

/** The wordmark. A plain geometric mark: a path that climbs to a waypoint. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="9" className="fill-ink" />
        <path
          d="M8 22 L14 12 L19 19 L24 9"
          fill="none"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="stroke-bg"
        />
        <circle cx="24" cy="9" r="2.6" className="fill-accent" />
      </svg>
      Waypoint
    </span>
  );
}
