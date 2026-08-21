import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import type { ApplicantValues } from "./useIngest";

export type ApplicantErrors = Partial<Record<keyof ApplicantValues, string>>;

export interface ApplicantFormProps {
  values: ApplicantValues;
  errors: ApplicantErrors;
  disabled?: boolean;
  onChange: (field: keyof ApplicantValues, value: string) => void;
}

interface FieldProps {
  id: keyof ApplicantValues;
  label: string;
  error?: string;
  children: React.ReactNode;
  hint?: string;
}

function Field({ id, label, error, children, hint }: FieldProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-negative">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function ApplicantForm({ values, errors, disabled = false, onChange }: ApplicantFormProps) {
  function common(field: keyof ApplicantValues, hasHint = false) {
    return {
      id: field,
      name: field,
      disabled,
      invalid: Boolean(errors[field]),
      "aria-describedby": errors[field]
        ? `${field}-error`
        : hasHint
          ? `${field}-hint`
          : undefined,
      value: values[field],
      onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
        onChange(field, event.target.value),
    };
  }

  return (
    <section aria-labelledby="applicant-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4">
        <p className="eyebrow">Step 1 · Applicant &amp; request</p>
        <h2 id="applicant-heading" className="text-heading font-semibold text-ink">
          Who is applying?
        </h2>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Field id="displayName" label="Applicant name" error={errors.displayName}>
          <Input {...common("displayName")} autoComplete="name" />
        </Field>
        <Field id="externalRef" label="External reference" error={errors.externalRef}>
          <Input {...common("externalRef")} autoComplete="off" />
        </Field>
        <Field id="occupation" label="Occupation" error={errors.occupation}>
          <Select
            id="occupation"
            name="occupation"
            disabled={disabled}
            invalid={Boolean(errors.occupation)}
            aria-describedby={errors.occupation ? "occupation-error" : undefined}
            value={values.occupation}
            onChange={(event) => onChange("occupation", event.target.value)}
          >
            <option value="">Select occupation</option>
            <option value="SALARIED">Salaried</option>
            <option value="GIG">Gig worker</option>
            <option value="SELF_EMPLOYED">Self-employed</option>
            <option value="BUSINESS">Business owner</option>
          </Select>
        </Field>
        <Field
          id="declaredIncomeRupees"
          label="Declared monthly income (₹)"
          error={errors.declaredIncomeRupees}
          hint="₹1 to ₹1,00,00,000; whole rupees"
        >
          <Input
            {...common("declaredIncomeRupees", true)}
            inputMode="numeric"
            min="1"
            max="10000000"
            step="1"
            type="number"
          />
        </Field>
        <Field
          id="requestedAmountRupees"
          label="Requested amount (₹)"
          error={errors.requestedAmountRupees}
          hint="₹1,000 to ₹50,00,000; whole rupees"
        >
          <Input
            {...common("requestedAmountRupees", true)}
            inputMode="numeric"
            min="1000"
            max="5000000"
            step="1"
            type="number"
          />
        </Field>
        <Field
          id="requestedTenorMonths"
          label="Requested tenor (months)"
          error={errors.requestedTenorMonths}
          hint="3 to 60 months"
        >
          <Input
            {...common("requestedTenorMonths", true)}
            inputMode="numeric"
            min="3"
            max="60"
            step="1"
            type="number"
          />
        </Field>
      </div>
    </section>
  );
}
