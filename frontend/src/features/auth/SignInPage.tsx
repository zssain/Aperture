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
        </form>
      </div>

      {/* Decorative brand panel — hidden from assistive tech so the form leads. */}
      <aside
        aria-hidden="true"
        className="relative hidden flex-col justify-between bg-nav p-10 text-nav-fg lg:flex"
      >
        <img
          src="/brand/aperture-logo-light.svg"
          alt=""
          className="h-8 w-auto"
          width="180"
          height="41"
        />
        <div className="max-w-md space-y-4">
          <p className="text-display font-semibold leading-tight text-nav-fg">
            Evidence-based credit decisions for thin-file applicants.
          </p>
          <p className="text-body text-nav-muted">
            Aperture assembles verified financial evidence, scores it transparently,
            and records every decision with a traceable, tamper-evident audit trail.
          </p>
        </div>
        <p className="eyebrow text-nav-muted">Credit decisioning workspace</p>
      </aside>
    </main>
  );
}
