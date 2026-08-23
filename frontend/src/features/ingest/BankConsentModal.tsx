import { useEffect, useMemo, useState, type ReactNode } from "react";

import { Button } from "../../components/ui/Button";
import { Chip } from "../../components/ui/Chip";
import { Input } from "../../components/ui/Input";
import { Modal } from "../../components/ui/Modal";
import type { DemoBank } from "./BankPicker";
import type { SourceType } from "./useIngest";

export interface AaConsentResult {
  scopes: SourceType[];
  purpose: string;
  expiresOn: string;
}

interface BankConsentModalProps {
  open: boolean;
  bank: DemoBank | null;
  applicantName: string;
  purpose: string;
  expiresOn: string;
  busy?: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: (result: AaConsentResult) => void;
}

type Step = "signin" | "consent";

/** A small deterministic 4-digit tail so the sandbox account numbers are stable per bank. */
function tail(seed: string): string {
  let value = 0;
  for (let index = 0; index < seed.length; index += 1) {
    value = (value * 31 + seed.charCodeAt(index)) % 10000;
  }
  return String(value).padStart(4, "0");
}

function firstName(name: string): string {
  const token = name.trim().split(/\s+/)[0]?.toLowerCase().replace(/[^a-z]/g, "");
  return token || "applicant";
}

function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
}

/**
 * Simulated Account Aggregator journey: the applicant "signs in" at their bank (OTP) and
 * approves exactly which accounts to share. This mirrors the real AA redirect — the lender
 * (Aperture) never sees credentials; consent is given at the bank/AA, granular and explicit.
 * It is honest theatre: no real authentication happens and nothing is pre-selected.
 */
export function BankConsentModal({
  open,
  bank,
  applicantName,
  purpose,
  expiresOn,
  busy = false,
  onOpenChange,
  onApprove,
}: BankConsentModalProps) {
  const [step, setStep] = useState<Step>("signin");
  const [mobile, setMobile] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otp, setOtp] = useState("");
  const [shareBank, setShareBank] = useState(false);
  const [shareUpi, setShareUpi] = useState(false);

  // Reset the whole journey whenever the dialog (re)opens or the bank changes.
  useEffect(() => {
    if (!open) return;
    setStep("signin");
    setMobile("");
    setOtpSent(false);
    setOtp("");
    setShareBank(false);
    setShareUpi(false);
  }, [open, bank?.id]);

  const accountTail = useMemo(() => tail(`${bank?.id ?? ""}:${applicantName}`), [bank, applicantName]);

  if (!bank) return null;

  const bankShort = bank.id.slice(0, 4);
  const upiHandle = `${firstName(applicantName)}@ok${bankShort}`;
  const scopes: SourceType[] = [
    ...(shareBank ? (["BANK"] as const) : []),
    ...(shareUpi ? (["UPI"] as const) : []),
  ];
  const canVerify = otp.trim().length >= 4;

  const brandStrip = (
    <div className="flex items-center gap-3 rounded border border-border bg-sunken p-3">
      <span className="flex h-11 w-28 shrink-0 items-center justify-center overflow-hidden rounded border border-border bg-white px-2">
        <img
          src={bank.logo}
          alt={bank.name}
          className="max-h-7 max-w-full object-contain"
          loading="lazy"
        />
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-ink">{bank.name}</p>
        <p className="text-xs text-muted">NetBanking · Account Aggregator</p>
      </div>
      <Chip tone="neutral" className="ml-auto">
        Sandbox
      </Chip>
    </div>
  );

  let footer: ReactNode;
  if (step === "signin") {
    footer = otpSent ? (
      <>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button disabled={!canVerify} onClick={() => setStep("consent")}>
          Verify &amp; continue
        </Button>
      </>
    ) : (
      <>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button disabled={mobile.trim().length < 3} onClick={() => setOtpSent(true)}>
          Send OTP
        </Button>
      </>
    );
  } else {
    footer = (
      <>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Deny
        </Button>
        <Button
          disabled={scopes.length === 0 || busy}
          loading={busy}
          onClick={() => onApprove({ scopes, purpose, expiresOn })}
        >
          Approve &amp; share
        </Button>
      </>
    );
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Connect via Account Aggregator"
      description="Sandbox · the applicant authenticates with their bank, never with Aperture."
      size="md"
      footer={footer}
    >
      <div className="space-y-4">
        {brandStrip}

        {step === "signin" ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-ink">Sign in to {bank.name}</h3>
            <p className="rounded border border-border bg-surface px-3 py-2 text-xs text-muted">
              Simulated bank sign-in — no real credentials are used or stored. Enter any values to
              continue.
            </p>
            <div className="space-y-1">
              <label htmlFor="aa-mobile" className="block text-sm font-medium text-ink">
                Registered mobile or customer ID
              </label>
              <Input
                id="aa-mobile"
                inputMode="numeric"
                autoComplete="off"
                placeholder="9876543210"
                value={mobile}
                disabled={otpSent}
                onChange={(event) => setMobile(event.target.value)}
              />
            </div>
            {otpSent ? (
              <div className="space-y-1">
                <label htmlFor="aa-otp" className="block text-sm font-medium text-ink">
                  One-time password
                </label>
                <Input
                  id="aa-otp"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="Any 6 digits"
                  value={otp}
                  onChange={(event) => setOtp(event.target.value)}
                />
                <p className="text-xs text-muted">
                  An OTP was “sent” to {mobile || "the registered mobile"}. Any 6 digits work here.
                </p>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-ink">Approve data sharing</h3>
            <p className="text-sm text-muted">
              <span className="font-medium text-ink">Aperture Credit</span> is requesting a one-time
              fetch of up to 12 months of transactions.
            </p>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted">Purpose</dt>
                <dd className="text-ink">{purpose.trim() || "Credit underwriting"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted">Valid until</dt>
                <dd className="text-ink">{expiresOn ? formatDate(expiresOn) : "—"}</dd>
              </div>
            </dl>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-ink">
                Accounts to share (none selected by default)
              </legend>
              <label className="flex items-center gap-2 rounded border border-border p-2.5 text-sm text-ink">
                <input
                  type="checkbox"
                  aria-label="Share bank account"
                  checked={shareBank}
                  onChange={(event) => setShareBank(event.target.checked)}
                />
                <span className="min-w-0">
                  <span className="font-medium">{bank.name} Savings</span> · A/C ••{accountTail}
                </span>
                <Chip tone="neutral" className="ml-auto">
                  Bank
                </Chip>
              </label>
              <label className="flex items-center gap-2 rounded border border-border p-2.5 text-sm text-ink">
                <input
                  type="checkbox"
                  aria-label="Share UPI account"
                  checked={shareUpi}
                  onChange={(event) => setShareUpi(event.target.checked)}
                />
                <span className="min-w-0">
                  <span className="font-medium">UPI</span> · {upiHandle}
                </span>
                <Chip tone="neutral" className="ml-auto">
                  UPI
                </Chip>
              </label>
            </fieldset>
            <p className="text-xs text-muted">
              Approving shares only the ticked accounts. A hash of these exact terms is recorded;
              revoking stops future collection immediately.
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
}
