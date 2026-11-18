# ConsumerAssist — Review Readiness Report (2026-11-19)

## A. Overall health
Before this audit, the app looked complete but had three serious hidden problems:
1. **Gemini never ran.** It was hardcoded to the retired `gemini-1.5-flash` model (HTTP 404), and OpenAI was tried first anyway.
2. **There was no backend authentication.** Anyone could call `GET /api/cases/` and get every case. Confirmed on production: 3 cases were returned without logging in.
3. **"Google login" accepted any email address**, and two fake demo accounts were built into the page.

All three are fixed and tested **locally**. **None of the fixes are deployed yet** (see G).

## B. Module audit
| Module | Initial | Changes | Final (local) |
|---|---|---|---|
| Gemini API | Broken (retired model, deprecated SDK, OpenAI used first) | REST client, `gemini-flash-lite-latest` with `gemini-flash-latest` as backup on 404/429/5xx, key sent in a header, Gemini tried first | ✅ Live responses verified |
| Chatbot / DST | Corrections ignored; regex overwrote LLM slots (₹5,000 could replace ₹1,995); "what…" messages skipped extraction; "skip" advanced from any stage | LLM output validated before it touches state; corrections override; regex is offline fallback only; stage gate; date/missing slots/legal facts injected into prompt | ✅ 10-turn live scenario correct |
| NLP | OK | none | ✅ existing tests pass |
| Auth | Fake (localStorage, any email) | Supabase token verified server-side (`backend/app/auth.py`); demo/any-email login removed | ✅ code; ⚠ OAuth not clicked through |
| User isolation | None (IDOR on every route) | Every case/chat/document route checks ownership (404 if not the owner); list is scoped by the token; the user ID in the request body is ignored | ✅ tested |
| Supabase DB | Local `.env` uses SQLite; Postgres driver mismatch (forces psycopg2, but requirements install psycopg v3) caused a silent fallback to temporary SQLite | Driver auto-detected; fallback logged as an ERROR; `/api/health` reports the DB backend | ⚠ Not verified: no reachable Postgres URL |
| Evidence upload | No type/size checks | Allowed types limited to pdf/png/jpg/webp/txt/mp4/mov; max 10 MB; empty files rejected | ✅ tested |
| Readiness / COD | `"cod"` matched inside "promo **code**" and waived evidence | Word-boundary matching | ✅ tested |
| Legal drafts | Tier 1 claimed a "15 days as mandated" deadline (wrong); missing values printed as "N/A" | Now cites Rule 4(5): acknowledge within 48 h, redress within 1 month; missing values show `[NOT PROVIDED]` | ✅ |
| Timeline / Escalation / NCH / e-Jagriti | Not changed | — | Existing tests pass; not audited in depth |

## D. Gemini results
- Local: key loaded server-side (never printed); live replies took 1–9 s. `gemini-flash-latest` frequently returns 503 (overloaded), so the lite model is the default.
- Fallback chain: Gemini → OpenAI (local key currently returns a quota/rate-limit error) → local rules engine. Tests cover 429, timeout and malformed JSON.
- Production: **not tested.** After deploying, open `/api/health` and confirm `gemini_configured: true`.

## E. Auth / DB
- Dummy accounts: "Rahul Verma" and "Ananya Sharma" existed only in frontend code (not Supabase Auth users) and are now removed. The local SQLite file has 2 cases under `google_umugash07_gmail_com`, a fake ID from the old any-email form. They were left untouched, but they will no longer show for any real login.
- RLS: the backend connects as the DB owner, so isolation is enforced in the API. You still need to enable RLS (SQL below) so the public anon key cannot read these tables through Supabase's REST API.

## F. Tests (actually run)
| Category | Passed | Failed | Not tested |
|---|---:|---:|---:|
| Backend pytest (8 existing + 7 new) | 15 | 0 | — |
| Frontend `tsc` + `vite build` | 2 | 0 | no unit tests exist |
| Live Gemini dialogue scenarios | 10 | 0 | — |
| Google OAuth click-through, Supabase Postgres, production | — | — | all |

## G. Remaining issues
**CRITICAL**
1. Deploy. Production still runs the old, open API.
2. Vercel → Project → Settings → Environment Variables (Production), then redeploy:
   - `GEMINI_API_KEY`
   - `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (the backend also reads these to verify logins)
   - `DATABASE_URL`: use the Supabase **Session pooler** URI (Dashboard → Connect). The direct `db.<ref>.supabase.co` host is IPv6-only and timed out from this machine.
3. Supabase → Authentication → URL Configuration: Site URL `https://consumer-assist.vercel.app`; Redirect URLs `https://consumer-assist.vercel.app/**` and `http://localhost:5173/**`.
4. Google Cloud → OAuth client: Authorized redirect URI `https://szwofyjmkhpljlcilljs.supabase.co/auth/v1/callback`.

**HIGH**
- Run this in the Supabase SQL editor:

  ```sql
  alter table cases enable row level security; alter table dialogue_turns enable row level security;
  alter table extracted_entities enable row level security; alter table timeline_events enable row level security;
  alter table evidence_documents enable row level security; alter table escalation_history enable row level security;
  alter table generated_drafts enable row level security;
  ```

- Uploaded files on Vercel go to `/tmp` and are lost on cold start. Only the metadata and OCR text persist, in the DB.

**MEDIUM**: `google.generativeai` is still used for vision OCR (deprecated); unused demo CSS is left over; the OpenAI key is out of quota.

## Manual demo checklist
1. Open `/api/health` and check `database: postgresql`, `gemini_configured: true`, `auth_configured: true`.
2. Sign in with Google, refresh the page, and confirm you are still signed in. Sign out.
3. Run the Zepto gift-card scenario. Check: platform Zepto, amount ₹1,995, a correction is applied, "why do you need X?" does not change the stage.
4. Upload an invoice, say "paid by cash on delivery", and check that readiness rises.
5. Generate the Tier 1 notice and check it cites Rule 4(5) with no invented facts.
6. Sign in from a second Google account and confirm the first account's cases are not visible.
