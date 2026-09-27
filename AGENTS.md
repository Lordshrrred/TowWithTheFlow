# TowWithTheFlow — Agent Instructions

Shared by every agent (Claude Code, Codex, others). `CLAUDE.md` imports this file.

## Start of every session

**First, get the latest code.** Matt works on this repo from more than one machine, so every session starts with `git pull --ff-only`. Claude Code does this automatically (SessionStart hook → `.claude/hooks/git-sync.sh`; look for its `git sync:` line). Every other agent runs it by hand before reading or editing anything. If the pull is refused because of uncommitted changes, local commits, or a diverged branch, stop and tell Matt. Never stash, reset, or discard work to make a pull succeed. Before ending, commit and push finished work so the next machine picks it up.
