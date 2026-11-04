# Task: Put all work on one branch `dev` and remove the other branches — without losing anything

Losing work is the one thing that must not happen. If any check below fails, **stop, change
nothing more, and report**.

1. **Nothing uncommitted:** `git status`. Commit all uncommitted and untracked work that belongs
   in the repo on the current branch. Check `git stash list`; if there are stashes, stop and
   report them (do not drop them).
2. **Backup first:** `git fetch --all --prune`. For every local and remote branch, create a tag
   `backup/<branch-name>-2026-10-28` at its tip and push all backup tags
   (`git push origin --tags`). These tags stay; they are the undo.
3. **Pick the branch that contains everything:** find the branch whose history contains every
   other branch except `main`
   (`git merge-base --is-ancestor <other> <candidate>` for all). If no single branch contains all
   of them, stop and report which commits are missing from each candidate.
4. Check out that branch, rename it to `dev` (`git branch -m dev`), `git push -u origin dev`.
   Verify `git rev-parse dev` == `git rev-parse origin/dev`.
5. **Verify again before deleting:** for each other branch (local and remote, except `main`
   and `dev`), `git merge-base --is-ancestor <branch> dev` must succeed. Any branch that fails is
   kept and reported with its unique commits (`git log dev..<branch> --oneline`).
6. Delete only the verified branches: `git branch -d <b>` (never `-D`),
   `git push origin --delete <b>`. Never delete `main`, `dev` or the backup tags. No force push
   anywhere.
7. `git fetch --prune`; show `git branch -a` and `git tag -l "backup/*"`. Run `pytest` on `dev`
   and confirm it is green.
8. From now on all work happens on `dev`, no new branches unless asked. Add a "Branching"
   section to `AGENTS.md` saying so; commit and push on `dev`.

Report: which branch became `dev` and why, backup tags created, deleted branches, any branch
kept and why, final `git branch -a`, `pytest` summary line.
