import { useCallback, useEffect, useRef, useState } from "react";
import {
  LuArrowLeft, LuArrowRight, LuAward, LuCalendarCheck, LuCalendarClock, LuCamera, LuCameraOff, LuClipboardCheck, LuClock, LuCopy, LuExternalLink, LuEye,
  LuMic, LuMicOff, LuMonitorUp, LuPhoneOff, LuScanFace, LuShieldCheck, LuSquareStack, LuVideo, LuVideoOff, LuWifi, LuWifiOff,
} from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { candidateApi } from "../../api/endpoints";
import type { AssessmentSession, AssessmentSummary, IdentityCheckResult, Interview, ProofOfSkill } from "../../api/types";
import { outcomeMeta } from "../../components/Verify";
import { CameraView, useCamera } from "../../components/Camera";
import { DataState, NotLoaded } from "../../components/DataState";
import { Button, ButtonLink, Card, CardHeader, EmptyState, Field, Modal, Notice, PageHeader, Pill, Spinner, Tabs, cx, inputCls } from "../../components/ui";
import { formatClock, formatDateTime } from "../../lib/format";
import { invalidate, useMutation, useQuery } from "../../lib/query";
import { useNavigate, useParams } from "../../lib/router";

const statusPill = (a: AssessmentSummary) =>
  a.status === "submitted" ? <Pill tone="green">Submitted</Pill> : a.status === "in_progress" ? <Pill tone="amber">In progress</Pill> : <Pill tone="blue">Assigned</Pill>;

/* ------------------------------------------------------------------ Proof of Skill table (shared with the recruiter report) */

