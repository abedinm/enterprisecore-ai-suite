# Translations needing native-speaker review

The current 11-locale catalog was bootstrapped to working completeness with
machine-quality translations. Every locale has 100% coverage of the keys
listed in `en.json`, but the following entries are flagged for a native
speaker pass before shipping to paying customers in that market.

## Status by locale

| Locale | Coverage | Confidence | Notes |
| ------ | -------- | ---------- | ----- |
| `en` | 100% | Source | — |
| `es` | 100% | High      | LatAm vs Iberian variants not split — single neutral catalog. |
| `fr` | 100% | High      | Neutral French; Quebec users may want `Tableau de bord` → `Tableau` etc. |
| `de` | 100% | High      | Formal "Sie" form throughout. |
| `pt` | 100% | High      | Neutral BR/PT — no separate pt-PT split yet. |
| `it` | 100% | High      | Informal "tu" — Italian formal "Lei" not used. |
| `ja` | 100% | Medium    | Mixed politeness levels. Module names kept in kanji where common. |
| `zh` | 100% | Medium    | Simplified Chinese only. Traditional (`zh-TW`) variant not yet provided. |
| `ar` | 100% | Medium    | Modern Standard Arabic. Dialectal terms (esp. for SaaS jargon) need review. |
| `he` | 100% | Medium    | Geresh/gershayim used (e.g. דוא״ל). Check with native speaker. |
| `ur` | 100% | Medium    | Loanwords kept in English where standard usage prefers them. |

## Specific strings to double-check

- `auth.magicLink` ("Email a link") — direct translation is awkward in
  most languages; consider customising per-market.
- `nav.coding` ("AI Coding") — Japanese/Chinese versions use a literal
  rendering; native devs may prefer keeping it in English.
- `module.crm` — kept as the acronym "CRM" in every locale; if a market
  prefers a translated equivalent, override here.
- Module names in CJK locales — short kanji/hanzi often loses nuance.

## Adding new keys

1. Add the key + English string to `locales/en.json`.
2. Run `node src/i18n/extract.mjs --write` from `frontend/` — this stubs
   the new key into every other locale using the English text.
3. Hand-translate the stubbed entries before release.
