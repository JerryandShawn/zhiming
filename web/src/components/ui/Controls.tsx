import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from 'react';
import { forwardRef } from 'react';
import { Check, ChevronRight, LoaderCircle, Trash2 } from 'lucide-react';
import * as SwitchPrimitive from '@radix-ui/react-switch';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive';
  loading?: boolean;
  block?: boolean;
};
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', loading = false, block = false, children, className = '', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      {...props}
      disabled={props.disabled || loading}
      aria-busy={loading || undefined}
      className={`button ${variant} ${block ? 'block' : ''} ${className}`}>
      {loading && <LoaderCircle className="icon small spinner" aria-hidden="true" />}
      {variant === 'destructive' && <Trash2 className="icon small" aria-hidden="true" />}
      {children}
    </button>
  );
});

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { label: string }>(
  function IconButton({ label, children, ...props }, ref) {
    return (
      <button ref={ref} type="button" {...props} className="icon-button" aria-label={label}>
        {children}
      </button>
    );
  },
);

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${props.className ?? ''}`} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`textarea ${props.className ?? ''}`} />;
}

export function Checkbox({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <span className="checkbox-target">
      <input {...props} type="checkbox" className="checkbox-input" aria-label={label} />
      <span className="checkbox-box" aria-hidden="true">
        <Check className="icon small" />
      </span>
    </span>
  );
}

export function Switch({
  label,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <span className="switch-target">
      <SwitchPrimitive.Root
        className="switch"
        aria-label={label}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}>
        <SwitchPrimitive.Thumb className="switch-thumb" />
      </SwitchPrimitive.Root>
    </span>
  );
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Tag({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`tag ${tone}`}>{children}</span>;
}

export function Disclosure({
  title,
  count,
  children,
  open = false,
}: {
  title: string;
  count?: string;
  children: ReactNode;
  open?: boolean;
}) {
  return (
    <details className="disclosure" open={open || undefined}>
      <summary>
        <ChevronRight className="icon small" aria-hidden="true" />
        {title}
        {count && <span className="meta">{count}</span>}
      </summary>
      <div className="disclosure-content">{children}</div>
    </details>
  );
}

export function Seal({ size = 'nav' }: { size?: 'nav' | 'small' | 'large' }) {
  return (
    <span className={`seal ${size}`} role="img" aria-label="明镜印章">
      <svg viewBox="0 0 28 28" aria-hidden="true">
        <text x="14" y="12" textAnchor="middle" fontSize="12" fill="currentColor" fontFamily="serif">
          明
        </text>
        <text x="14" y="24" textAnchor="middle" fontSize="12" fill="currentColor" fontFamily="serif">
          镜
        </text>
      </svg>
    </span>
  );
}
