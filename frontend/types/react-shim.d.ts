/**
 * Sandbox-only type shim. @types/react could not be installed in the build sandbox (no npm registry access),
 * so this declares the React surface the app uses. JSX element props are loosely typed here; everything
 * else (API types, hooks, forms, schemas, component props) is fully checked. With `npm install` the real
 * @types/react is used instead and this folder is excluded (see tsconfig.json).
 */
declare module "react" {
  export type ReactNode = any;
  export type Key = string | number;
  export type ComponentType<P = {}> = (props: P) => ReactNode;
  export type SetStateAction<S> = S | ((prev: S) => S);
  export function useState<S>(initial: S | (() => S)): [S, (v: SetStateAction<S>) => void];
  export function useState<S = undefined>(): [S | undefined, (v: SetStateAction<S | undefined>) => void];
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useRef<T>(initial: T): { current: T };
  export function useRef<T>(initial: T | null): { current: T | null };
  export function useCallback<T extends (...args: any[]) => any>(fn: T, deps: readonly unknown[]): T;
  export function useMemo<T>(fn: () => T, deps: readonly unknown[]): T;
  export function useId(): string;
  export interface Context<T> { Provider: ComponentType<{ value: T; children?: ReactNode }> }
  export function createContext<T>(defaultValue: T): Context<T>;
  export function useContext<T>(ctx: Context<T>): T;
  export const StrictMode: ComponentType<{ children?: ReactNode }>;
  export interface SyntheticEvent<T = Element> { target: EventTarget & T; currentTarget: EventTarget & T; preventDefault(): void; stopPropagation(): void }
  export interface ChangeEvent<T = Element> extends SyntheticEvent<T> {}
  export interface FormEvent<T = Element> extends SyntheticEvent<T> {}
  export interface MouseEvent<T = Element> extends SyntheticEvent<T> { button: number; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean; defaultPrevented: boolean }
  export interface HTMLAttributes<T> { className?: string; id?: string; role?: string; children?: ReactNode; onClick?: (e: MouseEvent<T>) => void; [aria: `aria-${string}`]: unknown }
  export interface AnchorHTMLAttributes<T> extends HTMLAttributes<T> { href?: string; target?: string; rel?: string }
  export interface SVGAttributes<T> extends HTMLAttributes<T> { [attr: string]: unknown }
  export type ReactElement = any;
  export namespace JSX { type Element = any }
  export interface ButtonHTMLAttributes<T> extends HTMLAttributes<T> { type?: "button" | "submit" | "reset"; disabled?: boolean; form?: string; title?: string }
}
declare module "react/jsx-runtime" {
  export const jsx: any, jsxs: any, Fragment: any;
}
declare module "react-dom/client" {
  export function createRoot(el: Element): { render(node: unknown): void };
}
declare namespace JSX {
  type Element = any;
  interface IntrinsicElements { [tag: string]: any }
  interface IntrinsicAttributes { key?: string | number }
}
