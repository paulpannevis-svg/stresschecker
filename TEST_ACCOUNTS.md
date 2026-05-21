# Test-accounts (levende fixtures op productie-DB)

**Beleid: NIET opruimen tenzij expliciet zo gemarkeerd in deze tabel.**

Reden voor levende test-fixtures op productie: er is geen staging-omgeving. Deze accounts zijn het enige referentiepunt voor handmatige regressie-checks van auth-, activatie-, tier-widget- en license-flows.

Productie-accounts (echte klanten) zijn duidelijk gescheiden — geen `+`-aliassen in het e-mailadres.

## Actieve test-accounts

| Account | License key | Soort | Aangemaakt | Gebruik |
|---|---|---|---|---|
| `paulpannevis+mueh-test@gmail.com` | `SC-PRO-AC3FD3AB` | Marketing-Pro (sc-pro-m, year, origin=marketing) | 2026-05-21 | Marketing-flow + tier-widget UX-verificatie (Licentiecode-label, Jaarabonnement-label). Eerste echte gebruik van marketing-pad post-reset. |
| `paulpannevis+evaltest@gmail.com` | `SC-PRO-F4751519` | Eval-Pro (sc-pro-m-eval, eval, origin=evaluation) | 2026-05-21 | Eval-flow eerste end-to-end test (90-dagen looptijd, Evaluatielicentie-label, geen Stripe-blok). Vervalt op 2026-08-19 → bonus expiry-UI-test op die datum. |

## Productie-accounts (NIET aanraken in test-context)

| Account | License key | Soort |
|---|---|---|
| `paulpannevis@lifestylemonitors.com` | `SC-PRO-D6405215` | Stripe-webshop Pro M (canceled subscription, niet meer billing maar nog wel actief tot expires_at) |
| `paulpannevis@lifestylemonitors.com` | `SC-PRO-20503ED0` | Manual-Pro (origin=manual) |
| `paulpannevis@gmail.com` | — | Operator-account |

## Onderhoud

- Verlopen test-fixture? Verleng `expires_at` of vervang met nieuw account; oude rij behouden voor audit-trail.
- Nieuwe test-fixture toevoegen? Update deze tabel **en** CHANGELOG.md regel met "Test-fixture toegevoegd: …".
- Per ongeluk opgeruimd? Re-creëer via `/opt/ic-license-server/generate_eval_license.py` (eval) of via marketing-code reset (zie eerdere sessie van 2026-05-21).
