# StressChecker — Recente wijzigingen

## 2026-05-21

- /instellingen UX-fix — Pro-abonnement label nu taal-consistent (Jaarabonnement/Jahresabonnement/Annual subscription via plan-code mapping i.p.v. Stripe product.name). Licentiecode-label expliciet gemaakt met helptekst voor activatie op nieuw apparaat. NL/DE/EN visueel geverifieerd.
- Pro-tier widget op /pro + /instellingen voor alle Pro-cohorts (was Stripe-only). Toont tier (Pro S/M/L), actieve koppelingen vs. max_clients en geldigheid; afgeleid uit licenses + plans, Stripe-onafhankelijk.
- git init: /opt/stresschecker nu onder versie-controle (main-branch), .gitignore voor secrets/backups/db's/CONTEXT.md.
