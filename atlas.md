# Atlas — EnterpriseCore AI Suite

The authoritative source of truth for the business. All other skills (Anchor, Northstar, Echo, Canvas, Keynote, Greenlight, Redline) read from this file. Update it whenever a stable fact changes.

---

## What this is

**EnterpriseCore AI Suite** — a single offline-first desktop app that replaces 15+ SaaS subscriptions for a small-to-mid business. Two pillars in one install:

1. **Enterprise Business Suite** — Finance, HR, CRM, Projects, Inventory, Documents, Communication, Security. 90+ tools.
2. **AI Coding Assistant** — Monaco IDE + AI chat (Claude / OpenAI / local Ollama). 15 tools, all functional.

One-time payment. Data never leaves the building. Works without internet.

## Target customer

**Primary:** Privacy-conscious small-to-mid businesses (10–250 people) currently paying $500–$5,000/month for fragmented SaaS — and one of these applies:
- Operates in a regulated industry (healthcare, legal, finance, gov contractors)
- Operates in environments with poor/no internet (manufacturing floors, ships, field sites, developing markets)
- Has been burned by a SaaS price hike, outage, or data breach
- Has data-sovereignty rules (EU AI Act, HIPAA, SOC2, on-prem mandates)

**Secondary:** Developers and small dev shops who want a local-first AI coding assistant they own outright (no monthly Cursor/Copilot bill, no code leaving their machine).

## Positioning (one sentence)

> EnterpriseCore replaces your SaaS stack with one offline install — your business runs on your hardware, with AI built in, for a one-time payment.

## Why now

- 2026 SaaS sprawl: avg company runs 130+ SaaS apps. Cost + risk are at all-time highs.
- AI subscriptions stacking on top of existing SaaS (Cursor, Copilot, Claude, etc.).
- Data sovereignty regulations tightening (EU AI Act enforcement phase, US state-level privacy laws).
- Ollama + local LLMs reached the quality threshold where "offline AI" actually works.

## Stack (technical facts)

- Frontend: React 18 + TypeScript + Vite + Tailwind
- Backend: FastAPI (Python 3.11+) + SQLAlchemy 2.x
- DB: SQLite default; Postgres for multi-user
- Desktop: Electron + electron-builder
- Installer: NSIS (.exe), Inno Setup alt
- AI: Anthropic API + OpenAI API + Ollama (local)
- Auth: JWT (HS256) + bcrypt
- Credentials: OS vault via Electron safeStorage (Windows DPAPI / macOS Keychain / libsecret)

## Differentiators

1. **Offline-first.** Not "offline-capable" — designed offline. Ollama fallback means AI works without an API key.
2. **One payment.** Not subscription. Not freemium. Buy once, run forever.
3. **BYO keys.** API keys go in OS credential vault, never persist server-side, never leave the device unencrypted.
4. **All-in-one.** Most "all-in-one" platforms cover 3–5 tool categories. EnterpriseCore covers 8 (Finance/HR/CRM/Projects/Inventory/Documents/Communication/Security) plus an AI IDE.

## Pricing (proposed — needs validation)

| Tier | Price | Audience | Includes |
|---|---|---|---|
| **Solo / Indie** | $497 one-time | 1 user | Full suite, 1-year updates, community support |
| **Team** | $1,997 one-time | up to 10 users | Full suite, 2-year updates, email support |
| **Business** | $4,997 one-time | up to 50 users | Full suite, lifetime updates, priority support, multi-tenant Postgres |
| **Enterprise** | Custom | 50+ users | On-prem deploy, white-label, SLA |

Note: not yet validated against actual willingness-to-pay. First 10 sales should be Tier 1/2 to learn.

## What's shipped vs not shipped

**Status as of 2026-05-20:** Codebase appears mature based on README. Unknown to Atlas: whether installer ships, whether there are paying customers, whether the AI Coding Assistant's 15 tools are all production-quality. Update this section after the user confirms.

## Next 30 days — proposed milestones

1. **Week 1:** Validate installer builds end-to-end on a clean Windows VM. Record a 90-second demo video.
2. **Week 2:** Ship landing page + waitlist form to 1 domain. Drive 100 visits from 3 channels (HN Show, IndieHackers, r/selfhosted).
3. **Week 3:** Convert 10 waitlist signups into 10 30-min demo calls. Listen, do not pitch.
4. **Week 4:** Close 1 paying customer at Tier 1 or 2 pricing.

If Week 4 misses, the problem is positioning (Atlas) or product readiness — not marketing.

---

*Edit this file directly. Skills that depend on Atlas will re-read on each invocation.*
