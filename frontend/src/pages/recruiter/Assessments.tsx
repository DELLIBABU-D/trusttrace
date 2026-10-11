import { useState } from "react";
import {
  LuBot, LuCheck, LuCircleCheck, LuCircleX, LuClipboardCheck, LuLibrary, LuPencil, LuPlus, LuSend, LuSparkles, LuTrash2, LuUserPen,
} from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { recruiterApi } from "../../api/endpoints";
import type { AssessmentAttemptDetail, AssessmentTemplate, ProofOfSkill, QuestionInput, TemplateQuestion } from "../../api/types";
import { DataState, NotLoaded } from "../../components/DataState";
import { outcomeMeta } from "../../components/Verify";
import { Button, ButtonLink, Card, CardHeader, EmptyState, Field, Modal, Notice, PageHeader, Pill, Spinner, cx, inputCls } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";
import { Link, useParams } from "../../lib/router";
import { ProofOfSkillTable } from "../candidate/Assessment";

const SOURCE: Record<TemplateQuestion["source"], { label: string; tone: "violet" | "blue" | "green"; icon: typeof LuBot }> = {
  gemini: { label: "AI-generated (Gemini)", tone: "violet", icon: LuBot },
  question_bank: { label: "Question bank", tone: "blue", icon: LuLibrary },
  recruiter: { label: "Written by recruiter", tone: "green", icon: LuUserPen },
};

/* ------------------------------------------------------------------ question editor */

const blank: QuestionInput = { skill: "", difficulty: "medium", prompt: "", code: "", options: ["", "", "", ""], correctOptionId: "a", explanation: "" };

function QuestionModal({ open, initial, skills, onClose, onSave, pending, error }: {
  open: boolean; initial: QuestionInput; skills: string[]; onClose: () => void; onSave: (q: QuestionInput) => void; pending: boolean; error: unknown;
}) {
  const [q, setQ] = useState<QuestionInput>(initial);
  const [err, setErr] = useState<Record<string, string>>({});
  const [lastInitial, setLastInitial] = useState(initial);
  if (initial !== lastInitial) (setLastInitial(initial), setQ(initial), setErr({}));
  function save() {
    const e: Record<string, string> = {};
    if (!q.skill.trim()) e.skill = "Pick or type a skill";
    if (q.prompt.trim().length < 10) e.prompt = "Write at least 10 characters";
    if (q.options.some((o) => !o.trim())) e.options = "Fill in all four options";
    else if (new Set(q.options.map((o) => o.trim().toLowerCase())).size !== 4) e.options = "Options must all be different";
    setErr(e);
    if (!Object.keys(e).length) onSave({ ...q, skill: q.skill.trim(), prompt: q.prompt.trim(), options: q.options.map((o) => o.trim()) });
  }
  return (
    <Modal open={open} onClose={onClose} title="Question" footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button loading={pending} onClick={save}>Save question</Button>
    </>}>
      <div className="max-h-[65vh] space-y-3 overflow-y-auto pr-1">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Skill" htmlFor="q-skill" error={err.skill} required>
            <input id="q-skill" list="q-skills" className={inputCls} value={q.skill} onChange={(e) => setQ({ ...q, skill: e.target.value })} />
            <datalist id="q-skills">{skills.map((s) => <option key={s} value={s} />)}</datalist>
          </Field>
          <Field label="Difficulty" htmlFor="q-diff">
            <select id="q-diff" className={inputCls} value={q.difficulty} onChange={(e) => setQ({ ...q, difficulty: e.target.value as QuestionInput["difficulty"] })}>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </select>
          </Field>
        </div>
        <Field label="Question" htmlFor="q-prompt" error={err.prompt} required><textarea id="q-prompt" rows={2} className={inputCls} value={q.prompt} onChange={(e) => setQ({ ...q, prompt: e.target.value })} /></Field>
        <Field label="Code (optional)" htmlFor="q-code"><textarea id="q-code" rows={3} className={cx(inputCls, "font-mono text-[13px]")} value={q.code} onChange={(e) => setQ({ ...q, code: e.target.value })} /></Field>
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium text-ink">Options — select the correct answer <span className="text-bad">*</span></legend>
          <div className="space-y-2">
            {q.options.map((o, i) => {
              const id = "abcd"[i];
              return (
                <div key={id} className="flex items-center gap-2">
                  <input type="radio" name="q-correct" aria-label={`Option ${id.toUpperCase()} is correct`} checked={q.correctOptionId === id} onChange={() => setQ({ ...q, correctOptionId: id })} className="size-4 accent-brand-600" />
                  <span className="w-4 text-[13px] font-medium text-ink-3">{id.toUpperCase()}</span>
                  <input aria-label={`Option ${id.toUpperCase()}`} id={`q-opt-${id}`} className={inputCls} value={o} onChange={(e) => setQ({ ...q, options: q.options.map((x, j) => (j === i ? e.target.value : x)) })} />
                </div>
              );
            })}
          </div>
          {err.options && <p className="mt-1 text-xs text-bad">{err.options}</p>}
        </fieldset>
        <Field label="Explanation (shown to recruiters)" htmlFor="q-expl"><input id="q-expl" className={inputCls} value={q.explanation} onChange={(e) => setQ({ ...q, explanation: e.target.value })} /></Field>
        {error ? <Notice tone="error" title="Not saved">{errorMessage(error)}</Notice> : null}
      </div>
    </Modal>
  );
}

