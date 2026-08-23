import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button, IconButton } from "../../components/ui/Button";
import { Icon } from "../../components/ui/Icon";
import { Input } from "../../components/ui/Input";
import { ApiError } from "../../lib/api";
import { useSignIn } from "./useSession";

interface SignInLocationState {
  returnTo?: string;
}

/** Local sandbox credentials, shown only in dev builds (stripped from production
 * bundles). They match the accounts created by `make demo-reset`. */
const DEMO_ACCOUNTS: Array<{ label: string; email: string }> = [
  { label: "Credit analyst", email: "credit-analyst@demo.aperture.test" },
  { label: "Policy owner", email: "credit-policy-owner@demo.aperture.test" },
  { label: "Fraud reviewer", email: "fraud-reviewer@demo.aperture.test" },
  { label: "Auditor", email: "auditor@demo.aperture.test" },
];
const DEMO_PASSWORD = "Demo-Only-Strong-Passw0rd!";

interface FieldErrors {
  email?: string;
  password?: string;
}

function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!email.trim()) errors.email = "Enter your email.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
    errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Enter your password.";
  return errors;
}

export function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const signIn = useSignIn();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitted, setSubmitted] = useState(false);

  const returnTo =
    (location.state as SignInLocationState | null)?.returnTo ?? "/queue";
  const apiError = signIn.error instanceof ApiError ? signIn.error : null;

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setSubmitted(true);
    const next = validate(email, password);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    signIn.mutate(
      { email, password },
      { onSuccess: () => navigate(returnTo, { replace: true }) },
    );
  }

  function revalidate(nextEmail: string, nextPassword: string): void {
    if (submitted) setErrors(validate(nextEmail, nextPassword));
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center bg-surface p-6 sm:p-10">
        <form
          onSubmit={onSubmit}
          noValidate
          aria-labelledby="signin-heading"
          className="w-full max-w-form space-y-5"
        >
          <div className="space-y-2">
            <h1 id="signin-heading">
              <img
                src="/brand/aperture-logo.svg"
                alt="Aperture"
                className="h-9 w-auto"
                width="157"
                height="36"
              />
            </h1>
            <p className="eyebrow">Analyst sign-in</p>
            <p className="text-sm text-muted">
              Sign in to review cases and record decisions.
            </p>
          </div>

          <div className="space-y-1">
            <label htmlFor="email" className="block eyebrow">
              Email
            </label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? "email-error" : undefined}
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                revalidate(event.target.value, password);
              }}
            />
            {errors.email ? (
              <p id="email-error" className="text-sm text-negative">
                {errors.email}
              </p>
            ) : null}
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="block eyebrow">
              Password
            </label>
            <div className="relative">
              <Input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? "password-error" : undefined}
                className="pr-11"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  revalidate(email, event.target.value);
                }}
              />
              <IconButton
                icon={showPassword ? "eye-off" : "eye"}
                label={showPassword ? "Hide password" : "Show password"}
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 -translate-y-1/2 border-0 text-muted hover:bg-sunken"
                onClick={() => setShowPassword((value) => !value)}
              />
            </div>
            {errors.password ? (
              <p id="password-error" className="text-sm text-negative">
                {errors.password}
              </p>
            ) : null}
          </div>

          {apiError ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded border border-negative bg-negative-subtle p-3 text-sm text-negative"
            >
              <span className="mt-0.5 shrink-0">
                <Icon name="alert" size={16} />
              </span>
              <div>
                <p className="font-medium">Sign in failed</p>
                <p className="mt-0.5">
                  The email or password is incorrect. Check your details and try again.
                </p>
                {apiError.correlationId ? (
                  <p className="mt-1 text-xs">
                    Reference:{" "}
                    <span className="font-mono">{apiError.correlationId}</span>
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <Button type="submit" className="w-full" loading={signIn.isPending}>
            Sign in
          </Button>

          {import.meta.env.DEV ? (
            <div className="rounded border border-border bg-sunken p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Demo accounts (sandbox)
              </p>
              <div className="mt-2 grid grid-cols-2 gap-1.5">
                {DEMO_ACCOUNTS.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    className="rounded border border-border-strong bg-surface px-2 py-1.5 text-left text-xs font-medium text-ink transition-colors duration-fast hover:border-accent/60 hover:bg-surface-subtle"
                    onClick={() => {
                      setEmail(account.email);
                      setPassword(DEMO_PASSWORD);
                      setErrors({});
                    }}
                  >
                    {account.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted">
                Fills the form with local sandbox credentials seeded by{" "}
                <span className="font-mono">make demo-reset</span>.
              </p>
            </div>
          ) : null}
        </form>
      </div>

      {/* Decorative brand panel — hidden from assistive tech so the form leads. */}
      <aside
        aria-hidden="true"
        className="relative hidden flex-col overflow-hidden bg-nav p-12 text-nav-fg lg:flex"
      >
        {/* Soft ambient glow, drawn from the brand teal. */}
        <span
          className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 animate-glow rounded-pill"
          style={{
            background:
              "radial-gradient(closest-side, rgba(16,158,119,0.30), rgba(16,158,119,0) 70%)",
          }}
        />
        <span
          className="pointer-events-none absolute bottom-0 left-1/4 h-80 w-80 animate-glow rounded-pill"
          style={{
            animationDelay: "2s",
            background:
              "radial-gradient(closest-side, rgba(30,75,143,0.35), rgba(30,75,143,0) 70%)",
          }}
        />

        {/* Oversized aperture glyph as a faint, slowly-rotating watermark. */}
        <img
          src="/brand/aperture-icon-light.svg"
          alt=""
          className="pointer-events-none absolute -bottom-24 -right-24 h-[34rem] w-[34rem] animate-spin-slow opacity-[0.06]"
        />

        {/* Prominent wordmark, top-left, with a gentle float. */}
        <div className="relative animate-rise">
          <img
            src="/brand/aperture-logo-light.svg"
            alt=""
            className="h-10 w-auto animate-float"
            width="225"
            height="51"
          />
        </div>

        {/* Hero copy, centred in the remaining space, staggered in. */}
        <div className="relative my-auto max-w-xl">
          <p
            className="animate-rise eyebrow text-brand"
            style={{ animationDelay: "120ms" }}
          >
            Credit decisioning
          </p>
          <h2
            className="animate-rise mt-4 font-serif text-hero font-medium text-nav-fg"
            style={{ animationDelay: "200ms" }}
          >
            Evidence-based credit decisions for thin-file applicants.
          </h2>
          <p
            className="animate-rise mt-5 max-w-md text-body leading-relaxed text-nav-muted"
            style={{ animationDelay: "320ms" }}
          >
            Aperture assembles verified financial evidence, scores it transparently,
            and records every decision with a traceable, tamper-evident audit trail.
          </p>
        </div>

        <p
          className="animate-rise relative eyebrow text-nav-muted"
          style={{ animationDelay: "440ms" }}
        >
          Credit decisioning workspace
        </p>
      </aside>
    </main>
  );
}
