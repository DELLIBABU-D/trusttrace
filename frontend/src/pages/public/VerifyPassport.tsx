import { LuCircleAlert, LuCircleCheck, LuCircleX } from "react-icons/lu";
import { passportApi } from "../../api/endpoints";
import type { PassportVerification } from "../../api/types";
import { NotLoaded } from "../../components/DataState";
import { Logo } from "../../components/Logo";
import { PassportCard } from "../../components/PassportCard";
import { Card, Spinner, cx } from "../../components/ui";
import { useQuery } from "../../lib/query";
import { useParams } from "../../lib/router";

const RESULT: Record<PassportVerification["result"], { title: string; tone: string; Icon: typeof LuCircleCheck }> = {
  valid: { title: "Valid TrustTrace passport", tone: "border-ok/30 bg-ok-soft text-ok", Icon: LuCircleCheck },
  expired: { title: "Passport expired", tone: "border-warn/30 bg-warn-soft text-warn", Icon: LuCircleAlert },
  superseded: { title: "Passport superseded", tone: "border-warn/30 bg-warn-soft text-warn", Icon: LuCircleAlert },
  revoked: { title: "Passport revoked", tone: "border-bad/30 bg-bad-soft text-bad", Icon: LuCircleX },
  unknown: { title: "Passport not recognised", tone: "border-bad/30 bg-bad-soft text-bad", Icon: LuCircleX },
  invalid: { title: "Passport could not be verified", tone: "border-bad/30 bg-bad-soft text-bad", Icon: LuCircleX },
};

/** Public page opened from the passport QR code. Shows only what the signed passport contains, plus its live status. */
export function VerifyPassport() {
  const { ref = "" } = useParams();
  const q = useQuery(`passport-verify:${ref}`, () => passportApi.verify(ref));
  const v = q.data;
  const meta = v ? RESULT[v.result] : null;
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-line bg-white"><div className="mx-auto max-w-3xl px-4 py-3.5"><Logo /></div></header>
      <main className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="text-xl font-semibold tracking-tight text-ink">Passport verification</h1>
        <p className="mt-1 text-sm text-ink-2">Checked live by TrustTrace: signature, expiry, revocation and the integrity of the evidence history.</p>
        <div className="mt-5">
          {q.isLoading ? <Spinner label="Verifying" /> : !v || !meta ? <Card><NotLoaded error={q.error} what="verification result" /></Card> : (
            <div className="space-y-5">
              <div role="status" className={cx("flex items-start gap-3 rounded-xl border px-4 py-3.5", meta.tone)}>
                <meta.Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
                <div>
                  <p className="font-semibold">{meta.title}</p>
                  <p className="text-[13.5px] text-ink-2">{v.message}</p>
                </div>
              </div>
              {v.passport && (
                <PassportCard p={v.passport} holderName={v.result === "valid" ? v.holderName : null}
                  className={v.result === "valid" ? undefined : "opacity-75"} />
              )}
              <Card className="p-5 text-[13px] leading-relaxed text-ink-2">
                <p className="font-medium text-ink">What this passport means</p>
                <ul className="mt-1.5 list-disc space-y-1 pl-5">
                  <li>It summarises checks recorded by TrustTrace for one job application, signed with TrustTrace's Ed25519 key.</li>
                  <li>“Verified” checks were actually completed (for example, a selfie matched the ID photo, or a mobile number was confirmed by OTP).
                    Document consistency is not issuer verification. Pending and simulated checks are never shown as verified.</li>
                  <li>Face matching is evidence, not proof, and no liveness or anti-spoofing check is performed. No government database was queried.</li>
                  <li>It contains no photos, documents, contact details, date of birth or biometric data. Compare the name with the person's own ID.</li>
                </ul>
              </Card>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
