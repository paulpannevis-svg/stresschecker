# Password-reset feature - 12 mei 2026

Scope (akkoord 1-5):
1. 6-cijferige code in mail (niet token-in-URL)
2. Hash-migratie SHA-256 -> bcrypt (transparant bij login)
3. Alleen NL/DE/EN
4. Geen test1/test2 recovery in deze sprint
5. Geen 2FA-log-fix in deze sprint

Architectuur:
- Nieuwe tabel password_reset_codes in saas_licenses.db (gecorrigeerd 12-05-2026: oorspronkelijk genoteerd als ic_licenses.db, maar de actieve users-tabel met data staat in saas_licenses.db; password_reset_codes is daar bijgemaakt om cross-DB lookups te vermijden)
- Nieuwe route GET/POST /wachtwoord-vergeten
- Nieuwe route GET/POST /wachtwoord-reset
- Nieuwe helpers hash_password() / verify_password() (bcrypt + SHA-256 fallback)
- Nieuwe helper send_password_reset_email() via SendGrid
- Bestaande login-handler aanpassen: SHA-256 match -> re-hash naar bcrypt (alleen /login-pad; /activeer en /api/license/migrate blijven SHA-256 schrijven en migreren transparant bij eerstvolgende login)

DB-schema:
CREATE TABLE password_reset_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL,
  code TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE INDEX idx_prc_email_code ON password_reset_codes(email, code);
CREATE INDEX idx_prc_expires ON password_reset_codes(expires_at);

Security-notes:
- Reset-code 10 min geldig
- Eenmalig gebruik (used_at timestamp)
- Rate-limiting 3 per uur per e-mailadres
- Geen email-enumeration (altijd dezelfde response)

Sidecar: /opt/stresschecker/app.py.bak_pwreset_20260512T140444