export function ProofOfSkillTable({ data }: { data: ProofOfSkill }) {
  if (!data.skills.length) return <EmptyState compact icon={LuAward} title="No skills to compare yet">Add skills to your profile or upload a resume.</EmptyState>;
  const tick = (v: boolean) => (v ? <span className="font-medium text-ok">Yes</span> : <span className="text-ink-3">—</span>);
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-[13.5px]">
          <thead className="border-y border-line bg-surface text-xs text-ink-3">
            <tr><th className="px-5 py-2.5 font-medium">Skill</th><th className="px-3 py-2.5 font-medium">Profile</th><th className="px-3 py-2.5 font-medium">Resume</th>
              <th className="px-3 py-2.5 font-medium">Required</th><th className="px-3 py-2.5 font-medium">Assessed</th><th className="px-5 py-2.5 font-medium">Note</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.skills.map((r) => (
              <tr key={r.skill}>
                <td className="px-5 py-2.5 font-medium text-ink">{r.skill}</td>
                <td className="px-3 py-2.5">{tick(r.profile)}</td>
                <td className="px-3 py-2.5">{tick(r.resume)}</td>
                <td className="px-3 py-2.5">{tick(r.required)}</td>
                <td className="px-3 py-2.5 tabular-nums">
                  {r.assessed ? <span className={cx("font-semibold", r.assessed.percent >= 60 ? "text-ok" : "text-warn")}>{r.assessed.percent}%</span> : <span className="text-ink-3">—</span>}
                  {r.assessed && <span className="ml-1 text-xs text-ink-3">({r.assessed.correct}/{r.assessed.total})</span>}
                </td>
                <td className="px-5 py-2.5 text-[13px] text-ink-2">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-3 text-xs text-ink-3">{data.disclaimer}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ assessments & interviews list */

function RespondModal({ interview, onClose }: { interview: Interview | null; onClose: () => void }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const respond = useMutation((n: string) => candidateApi.respondInterview(interview!.id, { response: "reschedule_requested", note: n }), {
    invalidates: ["candidate:interviews"], onSuccess: () => (setNote(""), onClose()),
  });
  return (
    <Modal open={!!interview} onClose={onClose} title="Ask for another time" footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button loading={respond.isPending} onClick={() => (note.trim().length < 5 ? setErr("Say which days and times suit you.") : (setErr(""), void respond.mutate(note.trim())))}>Send request</Button>
    </>}>
      <Field label="Which times suit you?" htmlFor="resched" error={err} required hint="The recruiter sees this next to the interview.">
        <textarea id="resched" rows={3} className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {respond.error ? <div className="mt-3"><Notice tone="error" title="Not sent">{errorMessage(respond.error)}</Notice></div> : null}
    </Modal>
  );
}

export function Assessments() {
  const [tab, setTab] = useState<"assessments" | "interviews">("assessments");
  const list = useQuery("candidate:assessments", candidateApi.assessments);
  const interviews = useQuery("candidate:interviews", candidateApi.interviews);
  const skills = useQuery("candidate:skills", candidateApi.skills);
  const [resched, setResched] = useState<Interview | null>(null);
  const accept = useMutation((id: string) => candidateApi.respondInterview(id, { response: "accepted", note: "" }), { invalidates: ["candidate:interviews"] });
  return (
    <div>
      <PageHeader title="Assessments & Interviews" sub="Skill tests and interviews assigned by recruiters for jobs you applied to."
        actions={<ButtonLink to="/candidate/interviews/check" variant="secondary" icon={LuVideo}>Test camera & network</ButtonLink>} />
      <div className="mb-4 max-w-sm">
        <Tabs label="Assessments or interviews" value={tab} onChange={setTab} tabs={[{ id: "assessments", label: "Assessments" }, { id: "interviews", label: "Interviews" }]} />
      </div>
      {tab === "assessments" ? (
        <div className="space-y-5">
          <Card>
            <DataState query={list} isEmpty={(l) => l.length === 0} empty={{ icon: LuClipboardCheck, title: "No assessments assigned", body: "When a recruiter publishes a skill test for a job you applied for, it shows up here." }}>
              {(items) => (
                <ul className="divide-y divide-line">
                  {items.map((a) => (
                    <li key={a.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-ink">{a.title}</p>
                        <p className="text-[13px] text-ink-3">{a.jobTitle} · {a.questionCount} questions · {a.durationMinutes} min
                          {a.submittedAt ? ` · submitted ${formatDateTime(a.submittedAt)}` : ""}</p>
                      </div>
                      {a.status === "submitted" && a.score != null && <span className="text-[13px] font-semibold tabular-nums text-ink">{a.score}/{a.maxScore} ({a.percent}%)</span>}
                      {statusPill(a)}
                      <ButtonLink to={`/candidate/assessments/${a.id}`} size="sm" variant={a.status === "submitted" ? "secondary" : "primary"}>
                        {a.status === "submitted" ? "View result" : a.status === "in_progress" ? "Resume" : "Start"}
                      </ButtonLink>
                    </li>
                  ))}
                </ul>
              )}
            </DataState>
          </Card>
          <Card>
            <CardHeader title="Proof of Skill" sub="Skills you claimed compared with what your assessments showed." />
            <DataState query={skills} isEmpty={() => false} empty={{ icon: LuAward, title: "" }}>{(d) => <ProofOfSkillTable data={d} />}</DataState>
          </Card>
        </div>
      ) : (
        <Card>
          {accept.error ? <div className="p-4"><Notice tone="error">{errorMessage(accept.error)}</Notice></div> : null}
          <DataState query={interviews} isEmpty={(l) => l.length === 0} empty={{ icon: LuCalendarClock, title: "No interviews scheduled", body: "Interview invitations from recruiters appear here." }}>
            {(items) => (
              <ul className="divide-y divide-line">
                {items.map((i) => (
                  <li key={i.id} className="flex flex-wrap items-center gap-3 px-5 py-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-ink">{i.jobTitle}</p>
                      <p className="text-[13px] text-ink-3">{formatDateTime(i.scheduledAt)} · {i.durationMinutes} min · {i.mode === "video" ? "video" : "on-site"} · with {i.interviewer}</p>
                      {i.candidateResponse && <p className="mt-1 text-xs text-ink-2">{i.candidateResponse === "accepted" ? "You accepted this invitation" : `You asked for another time: “${i.candidateNote}”`}</p>}
                    </div>
                    <Pill tone={i.status === "scheduled" ? "blue" : i.status === "completed" ? "green" : "gray"}>{i.status[0].toUpperCase() + i.status.slice(1)}</Pill>
                    {i.status === "scheduled" && !i.candidateResponse && (
                      <>
                        <Button size="sm" variant="secondary" icon={LuCalendarCheck} loading={accept.isPending} onClick={() => void accept.mutate(i.id)}>Accept</Button>
                        <Button size="sm" variant="ghost" onClick={() => setResched(i)}>Other time</Button>
                      </>
                    )}
                    {i.status === "scheduled" && i.mode === "video" && <ButtonLink to={`/candidate/interviews/${i.id}`} size="sm" icon={LuVideo}>Enter</ButtonLink>}
                  </li>
                ))}
              </ul>
            )}
          </DataState>
        </Card>
      )}
      <RespondModal interview={resched} onClose={() => setResched(null)} />
    </div>
  );
}

/* ------------------------------------------------------------------ integrity signals (visible to the candidate) */

type Ev = { type: string; clientAt: string; detail?: Record<string, string | number | boolean> };

function useIntegrityEvents(assessmentId: string, active: boolean) {
  const queue = useRef<Ev[]>([]);
  const [counts, setCounts] = useState({ tab: 0, focus: 0, clip: 0 });
  const flush = useCallback(async () => {
    const batch = queue.current.splice(0, 50);
    if (!batch.length) return;
    try {
      await candidateApi.assessmentEvents(assessmentId, batch);
    } catch {
      queue.current.unshift(...batch); // retry on the next flush
    }
  }, [assessmentId]);
  useEffect(() => {
    if (!active) return;
    const push = (type: string, detail?: Ev["detail"]) => queue.current.push({ type, clientAt: new Date().toISOString(), detail });
    const onVis = () => {
      if (document.visibilityState === "hidden") (push("visibility_hidden"), setCounts((c) => ({ ...c, tab: c.tab + 1 })));
      else push("visibility_visible");
    };
    const onBlur = () => (push("window_blur"), setCounts((c) => ({ ...c, focus: c.focus + 1 })));
    const onFocus = () => push("window_focus");
    const onClip = (e: ClipboardEvent) => {
      const text = e.type === "paste" ? e.clipboardData?.getData("text") ?? "" : String(window.getSelection() ?? "");
      push(e.type, { chars: text.length }); // only the length is recorded, never the text
      setCounts((c) => ({ ...c, clip: c.clip + 1 }));
    };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("copy", onClip);
    document.addEventListener("cut", onClip);
    document.addEventListener("paste", onClip);
    const t = window.setInterval(() => void flush(), 3000);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("copy", onClip);
      document.removeEventListener("cut", onClip);
      document.removeEventListener("paste", onClip);
      window.clearInterval(t);
      void flush();
    };
  }, [active, flush]);
  return { counts, flush };
}

/* ------------------------------------------------------------------ identity recheck */

function useIdentityRecheck(cam: ReturnType<typeof useCamera>, stage: "assessment" | "interview", referenceId: string | undefined, auto: boolean) {
  const [result, setResult] = useState<IdentityCheckResult | null>(null);
  const check = useMutation((image: string) => candidateApi.identityCheck({ stage, referenceId, image }), { onSuccess: setResult });
  const done = useRef(false);
  function run() {
    const image = cam.capture();
    if (image) void check.mutate(image);
  }
  useEffect(() => {
    if (!auto || done.current || cam.state !== "ready") return;
    done.current = true;
    const t = window.setTimeout(run, 1500); // let the camera adjust exposure first
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cam.state, auto]);
  return { result, run, pending: check.isPending, error: check.error };
}

function OutcomeText({ result, pending, error, idle = "Not checked" }: { result: IdentityCheckResult | null; pending: boolean; error: unknown; idle?: string }) {
  if (pending) return <span className="font-medium text-ink-3">Checking…</span>;
  if (error) return <span className="font-medium text-warn">Unavailable</span>;
  if (!result) return <span className="font-medium text-ink-3">{idle}</span>;
  const m = outcomeMeta[result.outcome];
  return <span className={cx("font-medium", m.tone === "green" ? "text-ok" : "text-warn")}>{m.label}</span>;
}

/* ------------------------------------------------------------------ (h) skill assessment: consent → test → result */

function ConsentStep({ session, onStarted }: { session: AssessmentSession; onStarted: (s: AssessmentSession, camOn: boolean) => void }) {
  const cam = useCamera(false);
  const [wantCamera, setWantCamera] = useState<boolean | null>(null);
  const start = useMutation((b: { cameraConsent: boolean; cameraState: "granted" | "denied" | "unavailable" | "declined" }) => candidateApi.startAssessment(session.id, b), {
    invalidates: ["candidate:assessments"], onSuccess: (s) => (cam.stop(), onStarted(s, s.cameraConsent === true && cam.state === "ready")),
  });
  useEffect(() => {
    if (wantCamera !== true || start.isPending || start.data) return;
    if (cam.state === "ready") void start.mutate({ cameraConsent: true, cameraState: "granted" });
    if (cam.state === "denied" || cam.state === "unavailable") void start.mutate({ cameraConsent: true, cameraState: cam.state });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cam.state, wantCamera]);
  return (
    <div>
      <PageHeader title="Skill Assessment" sub={session.title} back={{ to: "/candidate/assessments", label: "Assessments" }} />
      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <Card className="p-5 sm:p-6">
          <h2 className="text-[15px] font-semibold">Before you start</h2>
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[13.5px] text-ink-2">
            <li>{session.questionCount} multiple-choice questions, {Math.round(session.durationSeconds / 60)} minutes. The timer starts when you press Start and keeps running if you leave.</li>
            <li>Your answers are saved as you go. When time runs out, the answers saved so far are submitted.</li>
            <li>You can submit only once.</li>
            <li>The page notes when you switch tabs, leave the window, or copy/paste (only the number of characters, never the text). These are shown to the recruiter as <strong>review signals</strong>, not as proof of cheating.</li>
            <li><strong>Camera (optional):</strong> if you allow it, one frame is compared with your enrolment photo to confirm it's you. Video is not recorded or stored. If you prefer not to, you can still take the test; the recruiter just sees that the identity check was skipped.</li>
          </ul>
          {start.error ? <div className="mt-4"><Notice tone="error" title="Couldn't start">{errorMessage(start.error)}</Notice></div> : null}
          {wantCamera && (cam.state === "denied" || cam.state === "unavailable") && !start.error && (
            <div className="mt-4"><Notice tone="warn">Camera {cam.state === "denied" ? "permission was denied" : "isn't available"}. Starting without the identity check.</Notice></div>
          )}
          <div className="mt-6 flex flex-wrap gap-2">
            <Button icon={LuCamera} loading={start.isPending && wantCamera === true} disabled={start.isPending} onClick={() => (setWantCamera(true), void cam.start())}>Allow camera and start</Button>
            <Button variant="secondary" icon={LuCameraOff} loading={start.isPending && wantCamera === false} disabled={start.isPending}
              onClick={() => (setWantCamera(false), void start.mutate({ cameraConsent: false, cameraState: "declined" }))}>Start without camera</Button>
          </div>
        </Card>
        <Card className="p-4">
          <p className="mb-2 text-[13px] font-medium text-ink">Camera preview</p>
          <CameraView cam={cam} className="aspect-[4/3]" />
          <p className="mt-2 text-xs text-ink-3">The camera only turns on if you choose "Allow camera".</p>
        </Card>
      </div>
    </div>
  );
}

function Runner({ initial, cameraOn }: { initial: AssessmentSession; cameraOn: boolean }) {
  const cam = useCamera(cameraOn);
  const session = initial;
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>(session.savedAnswers ?? {});
  const [remaining, setRemaining] = useState(session.remainingSeconds);
  const [confirm, setConfirm] = useState(false);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const integrity = useIntegrityEvents(session.id, true);
  const recheck = useIdentityRecheck(cam, "assessment", session.id, cameraOn);
  const submit = useMutation(async () => {
    await integrity.flush();
    return candidateApi.submitAssessment(session.id, answers);
  }, { invalidates: ["candidate:"] });

  // countdown (server-authoritative: remainingSeconds came from the server)
  useEffect(() => {
    const t = window.setInterval(() => setRemaining((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(t);
  }, []);
  useEffect(() => {
    if (remaining === 0 && !submit.isPending && !submit.data && !submit.error) void submit.mutate(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining]);
  // autosave answers
  const first = useRef(true);
  useEffect(() => {
    if (first.current) return void (first.current = false);
    setSaveState("saving");
    const t = window.setTimeout(() => {
      candidateApi.saveAnswers(session.id, answers).then((r) => (setSaveState("saved"), setRemaining(r.remainingSeconds)), () => setSaveState("error"));
    }, 700);
    return () => window.clearTimeout(t);
  }, [answers, session.id]);

  if (submit.data) return <ResultView attempt={submit.data} />;

  const q = session.questions[index];
  const answered = Object.keys(answers).length;
  const diffTone = { easy: "green", medium: "amber", hard: "red" } as const;

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Skill Assessment</h1>
          <p className="text-sm text-ink-2">{session.title}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-ink-3" aria-live="polite">{saveState === "saving" ? "Saving…" : saveState === "error" ? "Not saved – retrying on next change" : "All answers saved"}</span>
          <div className={cx("flex items-center gap-2 rounded-lg border px-3 py-1.5 font-semibold tabular-nums", remaining < 60 ? "border-bad bg-bad-soft text-bad" : "border-line bg-white text-ink")} role="timer" aria-label="Time remaining">
            <LuClock className="size-4" aria-hidden /> {formatClock(remaining)}
          </div>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <Card className="p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between text-[13px]">
            <span className="font-medium text-ink-2">Question {index + 1} of {session.questions.length}{q.skill ? ` · ${q.skill}` : ""}</span>
            <Pill tone={diffTone[q.difficulty]}>{q.difficulty[0].toUpperCase() + q.difficulty.slice(1)}</Pill>
          </div>
          <fieldset>
            <legend className="text-[15px] font-medium text-ink">{q.prompt}</legend>
            {q.code && <pre className="mt-3 overflow-x-auto rounded-lg bg-navy-950 p-4 text-[13px] leading-relaxed text-[#d6e6ea]"><code>{q.code}</code></pre>}
            <div className="mt-4 space-y-2">
              {q.options.map((o, i) => (
                <label key={o.id} className={cx("flex cursor-pointer items-center gap-3 rounded-lg border px-3.5 py-3 text-[14px] transition-colors", answers[q.id] === o.id ? "border-brand-500 bg-brand-50" : "border-line hover:border-line-strong")}>
                  <input type="radio" name={q.id} value={o.id} checked={answers[q.id] === o.id} onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.id }))} className="size-4 accent-brand-600" />
                  <span className="font-medium text-ink-3">{String.fromCharCode(65 + i)}.</span>
                  <span className="text-ink">{o.text}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {submit.error ? <div className="mt-4"><Notice tone="error" title="Answers not submitted">{errorMessage(submit.error)}</Notice></div> : null}
          <div className="mt-6 flex items-center justify-between gap-3">
            <Button variant="secondary" icon={LuArrowLeft} disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>Previous</Button>
            {index < session.questions.length - 1 ? (
              <Button onClick={() => setIndex((i) => i + 1)}>Next <LuArrowRight className="size-4" aria-hidden /></Button>
            ) : (
              <Button onClick={() => setConfirm(true)} loading={submit.isPending}>Submit</Button>
            )}
          </div>
          <nav aria-label="Questions" className="mt-6 flex flex-wrap gap-1.5 border-t border-line pt-4">
            {session.questions.map((qq, i) => (
              <button key={qq.id} onClick={() => setIndex(i)} aria-current={i === index ? "step" : undefined} aria-label={`Question ${i + 1}${answers[qq.id] ? ", answered" : ""}`}
                className={cx("size-8 rounded-md text-xs font-semibold", i === index ? "bg-brand-600 text-white" : answers[qq.id] ? "bg-brand-100 text-brand-800" : "bg-surface text-ink-2 hover:bg-line")}>
                {i + 1}
              </button>
            ))}
          </nav>
        </Card>
        <div className="space-y-4">
          <Card className="p-4">
            <p className="mb-2 flex items-center justify-between text-[13px] font-medium text-ink">Live Proctoring {cam.state === "ready" && <span className="flex items-center gap-1 text-xs text-bad"><span className="size-1.5 rounded-full bg-bad" /> LIVE</span>}</p>
            {cameraOn ? <CameraView cam={cam} className="aspect-[4/3]" /> : (
              <div className="grid aspect-[4/3] place-items-center rounded-lg bg-[#dfe5e8] p-4 text-center text-[13px] text-ink-2">
                <span><LuCameraOff className="mx-auto mb-1 size-6 text-ink-3" aria-hidden />You chose to take this test without the camera.</span>
              </div>
            )}
          </Card>
          <Card className="p-4">
            <p className="mb-2 text-[13px] font-medium text-ink">Monitoring</p>
            <ul className="space-y-2 text-[13px]">
              <li className="flex items-center gap-2"><LuScanFace className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Webcam</span><span className={cam.state === "ready" ? "font-medium text-ok" : "font-medium text-ink-3"}>{cam.state === "ready" ? "Camera on" : cameraOn ? (cam.state === "denied" ? "Blocked" : "Off") : "Not used"}</span></li>
              <li className="flex items-center gap-2"><LuShieldCheck className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Identity</span><OutcomeText {...recheck} idle={cameraOn ? "Not checked" : "Skipped"} /></li>
              <li className="flex items-center gap-2"><LuSquareStack className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Tab switches</span><span className={cx("font-medium tabular-nums", integrity.counts.tab ? "text-warn" : "text-ok")}>{integrity.counts.tab}</span></li>
              <li className="flex items-center gap-2"><LuEye className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Window focus lost</span><span className={cx("font-medium tabular-nums", integrity.counts.focus ? "text-warn" : "text-ok")}>{integrity.counts.focus}</span></li>
              <li className="flex items-center gap-2"><LuCopy className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Copy / paste</span><span className={cx("font-medium tabular-nums", integrity.counts.clip ? "text-warn" : "text-ok")}>{integrity.counts.clip}</span></li>
              <li className="flex items-center gap-2"><LuClipboardCheck className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Answered</span><span className="font-medium tabular-nums text-ink">{answered}/{session.questions.length}</span></li>
            </ul>
            {recheck.result && recheck.result.outcome !== "matched" && <p className="mt-2 text-xs text-warn">{recheck.result.message}</p>}
            {cameraOn && <button onClick={recheck.run} disabled={cam.state !== "ready" || recheck.pending} className="mt-2 text-xs font-medium text-brand-700 hover:underline disabled:opacity-50">Check my face again</button>}
            <p className="mt-2 text-xs text-ink-3">These counts are review signals for a person, not proof of anything. Only one camera frame is compared; nothing is recorded.</p>
          </Card>
        </div>
      </div>
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Submit assessment?" footer={<>
        <Button variant="secondary" onClick={() => setConfirm(false)}>Keep working</Button>
        <Button loading={submit.isPending} onClick={() => (setConfirm(false), void submit.mutate(undefined))}>Submit answers</Button>
      </>}>
        <p className="text-sm text-ink-2">You answered {answered} of {session.questions.length} questions. You can submit only once.</p>
      </Modal>
    </div>
  );
}

function ResultView({ attempt }: { attempt: AssessmentSummary }) {
  const passed = attempt.passPercent != null && attempt.percent != null && attempt.percent >= attempt.passPercent;
  return (
    <div>
      <PageHeader title="Assessment result" sub={`${attempt.title} · ${attempt.jobTitle}`} back={{ to: "/candidate/assessments", label: "Assessments" }} />
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <Card className="p-6 text-center">
          <p className="text-[13px] text-ink-3">Your score</p>
          <p className="mt-1 text-4xl font-semibold tabular-nums">{attempt.score}<span className="text-xl text-ink-3">/{attempt.maxScore}</span></p>
          <p className="mt-1 text-sm font-medium text-ink-2">{attempt.percent}%{attempt.passPercent != null && ` · pass mark ${attempt.passPercent}%`}</p>
          {attempt.passPercent != null && <div className="mt-3"><Pill tone={passed ? "green" : "amber"}>{passed ? "At or above the pass mark" : "Below the pass mark"}</Pill></div>}
          <p className="mt-4 text-xs text-ink-3">Submitted {formatDateTime(attempt.submittedAt)}{attempt.submitReason === "time_up" ? " (time ran out; saved answers were used)" : ""}.</p>
        </Card>
        <Card>
          <CardHeader title="By skill" sub="A score reflects this short test only. It is shared with the recruiter as one piece of evidence." />
          <ul className="divide-y divide-line">
            {Object.entries(attempt.perSkill).map(([skill, s]) => (
              <li key={skill} className="flex items-center gap-3 px-5 py-3 text-[13.5px]">
                <span className="flex-1 font-medium text-ink">{skill}</span>
                <span className="w-40"><span className="block h-2 overflow-hidden rounded-full bg-line"><span className="block h-full rounded-full bg-brand-500" style={{ width: `${s.percent}%` }} /></span></span>
                <span className="w-20 text-right tabular-nums text-ink-2">{s.correct}/{s.total} ({s.percent}%)</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

export function AssessmentRunner() {
  const { id = "" } = useParams();
  const q = useQuery(`candidate:assessment:${id}`, () => candidateApi.assessment(id));
  const list = useQuery("candidate:assessments", candidateApi.assessments);
  const [started, setStarted] = useState<{ session: AssessmentSession; camOn: boolean } | null>(null);
  if (q.isLoading) return <Spinner label="Loading assessment" />;
  if (!q.data) return <><PageHeader title="Skill Assessment" back={{ to: "/candidate/assessments", label: "Assessments" }} /><Card><NotLoaded error={q.error} what="assessment" /></Card></>;
  if (q.data.status === "submitted") {
    const attempt = list.data?.find((a) => a.id === id);
    return attempt ? <ResultView attempt={attempt} /> : <Spinner />;
  }
  if (q.data.questionCount === 0)
    return <><PageHeader title={q.data.title} back={{ to: "/candidate/assessments", label: "Assessments" }} /><Card><EmptyState icon={LuClipboardCheck} title="This assessment has no questions yet">The recruiter hasn't added questions. Check back later.</EmptyState></Card></>;
  if (started) return <Runner initial={started.session} cameraOn={started.camOn} />;
  if (q.data.status === "in_progress") return <ResumeStep session={q.data} onResume={(s, camOn) => setStarted({ session: s, camOn })} />;
  return <ConsentStep session={q.data} onStarted={(s, camOn) => setStarted({ session: s, camOn })} />;
}

function ResumeStep({ session, onResume }: { session: AssessmentSession; onResume: (s: AssessmentSession, camOn: boolean) => void }) {
  const resume = useMutation(() => candidateApi.startAssessment(session.id, { cameraConsent: session.cameraConsent ?? false, cameraState: "declined" }), {
    onSuccess: (s) => onResume(s, s.cameraConsent === true),
  });
  useEffect(() => void resume.mutate(undefined), []); // eslint-disable-line react-hooks/exhaustive-deps
  if (resume.error) return <><PageHeader title="Skill Assessment" back={{ to: "/candidate/assessments", label: "Assessments" }} /><Card className="p-5"><Notice tone="warn">{errorMessage(resume.error)}</Notice><div className="mt-3"><ButtonLink to="/candidate/assessments" variant="secondary">Back to assessments</ButtonLink></div></Card></>;
  return <Spinner label="Resuming your assessment" />;
}

/* ------------------------------------------------------------------ (i) interview: identity step at entry */

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => (window.removeEventListener("online", on), window.removeEventListener("offline", off));
  }, []);
  return online;
}

/** EXPERIMENTAL: shows microphone input level only. It can't tell voices apart and is never saved or used as evidence. */
function useMicLevel() {
  const [level, setLevel] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stop = useRef<() => void>(() => undefined);
  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AC();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      let raf = 0;
      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
        raf = requestAnimationFrame(tick);
      };
      tick();
      stop.current = () => (cancelAnimationFrame(raf), stream.getTracks().forEach((t) => t.stop()), void ctx.close(), setLevel(null));
      setError(null);
    } catch {
      setError("Microphone permission was denied or no microphone was found.");
    }
  }
  useEffect(() => () => stop.current(), []);
  return { level, error, start, stop: () => stop.current() };
}

function InterviewRoom({ interview, testOnly }: { interview: Interview | undefined; testOnly: boolean }) {
  const navigate = useNavigate();
  const cam = useCamera(true);
  const online = useOnline();
  const mic = useMicLevel();
  const [current, setCurrent] = useState<Interview | undefined>(interview);
  const [entry, setEntry] = useState<IdentityCheckResult | null>(null);
  const [video, setVideo] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const enter = useMutation((body: { image?: string; camera: "ok" | "denied" | "unavailable" }) => candidateApi.interviewEntry(interview!.id, body), {
    onSuccess: (r) => (setEntry(r), setCurrent(r.interview), invalidate("candidate:interviews")),
  });
  const recheck = useIdentityRecheck(cam, "interview", undefined, false); // test page only
  useEffect(() => {
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  async function share() {
    if (sharing) return setSharing(false);
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      setSharing(true);
      setShareError(null);
      stream.getVideoTracks()[0]?.addEventListener("ended", () => setSharing(false));
    } catch {
      setShareError("Screen sharing was cancelled or isn't supported in this browser.");
    }
  }
  function toggleVideo() {
    if (video) cam.stop();
    else void cam.start();
    setVideo((v) => !v);
  }
  function verifyAndEnter() {
    const image = cam.capture();
    if (image) void enter.mutate({ image, camera: "ok" });
  }
  const ctl = "grid size-11 place-items-center rounded-full transition-colors";
  const result = testOnly ? recheck.result : entry;
  const outcome = result ? outcomeMeta[result.outcome] : null;

  return (
    <div>
      <PageHeader title="Interview Identity Verification" sub={current ? `${current.jobTitle} · with ${current.interviewer} · ${formatDateTime(current.scheduledAt)}` : "Check your camera, microphone and connection before an interview."}
        back={{ to: "/candidate/assessments", label: "Assessments" }} />
      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <Card className="overflow-hidden">
          <div className="relative">
            <CameraView cam={cam} className="aspect-video rounded-none" />
            <span className="absolute top-3 left-3 rounded-md bg-navy-950/70 px-2 py-1 text-xs font-medium text-white tabular-nums">{formatClock(seconds)}</span>
            <span className="absolute bottom-3 left-3 rounded-md bg-navy-950/70 px-2 py-1 text-xs text-white">Your camera preview · not recorded</span>
            {sharing && <span className="absolute top-3 right-3 rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white">Sharing screen</span>}
          </div>
          <div className="flex items-center justify-center gap-3 border-t border-line bg-white p-3">
            <button onClick={() => (mic.level == null ? void mic.start() : mic.stop())} aria-pressed={mic.level != null} aria-label={mic.level == null ? "Test microphone" : "Stop microphone test"}
              className={cx(ctl, mic.level != null ? "bg-brand-100 text-brand-700" : "bg-surface text-ink hover:bg-line")}>{mic.level != null ? <LuMic className="size-5" aria-hidden /> : <LuMicOff className="size-5" aria-hidden />}</button>
            <button onClick={toggleVideo} aria-pressed={!video} aria-label={video ? "Turn camera off" : "Turn camera on"} className={cx(ctl, video ? "bg-surface text-ink hover:bg-line" : "bg-bad-soft text-bad")}>{video ? <LuVideo className="size-5" aria-hidden /> : <LuVideoOff className="size-5" aria-hidden />}</button>
            <button onClick={() => void share()} aria-pressed={sharing} aria-label={sharing ? "Stop sharing" : "Test screen sharing"} className={cx(ctl, sharing ? "bg-brand-100 text-brand-700" : "bg-surface text-ink hover:bg-line")}><LuMonitorUp className="size-5" aria-hidden /></button>
            <button onClick={() => (cam.stop(), mic.stop(), navigate("/candidate/assessments"))} aria-label="Leave" className={cx(ctl, "bg-bad text-white hover:opacity-90")}><LuPhoneOff className="size-5" aria-hidden /></button>
          </div>
          {shareError && <div className="px-4 pb-4"><Notice tone="warn" onClose={() => setShareError(null)}>{shareError}</Notice></div>}
          <p className="border-t border-line px-4 py-3 text-xs text-ink-3">TrustTrace does not host the video call. After the identity step you join the interviewer's meeting link (Google Meet, Teams, Zoom…).</p>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader title="Identity Check" />
            <ul className="space-y-3 px-5 pb-4 text-[13px]">
              <li className="flex items-center gap-2"><LuScanFace className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Face vs. enrolment</span>
                {testOnly ? <OutcomeText {...recheck} /> : <OutcomeText result={entry} pending={enter.isPending} error={enter.error} />}</li>
              <li className="flex items-center gap-2"><LuShieldCheck className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Liveness</span><Pill tone="gray">Not checked</Pill></li>
              <li className="flex items-center gap-2"><LuVideo className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Camera</span><Pill tone={cam.state === "ready" ? "green" : "amber"}>{cam.state === "ready" ? "On" : cam.state === "denied" ? "Blocked" : "Off"}</Pill></li>
            </ul>
            <div className="space-y-2 px-5 pb-5">
              {testOnly ? (
                <Button variant="secondary" icon={LuScanFace} className="w-full" loading={recheck.pending} disabled={cam.state !== "ready"} onClick={recheck.run}>Verify my identity</Button>
              ) : current?.entryCheckedAt && current.meetingLink ? (
                <a href={current.meetingLink} target="_blank" rel="noreferrer noopener" className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700">
                  <LuExternalLink className="size-4" aria-hidden /> Join the interview call
                </a>
              ) : (
                <>
                  <Button icon={LuScanFace} className="w-full" loading={enter.isPending} disabled={cam.state !== "ready" || !current} onClick={verifyAndEnter}>Verify identity & enter</Button>
                  {(cam.state === "denied" || cam.state === "unavailable") && current && (
                    <Button variant="secondary" className="w-full" loading={enter.isPending} onClick={() => void enter.mutate({ camera: cam.state === "denied" ? "denied" : "unavailable" })}>Continue without camera</Button>
                  )}
                </>
              )}
              {!testOnly && current?.entryCheckedAt && !current.meetingLink && <Notice tone="info">The interviewer hasn't added a meeting link. They'll contact you.</Notice>}
              {result && outcome && (
                <Notice tone={result.outcome === "matched" ? "success" : "warn"} title={outcome.label}>
                  {result.message}{result.similarity != null && ` (similarity ${result.similarity.toFixed(2)})`}
                  {result.outcome !== "matched" && !testOnly && " You can still join; the interviewer will confirm your identity."}
                </Notice>
              )}
              {enter.error ? <Notice tone="error">{errorMessage(enter.error)}</Notice> : null}
            </div>
          </Card>
          <Card>
            <CardHeader title="Environment" />
            <ul className="space-y-3 px-5 pb-5 text-[13px]">
              <li className="flex items-center gap-2">{online ? <LuWifi className="size-4 text-ok" aria-hidden /> : <LuWifiOff className="size-4 text-bad" aria-hidden />}<span className="flex-1 text-ink-2">Network</span><span className={online ? "font-medium text-ok" : "font-medium text-bad"}>{online ? "Online" : "Offline"}</span></li>
              <li className="text-ink-2">
                <div className="flex items-center gap-2"><LuMic className="size-4 text-ink-3" aria-hidden /><span className="flex-1">Microphone level</span><Pill tone="violet">Experimental</Pill></div>
                {mic.level != null ? (
                  <span className="mt-2 block h-2 overflow-hidden rounded-full bg-line" role="meter" aria-label="Microphone level" aria-valuenow={Math.round(mic.level * 100)} aria-valuemin={0} aria-valuemax={100}>
                    <span className="block h-full rounded-full bg-brand-500 transition-[width]" style={{ width: `${Math.round(mic.level * 100)}%` }} />
                  </span>
                ) : <button onClick={() => void mic.start()} className="mt-1 text-xs font-medium text-brand-700 hover:underline">Test microphone</button>}
                {mic.error && <p className="mt-1 text-xs text-warn">{mic.error}</p>}
                <p className="mt-1 text-xs text-ink-3">Shows input level only, on this device. It can't tell voices apart, is never saved, and is never used as evidence.</p>
              </li>
              <li className="flex items-center gap-2"><LuMonitorUp className="size-4 text-ink-3" aria-hidden /><span className="flex-1 text-ink-2">Screen share</span><span className="font-medium text-ink">{sharing ? "Working" : "Not tested"}</span></li>
            </ul>
          </Card>
          <p className="text-xs text-ink-3">One camera frame is compared with your enrolment photo and only the result is saved. Liveness isn't checked, so the result is a signal for the interviewer, not a decision. More than one face in view is flagged for review.</p>
        </div>
      </div>
    </div>
  );
}

export function InterviewVerification() {
  const { id = "" } = useParams();
  const testOnly = id === "check";
  const q = useQuery(`candidate:interview:${id}`, () => candidateApi.interview(id), { enabled: !!id && !testOnly });
  if (q.isLoading && !testOnly) return <Spinner label="Loading interview" />;
  if (!testOnly && !q.data) return <><PageHeader title="Interview" back={{ to: "/candidate/assessments", label: "Assessments" }} /><Card><NotLoaded error={q.error} what="interview" /></Card></>;
  if (!testOnly && q.data && q.data.status !== "scheduled")
    return <><PageHeader title="Interview" back={{ to: "/candidate/assessments", label: "Assessments" }} /><Card><EmptyState icon={LuCalendarClock} title={`This interview is ${q.data.status}`}>Check your Messages for updates.</EmptyState></Card></>;
  return <InterviewRoom interview={q.data} testOnly={testOnly} />;
}

