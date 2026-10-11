/**
 * Phase switches.
 * PREVIEW_MODE (Phase 1): role-protected screens can be opened without signing in, with a banner saying so.
 * Phase 2 sets this to false; RequireRole then sends anonymous users to /login and wrong roles to their own home.
 */
export const PREVIEW_MODE = false;

export const APP_NAME = "TrustTrace";
export const BASE_TRUST_SCORE = 80;
