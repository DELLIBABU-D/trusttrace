/**
 * Form state + Zod validation (React Hook Form style: register, errors, handleSubmit).
 * Errors appear after a field is touched or after the first submit attempt.
 */
import { useState, type ChangeEvent, type FormEvent } from "react";
import type { ZodType, ZodTypeDef } from "zod";

type Values = Record<string, unknown>;
type Errors<T> = Partial<Record<keyof T & string, string>>;

export function useZodForm<T extends Values>(schema: ZodType<T, ZodTypeDef, unknown>, defaults: T) {
  const [values, setValues] = useState<T>(defaults);
  const [touched, setTouched] = useState<Partial<Record<keyof T & string, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);

  const validate = (v: T): Errors<T> => {
    const r = schema.safeParse(v);
    if (r.success) return {};
    const out: Errors<T> = {};
    for (const issue of r.error.issues) {
      const k = String(issue.path[0] ?? "") as keyof T & string;
      if (k && !out[k]) out[k] = issue.message;
    }
    return out;
  };
  const allErrors = validate(values);
  const errors: Errors<T> = {};
  for (const k of Object.keys(allErrors) as (keyof T & string)[]) {
    if (submitted || touched[k]) errors[k] = allErrors[k];
  }

  const setValue = <K extends keyof T & string>(name: K, value: T[K]) => setValues((v) => ({ ...v, [name]: value }));

  /** Spread onto <input>, <select> or <textarea>. */
  const register = <K extends keyof T & string>(name: K) => ({
    name,
    id: name,
    value: (values[name] ?? "") as string,
    "aria-invalid": errors[name] ? true : undefined,
    "aria-describedby": errors[name] ? `${name}-error` : undefined,
    onChange: (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      const t = e.target as HTMLInputElement;
      setValue(name, (t.type === "checkbox" ? t.checked : t.value) as T[K]);
    },
    onBlur: () => setTouched((s) => ({ ...s, [name]: true })),
  });

  const checkbox = <K extends keyof T & string>(name: K) => ({
    name,
    id: name,
    type: "checkbox" as const,
    checked: Boolean(values[name]),
    onChange: (e: ChangeEvent<HTMLInputElement>) => {
      setValue(name, e.target.checked as T[K]);
      setTouched((s) => ({ ...s, [name]: true }));
    },
  });

  const handleSubmit = (onValid: (v: T) => void | Promise<void>) => (e?: FormEvent) => {
    e?.preventDefault();
    setSubmitted(true);
    const parsed = schema.safeParse(values);
    if (parsed.success) void onValid(parsed.data);
    else {
      const first = String(parsed.error.issues[0]?.path[0] ?? "");
      document.getElementById(first)?.focus();
    }
  };

  /** Validate only some fields (multi-step forms). */
  const validateFields = (names: (keyof T & string)[]) => {
    const t: Partial<Record<keyof T & string, boolean>> = { ...touched };
    names.forEach((n) => (t[n] = true));
    setTouched(t);
    return names.every((n) => !allErrors[n]);
  };

  return { values, setValue, setValues, errors, register, checkbox, handleSubmit, validateFields, isValid: Object.keys(allErrors).length === 0, reset: () => (setValues(defaults), setTouched({}), setSubmitted(false)) };
}
