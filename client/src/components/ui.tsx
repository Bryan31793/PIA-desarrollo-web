import { useId } from 'react';
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from 'react';

export type IconName =
  | 'grid'
  | 'card'
  | 'scan'
  | 'users'
  | 'plans'
  | 'arrow'
  | 'logout'
  | 'check'
  | 'refresh'
  | 'shield'
  | 'plus'
  | 'clock';
const paths: Record<IconName, string> = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  card: 'M3 5h18v14H3z M3 10h18 M7 15h3',
  scan: 'M3 8V3h5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5 M3 12h18',
  users:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M17 4a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87',
  plans: 'M6 3h12v18H6z M9 7h6 M9 11h6 M9 15h3',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  logout: 'M9 3H3v18h6 M10 12h11 M16 7l5 5-5 5',
  check: 'M5 12l4 4L19 6',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 14 6 M18 18a8 8 0 0 1-14-6',
  shield: 'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-5',
  plus: 'M12 5v14 M5 12h14',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l3 2',
};
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
export function Brand() {
  return (
    <span className="brand">
      <span className="brand-mark" aria-hidden="true">
        G<span>↗</span>
      </span>
      GymFlow<span className="brand-dot">®</span>
    </span>
  );
}
export function Button({
  children,
  busy,
  variant = 'primary',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  busy?: boolean;
  variant?: 'primary' | 'secondary' | 'ghost';
}) {
  return (
    <button
      {...props}
      disabled={busy || props.disabled}
      className={`button ${variant} ${props.className || ''}`}
      aria-busy={busy}
    >
      {busy ? <span className="spinner" /> : null}
      {children}
    </button>
  );
}
export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const generatedId = useId();
  const id = props.id || generatedId;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        {...props}
        id={id}
        aria-describedby={hint ? `${id}-hint` : props['aria-describedby']}
      />
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
export function SelectField({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select {...props}>{children}</select>
    </label>
  );
}
export function Notice({
  children,
  kind = 'error',
}: {
  children?: ReactNode;
  kind?: 'error' | 'success' | 'info';
}) {
  if (!children) return null;
  return (
    <div className={`notice ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
export function Card({
  children,
  title,
  subtitle,
  icon,
  className = '',
}: {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  icon?: IconName;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <header className="card-heading">
          {icon && (
            <span className="icon-tile">
              <Icon name={icon} />
            </span>
          )}
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
        </header>
      )}
      {children}
    </section>
  );
}
export function SectionIntro({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="section-intro">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{children}</p>
    </div>
  );
}
