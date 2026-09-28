# _env.sh — sourced by the automation scripts to put node and the claude CLI
# on PATH. Not executable on its own.
#
# cron and launchd start with a bare PATH (/usr/bin:/bin), so nothing the login
# shell set up is there. Nothing here is version-pinned: a hardcoded
# ~/.nvm/versions/node/vX.Y.Z breaks the first time nvm installs a newer node.
#
# Order: node already on PATH wins; then the newest nvm install; then the
# Homebrew (macOS) and ~/.local/bin dirs, appended so they never shadow nvm.

if ! command -v node >/dev/null 2>&1; then
  _nvm_bin="$(ls -d "${NVM_DIR:-$HOME/.nvm}"/versions/node/v*/bin 2>/dev/null | sort -V | tail -1 || true)"
  [[ -n "$_nvm_bin" ]] && PATH="$_nvm_bin:$PATH"
  unset _nvm_bin
fi

for _d in "$HOME/.local/bin" /opt/homebrew/bin /usr/local/bin; do
  [[ -d "$_d" ]] || continue
  case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac
done
unset _d
export PATH

NODE="$(command -v node || true)"
