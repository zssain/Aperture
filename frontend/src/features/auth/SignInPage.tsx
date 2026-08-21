import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { ErrorState } from "../../components/ui/ErrorState";
import { Input } from "../../components/ui/Input";
import { ApiError } from "../../lib/api";
import { useSignIn } from "./useSession";

interface SignInLocationState {
  returnTo?: string;
}

export function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const signIn = useSignIn();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const returnTo =
    (location.state as SignInLocationState | null)?.returnTo ?? "/queue";
  const error = signIn.error instanceof ApiError ? signIn.error : null;

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    signIn.mutate(
      { email, password },
      { onSuccess: () => navigate(returnTo, { replace: true }) },
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-sunken p-6">
      <form
        onSubmit={onSubmit}
        aria-labelledby="signin-heading"
        className="w-full max-w-form space-y-4 rounded border border-border bg-surface p-6"
      >
        <div className="space-y-1">
          <h1 id="signin-heading">
            <img
              src="/brand/aperture-logo.svg"
              alt="Aperture"
              className="h-12 w-auto"
              width="210"
              height="48"
            />
          </h1>
          <p className="text-sm text-muted">Sign in to continue.</p>
        </div>

        <div className="space-y-1">
          <label htmlFor="email" className="text-sm font-medium text-ink">
            Email
          </label>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="password" className="text-sm font-medium text-ink">
            Password
          </label>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error ? (
          <ErrorState
            title="Sign in failed"
            message={error.message}
            correlationId={error.correlationId}
          />
        ) : null}

        <Button type="submit" className="w-full" disabled={signIn.isPending}>
          {signIn.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
