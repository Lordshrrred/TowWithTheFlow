#!/usr/bin/env bash
# Runs at the start of every Claude Code session (see .claude/settings.json).
# Brings this checkout up to date with GitHub so work always starts from the
# newest code, whichever machine it's on. Only fast-forwards a clean checkout;
# it never touches uncommitted changes or local commits.

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
export GIT_TERMINAL_PROMPT=0

branch=$(git branch --show-current)
if ! git fetch -q origin 2>/dev/null; then
  echo "⚠ git sync: couldn't reach GitHub (offline?). This checkout may be stale — run 'git pull --ff-only' before editing."
  exit 0
fi

if ! git rev-parse -q --verify '@{u}' >/dev/null 2>&1; then
  echo "⚠ git sync: branch '$branch' has no GitHub upstream, so nothing was pulled."
  exit 0
fi

set -- $(git rev-list --left-right --count 'HEAD...@{u}')
ahead=$1 behind=$2
dirty=$(git status --porcelain | wc -l | tr -d ' ')

if [ "$dirty" -gt 0 ]; then
  echo "⚠ git sync: NOT pulled — $dirty uncommitted change(s) on '$branch' (GitHub is $behind commit(s) ahead). Tell Matt before editing; never stash, reset, or discard this work."
elif [ "$ahead" -gt 0 ] && [ "$behind" -gt 0 ]; then
  echo "⚠ git sync: NOT pulled — '$branch' has diverged ($ahead local, $behind on GitHub). Tell Matt and agree on a merge before editing."
elif [ "$ahead" -gt 0 ]; then
  echo "⚠ git sync: '$branch' has $ahead local commit(s) not on GitHub yet. Push them (git push) so other machines get them."
elif [ "$behind" -gt 0 ]; then
  if git pull -q --ff-only; then
    echo "✓ git sync: pulled $behind new commit(s) from GitHub — '$branch' is up to date."
  else
    echo "⚠ git sync: pull failed on '$branch'. Run 'git pull --ff-only' and check the error before editing."
  fi
else
  echo "✓ git sync: '$branch' is up to date with GitHub."
fi
exit 0
