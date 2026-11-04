# Task: Keep only branch `refactor` (with all work in it) and delete every other branch

Losing work is the one thing that must not happen. If any check fails, **stop, change nothing
more, and report**. No force push anywhere, no `git branch -D`, no history rewrite.

1. **Nothing uncommitted:** `git status`. Commit all uncommitted/untracked work that belongs in
   the repo on the current branch. If `git stash list` is not empty, stop and report.
2. **Backup first:** `git fetch --all --prune`. For every local branch and every remote branch,
   create a tag `backup/<branch-name-with-/-replaced-by-->-2026-10-28` at its tip and push them
   (`git push origin --tags`). These tags stay; they are the undo.
3. **Find the tip that contains all work:** among all local and remote branches except `main`,
   find the one whose history contains every other one
   (`git merge-base --is-ancestor <other> <candidate>`). If none contains all:
   - if the missing commits are only on `origin/refactor` or one other branch, merge them into
     the candidate with a normal merge (`git merge --no-ff`), resolve conflicts only if trivial,
     run the tests;
   - otherwise stop and report what is missing where.
4. **Create `refactor` locally at that tip.** Note: git cannot have `refactor` and
   `refactor/...` branches at the same time. So: `git switch --detach <tip>`; verify again that
   every local `refactor/*` branch is an ancestor of `HEAD`; delete those with `git branch -d`;
   then `git switch -c refactor` (or move an existing local `refactor` only if it is an ancestor
   of the tip: `git branch -f` is allowed only in that case).
5. **Push:** `origin/refactor` must be an ancestor of local `refactor` (otherwise go back to step
   3 and merge it in). `git push -u origin refactor`. Verify
   `git rev-parse refactor` == `git rev-parse origin/refactor`.
6. **Delete the rest:** for every other local and remote branch except `main` and `refactor`,
   check `git merge-base --is-ancestor <branch> refactor`; delete only those that pass
   (`git branch -d <b>`, `git push origin --delete <b>`). Any branch that fails is kept and
   reported with `git log refactor..<branch> --oneline`. Never delete `main`, `refactor` or the
   backup tags.
7. `git fetch --prune`; show `git branch -a` and `git tag -l "backup/*"`. Run the default test
   profile (or the default `pytest` if profiles do not exist yet) on `refactor`; it must pass.
8. In `AGENTS.md` add/update a "Branching" section: all work happens directly on `refactor`; no
   new branches unless the user asks. Commit and push on `refactor`.

Report: which commit `refactor` now points to and which branch it came from, merges done (if
any), backup tags, deleted branches, branches kept and why, final `git branch -a`, test summary.
