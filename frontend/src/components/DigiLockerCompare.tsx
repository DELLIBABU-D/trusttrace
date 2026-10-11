import { LuCircleAlert, LuCircleCheck, LuCircleMinus, LuCircleX } from "react-icons/lu";
import type { DigiLockerComparison } from "../api/types";
import { formatDateTime } from "../lib/format";
import { Pill } from "./ui";

const STATUS: Record<string, { tone: "green" | "red" | "amber" | "gray" | "violet"; label: string }> = {
  match: { tone: "green", label: "Matches DigiLocker" },
  mismatch: { tone: "red", label: "Differs from DigiLocker" },
  partial: { tone: "amber", label: "Needs a person to compare" },
  no_upload: { tone: "gray", label: "No uploaded certificate" },
};

/** Field-by-field table: uploaded certificate vs the issuer's DigiLocker copy. Simulated records are always labelled. */
export function DigiLockerCompare({ c }: { c: DigiLockerComparison }) {
  const meta = STATUS[c.status];
  if (!meta) return null;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={c.simulated ? "violet" : meta.tone}>{c.simulated ? "SIMULATED – " : ""}{meta.label}</Pill>
        {!c.simulated && c.hmacVerified && <Pill tone="green">Download integrity verified</Pill>}
        <span className="text-xs text-ink-3">{c.title}{c.issuer ? ` · issued by ${c.issuer}` : ""}{c.fetchedAt ? ` · pulled ${formatDateTime(c.fetchedAt)}` : ""}</span>
      </div>
      {c.summary && <p className="mt-2 text-[13px] text-ink-2">{c.summary}</p>}
      {(c.rows?.length ?? 0) > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[420px] text-[13px]">
            <thead className="text-left text-xs text-ink-3">
              <tr><th className="py-1.5 font-medium">Field</th><th className="font-medium">Uploaded certificate</th><th className="font-medium">DigiLocker copy</th><th className="font-medium">Result</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {c.rows!.map((r) => (
                <tr key={r.field}>
                  <td className="py-2 text-ink-2">{r.field}</td>
                  <td className="text-ink">{r.uploaded ?? <span className="text-ink-3">not found</span>}</td>
                  <td className="text-ink">{r.digilocker ?? <span className="text-ink-3">not found</span>}</td>
                  <td>
                    {r.match === true ? <span className="inline-flex items-center gap-1 text-ok"><LuCircleCheck className="size-4" aria-hidden />Match</span>
                      : r.match === false ? <span className="inline-flex items-center gap-1 font-medium text-bad"><LuCircleX className="size-4" aria-hidden />Mismatch</span>
                        : <span className="inline-flex items-center gap-1 text-ink-3"><LuCircleMinus className="size-4" aria-hidden />Not compared</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {c.simulated && (
        <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-3"><LuCircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          This DigiLocker record is SIMULATED for testing. It is shown so the flow can be demonstrated, and it never counts as verification.</p>
      )}
    </div>
  );
}
