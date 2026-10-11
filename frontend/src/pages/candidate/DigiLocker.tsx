import { useEffect, useState } from "react";
import { LuExternalLink, LuFileCheck, LuLink2, LuShieldCheck, LuTrash2 } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { digilockerApi } from "../../api/endpoints";
import { DigiLockerCompare } from "../../components/DigiLockerCompare";
import { Logo } from "../../components/Logo";
import { Button, Card, CardHeader, Notice, Pill, Spinner } from "../../components/ui";
import { invalidate, useMutation, useQuery } from "../../lib/query";
import { useSearchParam } from "../../lib/router";

/** Education page card: connect DigiLocker, pick the issued document, see the field-by-field comparison. */
export function DigiLockerCard() {
  const q = useQuery("candidate:digilocker", digilockerApi.status);
  const flag = useSearchParam("digilocker");
  const message = useSearchParam("message");
  const [agree, setAgree] = useState(false);
  const refresh = () => (invalidate("candidate:digilocker"), invalidate("candidate:verification"));
  const start = useMutation(() => digilockerApi.start(), { onSuccess: (r) => { window.location.href = r.authorizeUrl; } });
  const pull = useMutation((uri: string) => digilockerApi.fetch(uri), { onSuccess: () => { refresh(); setTimeout(refresh, 2500); setTimeout(refresh, 6000); } });
  const remove = useMutation(() => digilockerApi.remove(), { onSuccess: refresh });
  useEffect(() => { if (flag) refresh(); }, [flag]);
  if (q.isLoading) return <Card className="mt-5"><Spinner label="Checking DigiLocker" /></Card>;
  const d = q.data;
  if (!d || !d.enabled) return null;
  const c = d.comparison && !["off", "not_connected"].includes(d.comparison.status) ? d.comparison : null;
  const issued = [...d.issued].sort((a, b) => Number(b.likelyEducation) - Number(a.likelyEducation));
  return (
    <Card className="mt-5">
      <CardHeader title={<span className="flex items-center gap-2">Compare with DigiLocker {d.simulated && <Pill tone="violet">SIMULATED mode</Pill>}</span>}
        sub="Pull the issuer's own copy of your certificate from DigiLocker and compare it field by field with the one you uploaded." />
      <div className="space-y-4 px-5 pb-5">
        {flag === "connected" && <Notice tone="success">DigiLocker connected. Choose the document to compare.</Notice>}
        {flag === "denied" && <Notice tone="warn">DigiLocker access was not granted. Nothing was shared.</Notice>}
        {flag === "error" && <Notice tone="error" title="DigiLocker">{message ?? "Something went wrong. Try again."}</Notice>}
        {d.simulated && (
          <p className="rounded-lg bg-violet-soft px-3 py-2 text-xs text-violet">
            This server has no DigiLocker partner credentials, so a SIMULATED DigiLocker is used for testing. Simulated records are always labelled and never
            count as verification. With an approved DigiLocker partner app, the same button opens the real DigiLocker.
          </p>
        )}
        {c && <DigiLockerCompare c={c} />}
        {d.document && !c && <p className="flex items-center gap-1.5 text-[13px] text-ink-2"><LuFileCheck className="size-4 text-ok" aria-hidden />Pulled “{d.document.title}”. Comparing… refresh in a moment.</p>}

        {!d.connected ? (
          <div className="space-y-3">
            {d.sessionExpired && <Notice tone="info">Your DigiLocker session has ended. Connect again to pull another document.</Notice>}
            <label className="flex items-start gap-2 text-[13px] text-ink-2">
              <input type="checkbox" className="mt-0.5 size-4 accent-brand-600" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              <span>{d.consentText}</span>
            </label>
            <Button icon={LuExternalLink} disabled={!agree} loading={start.isPending} onClick={() => void start.mutate(undefined)}>
              {d.simulated ? "Connect DigiLocker (simulated)" : "Connect DigiLocker"}
            </Button>
          </div>
        ) : issued.length === 0 ? (
          <Notice tone="info">No issued documents were found in this DigiLocker account{d.simulated ? " (no simulated records match your name or mobile number)" : ""}.</Notice>
        ) : (
          <div>
            <p className="mb-2 text-[13px] font-medium text-ink">Your DigiLocker documents</p>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {issued.map((i) => (
                <li key={i.uri} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-[13px]">
                  <LuShieldCheck className="size-4 text-ink-3" aria-hidden />
                  <span className="min-w-0 flex-1"><span className="font-medium text-ink">{i.name}</span>
                    <span className="block text-xs text-ink-3">{i.issuer}{i.doctype ? ` · ${i.doctype}` : ""}{i.date ? ` · ${i.date}` : ""}</span></span>
                  {i.likelyEducation && <Pill tone="blue">Education</Pill>}
                  <Button size="sm" variant="secondary" icon={LuLink2} loading={pull.isPending} onClick={() => void pull.mutate(i.uri)}>Compare this</Button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {(start.error || pull.error || remove.error) ? <Notice tone="error">{errorMessage(start.error || pull.error || remove.error)}</Notice> : null}
        {(d.connected || d.document) && (
          <Button size="sm" variant="ghost" icon={LuTrash2} loading={remove.isPending} onClick={() => void remove.mutate(undefined)}>Disconnect and delete DigiLocker data</Button>
        )}
      </div>
    </Card>
  );
}

/** The SIMULATED DigiLocker consent screen (only used when the server runs in simulated mode). */
export function SimulatedDigiLocker() {
  const state = useSearchParam("state") ?? "";
  const q = useQuery(`digilocker-sim:${state}`, () => digilockerApi.simView(state));
  const decide = useMutation((allow: boolean) => digilockerApi.simDecide(state, allow), { onSuccess: (r) => { window.location.href = r.redirect; } });
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-line bg-white"><div className="mx-auto max-w-3xl px-4 py-3.5"><Logo /></div></header>
      <main className="mx-auto max-w-lg px-4 py-8">
        <Card className="p-6">
          <p className="inline-block rounded-md bg-violet-soft px-2 py-0.5 text-xs font-semibold text-violet">SIMULATED DIGILOCKER – FOR TESTING ONLY</p>
          <h1 className="mt-3 text-xl font-semibold text-ink">Share documents with TrustTrace?</h1>
          <p className="mt-1 text-sm text-ink-2">This page stands in for the real DigiLocker consent screen. No government system is contacted, and nothing here counts as verification.</p>
          {q.isLoading ? <Spinner /> : !q.data ? (
            <Notice tone="error">This request has expired or is invalid. Go back and start again.</Notice>
          ) : (
            <>
              <ul className="mt-4 divide-y divide-line rounded-lg border border-line text-[13px]">
                {q.data.documents.length ? q.data.documents.map((x, i) => <li key={i} className="px-3 py-2"><span className="font-medium">{x.name}</span><span className="block text-xs text-ink-3">{x.issuer} · {x.doctype}</span></li>)
                  : <li className="px-3 py-2 text-ink-3">No simulated records match this candidate. An administrator can load them with manage.py load-digilocker-records.</li>}
              </ul>
              <div className="mt-5 flex gap-2">
                <Button loading={decide.isPending} onClick={() => void decide.mutate(true)}>Allow</Button>
                <Button variant="secondary" onClick={() => void decide.mutate(false)}>Deny</Button>
              </div>
              {decide.error ? <div className="mt-3"><Notice tone="error">{errorMessage(decide.error)}</Notice></div> : null}
            </>
          )}
        </Card>
      </main>
    </div>
  );
}