const toInput = (q: TemplateQuestion): QuestionInput => ({
  skill: q.skill, difficulty: q.difficulty, prompt: q.prompt, code: q.code ?? "", options: q.options.map((o) => o.text), correctOptionId: q.correctOptionId, explanation: q.explanation,
});

/* ------------------------------------------------------------------ builder */

export function AssessmentBuilderPage() {
  const { id = "" } = useParams();
  const key = `recruiter:builder:${id}`;
  const q = useQuery(key, () => recruiterApi.builder(id));
  const [count, setCount] = useState(10);
  const [duration, setDuration] = useState(20);
  const [pass, setPass] = useState(60);
  const [editing, setEditing] = useState<{ q: TemplateQuestion | null; input: QuestionInput } | null>(null);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const inv = { invalidates: [key, "recruiter:assessments", "recruiter:dashboard"] };
  const gen = useMutation((source: "auto" | "bank") => recruiterApi.generateQuestions(id, { count, durationMinutes: duration, passPercent: pass, title: "", source, replace: false }), inv);
  const settings = useMutation((t: AssessmentTemplate) => recruiterApi.updateAssessment(id, { title: t.title, durationMinutes: duration, passPercent: pass }), inv);
  const save = useMutation((v: QuestionInput) => (editing?.q ? recruiterApi.editQuestion(editing.q.id, v) : recruiterApi.addQuestion(id, v)), { ...inv, onSuccess: () => setEditing(null) });
  const approve = useMutation((qid: string) => recruiterApi.approveQuestion(qid), inv);
  const remove = useMutation((qid: string) => recruiterApi.deleteQuestion(qid), inv);
  const publish = useMutation(() => recruiterApi.publishAssessment(id), { ...inv, onSuccess: () => setConfirmPublish(false) });
  const [synced, setSynced] = useState<string | null>(null);

  if (q.isLoading) return <Spinner label="Loading assessment" />;
  if (!q.data) return <><PageHeader title="Skill assessment" back={{ to: "/recruiter/jobs", label: "Jobs" }} /><Card><NotLoaded error={q.error} what="assessment" /></Card></>;
  const { job, template: t, geminiConfigured } = q.data;
  if (t && synced !== t.id) (setSynced(t.id), setDuration(t.durationMinutes), setPass(t.passPercent));
  const locked = t?.status === "published";
  const pendingCount = t ? t.questionCount - t.approvedCount : 0;
  const firstError = gen.error ?? approve.error ?? remove.error ?? settings.error;

  return (
    <div>
      <PageHeader title="Skill assessment" sub={`${job.title} · required skills: ${job.skills.join(", ")}`} back={{ to: "/recruiter/jobs", label: "Jobs" }}
        actions={t ? <Pill tone={locked ? "green" : "amber"}>{locked ? `Published · ${t.assignedCount} assigned · ${t.submittedCount} submitted` : "Draft"}</Pill> : undefined} />
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          {firstError ? <Notice tone="error">{errorMessage(firstError)}</Notice> : null}
          {t?.generationNote && !locked && <Notice tone="info">{t.generationNote}</Notice>}
          {!t || t.questions.length === 0 ? (
            <Card><EmptyState icon={LuClipboardCheck} title="No questions yet" action={<Button icon={LuPlus} variant="secondary" onClick={() => setEditing({ q: null, input: { ...blank, skill: job.skills[0] ?? "" } })}>Write a question</Button>}>
              Draft questions from the job's skills on the right, or write your own. Nothing reaches candidates until you approve every question and publish.
            </EmptyState></Card>
          ) : t.questions.map((qq, i) => {
            const src = SOURCE[qq.source];
            return (
              <Card key={qq.id} className="p-5">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-semibold text-ink-2">Q{i + 1}</span>
                  <Pill tone="gray">{qq.skill}</Pill>
                  <Pill tone={src.tone}><src.icon className="mr-1 size-3" aria-hidden />{src.label}{qq.edited ? " · edited" : ""}</Pill>
                  <span className="ml-auto">{qq.approved ? <Pill tone="green"><LuCheck className="mr-1 size-3" aria-hidden />Approved</Pill> : <Pill tone="amber">Needs your review</Pill>}</span>
                </div>
                <p className="mt-3 text-[14.5px] font-medium text-ink">{qq.prompt}</p>
                {qq.code && <pre className="mt-2 overflow-x-auto rounded-lg bg-navy-950 p-3 text-[12.5px] text-[#d6e6ea]"><code>{qq.code}</code></pre>}
                <ul className="mt-3 space-y-1.5">
                  {qq.options.map((o) => (
                    <li key={o.id} className={cx("flex items-center gap-2 rounded-md border px-3 py-2 text-[13.5px]", o.id === qq.correctOptionId ? "border-ok bg-ok-soft" : "border-line")}>
                      <span className="font-medium text-ink-3">{o.id.toUpperCase()}.</span><span className="flex-1">{o.text}</span>
                      {o.id === qq.correctOptionId && <span className="text-xs font-medium text-ok">Answer key</span>}
                    </li>
                  ))}
                </ul>
                {qq.explanation && <p className="mt-2 text-xs text-ink-3">Why: {qq.explanation}</p>}
                {!locked && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {!qq.approved && <Button size="sm" icon={LuCircleCheck} loading={approve.isPending} onClick={() => void approve.mutate(qq.id)}>Approve question & answer</Button>}
                    <Button size="sm" variant="secondary" icon={LuPencil} onClick={() => setEditing({ q: qq, input: toInput(qq) })}>Edit</Button>
                    <Button size="sm" variant="ghost" icon={LuTrash2} loading={remove.isPending} onClick={() => void remove.mutate(qq.id)}>Remove</Button>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
        <div className="space-y-4">
          <Card className="p-5">
            <h2 className="text-[15px] font-semibold">Settings</h2>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field label="Duration (min)" htmlFor="dur"><input id="dur" type="number" min={5} max={120} className={inputCls} disabled={locked} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></Field>
              <Field label="Pass mark (%)" htmlFor="pass"><input id="pass" type="number" min={0} max={100} className={inputCls} disabled={locked} value={pass} onChange={(e) => setPass(Number(e.target.value))} /></Field>
            </div>
            {t && !locked && <Button size="sm" variant="secondary" className="mt-3" loading={settings.isPending} onClick={() => void settings.mutate(t)}>Save settings</Button>}
            <p className="mt-3 text-xs text-ink-3">The pass mark only labels results. A score below it is never treated as dishonesty.</p>
          </Card>
          {!locked && (
            <Card className="p-5">
              <h2 className="text-[15px] font-semibold">Draft questions</h2>
              <p className="mt-1 text-[13px] text-ink-3">From the job's required skills. Every drafted question starts unapproved.</p>
              <Field label="How many" htmlFor="count" className="mt-3"><input id="count" type="number" min={3} max={20} className={inputCls} value={count} onChange={(e) => setCount(Number(e.target.value))} /></Field>
              <div className="mt-3 grid gap-2">
                {geminiConfigured && <Button icon={LuSparkles} loading={gen.isPending} onClick={() => void gen.mutate("auto")}>Draft with Gemini (AI)</Button>}
                <Button variant={geminiConfigured ? "secondary" : "primary"} icon={LuLibrary} loading={gen.isPending} onClick={() => void gen.mutate("bank")}>Draft from question bank</Button>
                <Button variant="secondary" icon={LuPlus} onClick={() => setEditing({ q: null, input: { ...blank, skill: job.skills[0] ?? "" } })}>Write my own question</Button>
              </div>
              {!geminiConfigured && <p className="mt-2 text-xs text-ink-3">Gemini isn't configured on this server (GEMINI_API_KEY), so the built-in question bank is used.</p>}
            </Card>
          )}
          <Card className="p-5">
            <h2 className="text-[15px] font-semibold">Publish</h2>
            {locked ? (
              <p className="mt-1 text-[13px] text-ink-2">Published {formatDateTime(t!.publishedAt)}. Questions are locked so every candidate gets the same test. New applicants receive it automatically.</p>
            ) : (
              <>
                <p className="mt-1 text-[13px] text-ink-2">{t ? `${t.approvedCount} of ${t.questionCount} questions approved.` : "No questions yet."} Publishing locks the questions and assigns the test to current and future applicants.</p>
                {publish.error ? <div className="mt-2"><Notice tone="error">{errorMessage(publish.error)}</Notice></div> : null}
                <Button className="mt-3 w-full" icon={LuSend} disabled={!t || t.questionCount === 0 || pendingCount > 0} onClick={() => setConfirmPublish(true)}>Publish assessment</Button>
                {pendingCount > 0 && <p className="mt-2 text-xs text-warn">Approve the remaining {pendingCount} question(s) first.</p>}
              </>
            )}
          </Card>
        </div>
      </div>
      <QuestionModal open={!!editing} initial={editing?.input ?? blank} skills={job.skills} onClose={() => (setEditing(null), save.reset())}
        onSave={(v) => void save.mutate(v)} pending={save.isPending} error={save.error} />
      <Modal open={confirmPublish} onClose={() => setConfirmPublish(false)} title="Publish this assessment?" footer={<>
        <Button variant="secondary" onClick={() => setConfirmPublish(false)}>Cancel</Button>
        <Button loading={publish.isPending} onClick={() => void publish.mutate(undefined)}>Publish</Button>
      </>}>
        <p className="text-sm text-ink-2">{t?.questionCount} questions, {duration} minutes. You won't be able to edit the questions afterwards. Every current applicant gets the test and a message.</p>
      </Modal>
    </div>
  );
}

/* ------------------------------------------------------------------ attempts list & detail */

export function RecruiterAssessments() {
  const q = useQuery("recruiter:assessments", recruiterApi.assessments);
  return (
    <div>
      <PageHeader title="Assessments" sub="Skill test attempts for your jobs. Build or publish a test from Jobs → Assessment." actions={<ButtonLink to="/recruiter/jobs" variant="secondary">Jobs</ButtonLink>} />
      <Card>
        <DataState query={q} isEmpty={(l) => l.length === 0} empty={{ icon: LuClipboardCheck, title: "No assessment attempts yet", body: "Publish an assessment for a job; applicants receive it automatically." }}>
          {(list) => (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[13.5px]">
                <thead className="border-y border-line bg-surface text-xs text-ink-3">
                  <tr><th className="px-5 py-2.5 font-medium">Candidate</th><th className="px-5 py-2.5 font-medium">Job</th><th className="px-5 py-2.5 font-medium">Status</th>
                    <th className="px-5 py-2.5 font-medium">Score</th><th className="px-5 py-2.5 font-medium">Review signals</th><th className="px-5 py-2.5" /></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {list.map((a) => {
                    const sig = a.signals.visibility_hidden + a.signals.window_blur + a.signals.copy + a.signals.paste + a.signals.cut;
                    return (
                      <tr key={a.id}>
                        <td className="px-5 py-3 font-medium text-ink">{a.candidateName}</td>
                        <td className="px-5 py-3 text-ink-2">{a.jobTitle}</td>
                        <td className="px-5 py-3">{a.status === "submitted" ? <Pill tone="green">Submitted</Pill> : a.status === "in_progress" ? <Pill tone="amber">In progress</Pill> : <Pill tone="blue">Assigned</Pill>}</td>
                        <td className="px-5 py-3 tabular-nums">{a.score != null ? `${a.score}/${a.maxScore} (${a.percent}%)` : "—"}</td>
                        <td className="px-5 py-3 tabular-nums text-ink-2">{a.status === "assigned" ? "—" : sig}</td>
                        <td className="px-5 py-3 text-right"><Link to={`/recruiter/assessments/${a.id}`} className="font-medium text-brand-700 hover:underline">Details</Link></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </Card>
    </div>
  );
}

const EVENT_LABEL: Record<string, string> = {
  started: "Started the test", resumed: "Reopened the test", submitted: "Submitted", time_up: "Time ran out – saved answers submitted",
  camera_granted: "Camera allowed", camera_denied: "Camera blocked or unavailable", camera_declined: "Chose to continue without camera",
  visibility_hidden: "Left the test tab", visibility_visible: "Returned to the test tab", window_blur: "Test window lost focus", window_focus: "Test window focused again",
  copy: "Copied text", paste: "Pasted text", cut: "Cut text", fullscreen_exit: "Left full screen", face_check: "Identity recheck",
};

export function AttemptTimeline({ a }: { a: AssessmentAttemptDetail }) {
  return (
    <ol className="divide-y divide-line">
      {a.timeline.map((e, i) => (
        <li key={i} className="flex items-start gap-3 px-5 py-2.5 text-[13px]">
          <span className="w-36 shrink-0 tabular-nums text-ink-3">{formatDateTime(e.at)}</span>
          <span className={cx("flex-1", e.reviewSignal ? "font-medium text-warn" : "text-ink")}>
            {EVENT_LABEL[e.kind] ?? e.kind}
            {e.kind === "face_check" && e.detail.decision ? ` – ${String(e.detail.decision).replace(/_/g, " ")}${e.detail.similarity != null ? ` (${Number(e.detail.similarity).toFixed(2)})` : ""}` : ""}
            {(e.kind === "paste" || e.kind === "copy" || e.kind === "cut") && e.detail.chars != null ? ` (${e.detail.chars} characters)` : ""}
          </span>
          {e.reviewSignal && <Pill tone="amber">Review signal</Pill>}
        </li>
      ))}
    </ol>
  );
}

export function AttemptDetailPage() {
  const { id = "" } = useParams();
  const q = useQuery(`recruiter:assessment:${id}`, () => recruiterApi.assessmentAttempt(id));
  if (q.isLoading) return <Spinner />;
  const a = q.data;
  if (!a) return <><PageHeader title="Assessment attempt" back={{ to: "/recruiter/assessments", label: "Assessments" }} /><Card><NotLoaded error={q.error} what="attempt" /></Card></>;
  const signals = Object.values(a.signals).reduce((x, y) => x + y, 0);
  return (
    <div>
      <PageHeader title={`${a.candidateName} · ${a.title}`} sub={`${a.jobTitle} · ${a.questionCount} questions · ${a.durationMinutes} min`} back={{ to: "/recruiter/assessments", label: "Assessments" }}
        actions={<ButtonLink to={`/recruiter/applicants/${a.applicationId}`} variant="secondary">Trust report</ButtonLink>} />
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="space-y-5">
          <Card>
            <CardHeader title="Answers" sub={a.status === "submitted" ? "Scored on the server against the approved answer key." : "Answers appear after submission."} />
            {a.answers ? (
              <ol className="divide-y divide-line">
                {a.answers.map((x, i) => (
                  <li key={x.id} className="px-5 py-3 text-[13.5px]">
                    <div className="flex items-start gap-2">
                      {x.correct ? <LuCircleCheck className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden /> : <LuCircleX className="mt-0.5 size-4 shrink-0 text-bad" aria-hidden />}
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-ink">Q{i + 1}. {x.prompt} <span className="font-normal text-ink-3">· {x.skill}</span></p>
                        <p className="mt-0.5 text-ink-2">Chose: {x.chosen ? `${x.chosen.toUpperCase()}. ${x.options.find((o) => o.id === x.chosen)?.text}` : "No answer"}
                          {!x.correct && <> · Answer key: {x.correctOptionId.toUpperCase()}. {x.options.find((o) => o.id === x.correctOptionId)?.text}</>}</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            ) : <EmptyState compact icon={LuClipboardCheck} title={a.status === "assigned" ? "Not started yet" : "In progress"} />}
          </Card>
          <Card>
            <CardHeader title="Activity timeline" sub="Tab switches, focus changes and copy/paste are review signals: they can have innocent causes (notifications, a second monitor) and are not proof of cheating." />
            {a.timeline.length ? <AttemptTimeline a={a} /> : <EmptyState compact icon={LuClipboardCheck} title="No activity yet" />}
          </Card>
        </div>
        <div className="space-y-5">
          <Card className="p-5">
            <p className="text-[13px] text-ink-3">Score</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{a.score != null ? <>{a.score}<span className="text-lg text-ink-3">/{a.maxScore}</span></> : "—"}</p>
            {a.percent != null && <p className="text-sm text-ink-2">{a.percent}%{a.passPercent != null && ` · pass mark ${a.passPercent}%`}</p>}
            <dl className="mt-4 space-y-1.5 text-[13px]">
              <div className="flex justify-between"><dt className="text-ink-3">Started</dt><dd>{formatDateTime(a.startedAt)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-3">Submitted</dt><dd>{formatDateTime(a.submittedAt)}{a.submitReason === "time_up" ? " (time up)" : ""}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-3">Camera</dt><dd>{a.cameraConsent == null ? "—" : a.cameraConsent ? "Allowed by candidate" : "Declined by candidate"}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-3">Review signals</dt><dd>{signals}</dd></div>
            </dl>
          </Card>
          <Card>
            <CardHeader title="By skill" />
            <ul className="divide-y divide-line">
              {Object.entries(a.perSkill).map(([s, v]) => <li key={s} className="flex justify-between px-5 py-2.5 text-[13.5px]"><span>{s}</span><span className="tabular-nums">{v.correct}/{v.total} ({v.percent}%)</span></li>)}
              {!Object.keys(a.perSkill).length && <li className="px-5 py-3 text-[13px] text-ink-3">Available after submission.</li>}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Identity rechecks" sub="Live camera frame vs. enrolment photo. Liveness isn't checked." />
            {a.faceChecks.length ? (
              <ul className="divide-y divide-line">
                {a.faceChecks.map((f, i) => (
                  <li key={i} className="flex items-center justify-between px-5 py-2.5 text-[13px]">
                    <span className="text-ink-2">{formatDateTime(f.at)}{f.similarity != null && ` · ${f.similarity.toFixed(2)}`}</span>
                    <Pill tone={outcomeMeta[f.outcome].tone}>{outcomeMeta[f.outcome].label}</Pill>
                  </li>
                ))}
              </ul>
            ) : <p className="px-5 pb-4 text-[13px] text-ink-3">{a.cameraConsent === false ? "The candidate chose not to use the camera." : "No recheck recorded."}</p>}
          </Card>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Proof of Skill card for the trust report */

export function SkillEvidence({ appId }: { appId: string }) {
  const q = useQuery<ProofOfSkill>(`recruiter:skills:${appId}`, () => recruiterApi.applicantSkills(appId));
  return (
    <Card>
      <CardHeader title="Proof of Skill" sub="Claimed skills (profile, resume) vs. performance in this job's assessment." />
      <DataState query={q} isEmpty={() => false} empty={{ icon: LuClipboardCheck, title: "" }}>
        {(d) => (
          <>
            <ProofOfSkillTable data={d} />
            {d.attemptsForThisJob?.length ? (
              <ul className="divide-y divide-line border-t border-line">
                {d.attemptsForThisJob.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 px-5 py-3 text-[13.5px]">
                    <span className="flex-1">{a.title}</span>
                    <span className="tabular-nums">{a.score != null ? `${a.score}/${a.maxScore} (${a.percent}%)` : a.status.replace("_", " ")}</span>
                    <Link to={`/recruiter/assessments/${a.id}`} className="font-medium text-brand-700 hover:underline">Details & timeline</Link>
                  </li>
                ))}
              </ul>
            ) : <p className="border-t border-line px-5 py-3 text-[13px] text-ink-3">No assessment for this job yet. Build one from Jobs → Assessment.</p>}
          </>
        )}
      </DataState>
    </Card>
  );
}
