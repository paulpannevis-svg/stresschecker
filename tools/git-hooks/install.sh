#!/bin/bash
# Installeert de versiebeheerde git-hooks als dunne shims in .git/hooks/.
# Idempotent: opnieuw draaien overschrijft de shim. Draai vanuit de repo-root of waar dan ook.
set -eu
REPO=/opt/stresschecker
HOOK="$REPO/.git/hooks/pre-commit"
cat > "$HOOK" <<'SHIM'
#!/bin/bash
# Shim -> versiebeheerde hook. Bewerk tools/git-hooks/pre-commit, niet dit bestand.
exec /opt/stresschecker/tools/git-hooks/pre-commit "$@"
SHIM
chmod +x "$HOOK"
echo "pre-commit hook geïnstalleerd -> $HOOK (shim naar tools/git-hooks/pre-commit)"
