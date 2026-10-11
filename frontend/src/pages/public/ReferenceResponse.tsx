import { useState } from "react";
import { z } from "zod";
import { LuCircleCheck } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { referenceApi } from "../../api/endpoints";
import { NotLoaded } from "../../components/DataState";
import { Logo } from "../../components/Logo";
import { Button, Card, Field, Notice, Spinner, inputCls } from "../../components/ui";
import { useZodForm } from "../../lib/form";
import { useMutation, useQuery } from "../../lib/query";
import { useParams } from "../../lib/router";

const month = z.union([z.literal(""), z.string().regex(/^\d{4}-\d{2}$/, "Use the month picker")]);
const schema = z.object({
  confirmed: z.enum(["yes", "no"], { errorMap: () => ({ message: "Choose an answer" }) }),
  title: z.string().trim().max(120),
  start: month,
  end: month,
  comments: z.string().trim().max(2000),
  responderName: z.string().trim().min(2, "Enter your name"),
  responderRole: z.string().trim().max(120),
});
type Values = z.infer<typeof schema>;

/** One-time page for a referee / HR contact. No account needed; the link itself is the credential. */
export function ReferenceResponse() {
  const { token = "" } = useParams();
  const q = useQuery(`reference:${token}`, () => referenceApi.view(token));
  const form = useZodForm(schema, { confirmed: "" as unknown as "yes", title: "", start: "", end: "", comments: "", responderName: "", responderRole: "" });
  const [done, setDone] = useState(false);
  const send = useMutation((v: Values) => referenceApi.respond(token, { ...v, confirmed: v.confirmed === "yes" }), { onSuccess: () => setDone(true) });
  const r = q.data;
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-line bg-white"><div className="mx-auto max-w-3xl px-4 py-3.5"><Logo /></div></header>
      <main className="mx-auto max-w-2xl px-4 py-8">
        {q.isLoading ? <Spinner /> : !r ? <Card><NotLoaded error={q.error} what="reference request" /></Card> : done || r.status === "responded" ? (
          <Card className="p-8 text-center">
            <LuCircleCheck className="mx-auto size-10 text-ok" aria-hidden />
            <h1 className="mt-3 text-xl font-semibold">Thank you</h1>
            <p className="mt-1 text-sm text-ink-2">Your answer has been recorded and shared with the recruiter.</p>
          </Card>
        ) : r.status !== "sent" ? (
          <Card className="p-8 text-center"><h1 className="text-lg font-semibold">This link is no longer active</h1><p className="mt-1 text-sm text-ink-2">It has {r.status}. Ask the recruiter for a new link.</p></Card>
        ) : (
          <Card className="p-6">
            <h1 className="text-xl font-semibold tracking-tight">Employment confirmation</h1>
            <p className="mt-1 text-sm text-ink-2">Hello {r.refereeName}. <b>{r.candidateName}</b> listed you as a reference. Please confirm what you know about their work at <b>{r.company || "your organisation"}</b>.</p>
            <div className="mt-4 rounded-lg bg-surface p-3.5 text-[13px] text-ink-2">
              The candidate says: <b>{r.claimedTitle || "role not given"}</b>{r.claimedStart && <>, from <b>{r.claimedStart}</b></>}{r.claimedEnd && <> to <b>{r.claimedEnd}</b></>}.
            </div>
            <form className="mt-5 grid gap-4 sm:grid-cols-2" noValidate onSubmit={form.handleSubmit((v) => void send.mutate(v))}>
              <fieldset className="sm:col-span-2">
                <legend className="mb-1.5 text-[13px] font-medium text-ink">Did this person work at {r.company || "your organisation"}? <span className="text-bad">*</span></legend>
                <div className="flex gap-4 text-sm">
                  {(["yes", "no"] as const).map((v) => (
                    <label key={v} className="flex items-center gap-2"><input type="radio" name="confirmed" className="size-4 accent-brand-600" checked={form.values.confirmed === v} onChange={() => form.setValue("confirmed", v)} /> {v === "yes" ? "Yes" : "No"}</label>
                  ))}
                </div>
                {form.errors.confirmed && <p className="mt-1 text-xs text-bad">{form.errors.confirmed}</p>}
              </fieldset>
              <Field label="Their job title" htmlFor="title" error={form.errors.title} className="sm:col-span-2"><input className={inputCls} {...form.register("title")} /></Field>
              <Field label="Start month" htmlFor="start" error={form.errors.start}><input type="month" className={inputCls} {...form.register("start")} /></Field>
              <Field label="End month" htmlFor="end" error={form.errors.end} hint="Leave empty if they still work there"><input type="month" className={inputCls} {...form.register("end")} /></Field>
              <Field label="Comments" htmlFor="comments" error={form.errors.comments} className="sm:col-span-2"><textarea rows={3} className={inputCls} {...form.register("comments")} /></Field>
              <Field label="Your name" htmlFor="responderName" error={form.errors.responderName} required><input className={inputCls} autoComplete="name" {...form.register("responderName")} /></Field>
              <Field label="Your role" htmlFor="responderRole" error={form.errors.responderRole}><input className={inputCls} {...form.register("responderRole")} /></Field>
              {send.error ? <div className="sm:col-span-2"><Notice tone="error" title="Answer not sent">{errorMessage(send.error)}</Notice></div> : null}
              <div className="flex justify-end sm:col-span-2"><Button type="submit" loading={send.isPending}>Send answer</Button></div>
            </form>
            <p className="mt-4 text-xs text-ink-3">This link works once. Your answer, name and the time are recorded and shown to the recruiter.</p>
          </Card>
        )}
      </main>
    </div>
  );
}
