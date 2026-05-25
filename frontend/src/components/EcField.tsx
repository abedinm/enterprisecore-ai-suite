/**
 * EcField — principled form-field wrapper that ties together label, input,
 * description, and error message via stable IDs + ARIA relationships.
 *
 * What it fixes
 * -------------
 * The audit found 592 ``.ec-label`` elements that aren't programmatically
 * associated with the input they describe (no ``htmlFor`` / ``id``), and
 * the same number of inputs whose error messages aren't wired via
 * ``aria-invalid`` / ``aria-describedby``. The runtime a11y shim covers
 * the first issue for legacy markup; this component is the principled
 * replacement for NEW forms.
 *
 * Usage
 * -----
 *     <EcField label="Customer name" required error={errors.name?.message}>
 *       {(id, descId, invalid) => (
 *         <input id={id} aria-invalid={invalid} aria-describedby={descId}
 *                {...register('name')} className="ec-input" />
 *       )}
 *     </EcField>
 *
 * Or, with the convenience shorthand for a simple text input:
 *
 *     <EcField.Input label="Email" type="email" {...register('email')}
 *                    error={errors.email?.message} />
 *
 * Why a render-prop instead of cloneElement
 * -----------------------------------------
 * Existing forms use ``react-hook-form`` and want to spread ``register()``
 * onto the bare input. Wrapping the input in our own component would force
 * a refactor of every form. The render-prop hands the caller the
 * ``id`` / ``descId`` / ``invalid`` triplet so they can decorate the input
 * themselves with one line.
 */
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';

type Render = (id: string, descId: string | undefined, invalid: boolean) => ReactNode;

type EcFieldProps = {
  label: string;
  description?: string;
  error?: string;
  required?: boolean;
  hideLabel?: boolean;
  children: Render;
};

export function EcField({
  label, description, error, required, hideLabel, children,
}: EcFieldProps) {
  const id = useId();
  const descId = description ? `${id}-desc` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const aria = [descId, errId].filter(Boolean).join(' ') || undefined;
  const invalid = Boolean(error);
  return (
    <div className="space-y-1">
      <label
        htmlFor={id}
        className={hideLabel ? 'sr-only' : 'ec-label'}
      >
        {label}
        {required && <span aria-hidden="true" className="ml-0.5 text-rose-500">*</span>}
      </label>
      {children(id, aria, invalid)}
      {description && !error && (
        <p id={descId} className="text-xs text-ink-muted">{description}</p>
      )}
      {error && (
        <p id={errId} role="alert" className="text-xs text-rose-600 dark:text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Convenience: <EcField.Input> for the common bare-input case.
// ---------------------------------------------------------------------------

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'name'> & {
  name?: string;
  label: string;
  description?: string;
  error?: string;
  required?: boolean;
  hideLabel?: boolean;
};

const EcFieldInput = forwardRef<HTMLInputElement, InputProps>(function EcFieldInput(
  { label, description, error, required, hideLabel, className, ...rest },
  ref,
) {
  return (
    <EcField
      label={label}
      description={description}
      error={error}
      required={required}
      hideLabel={hideLabel}
    >
      {(id, descId, invalid) => (
        <input
          ref={ref}
          id={id}
          aria-invalid={invalid}
          aria-describedby={descId}
          required={required}
          className={`ec-input ${invalid ? 'border-rose-500 focus:border-rose-500' : ''} ${className ?? ''}`}
          {...rest}
        />
      )}
    </EcField>
  );
});

(EcField as any).Input = EcFieldInput;
export type { EcFieldProps };
export const EcFieldInputComponent = EcFieldInput;
