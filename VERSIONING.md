# Versioning and Release Notes Policy

This repository uses **Semantic Versioning (SemVer)** and **Keep a Changelog**.

## Versioning scheme

Version format: `MAJOR.MINOR.PATCH`

- **MAJOR**: incompatible API or behavior changes.
- **MINOR**: backward-compatible feature additions.
- **PATCH**: backward-compatible bug fixes and small improvements.

While the version is below 1.0, a breaking change to a public name or return field raises MINOR
(`0.3.0`) and an addition or a fix raises PATCH (`0.1.1`).

The version has one source: `version` in the `[project]` section of `pyproject.toml`.
`gm.__version__` reads it, and the public-API snapshot, checkpoints and saved results record it.

## Release notes source of truth

- Release notes are maintained in [`CHANGELOG.md`](./CHANGELOG.md).
- New work is recorded under `## [Unreleased]`.
- At release time, move relevant items from `Unreleased` to a new version section.

## Recommended release process

1. Ensure `CHANGELOG.md` (`Unreleased`) is up to date.
2. Choose next SemVer number (`MAJOR.MINOR.PATCH`).
3. Update the version in `pyproject.toml`.
4. Create a new section in `CHANGELOG.md`:
   - `## [X.Y.Z] - YYYY-MM-DD`
5. Commit the version/changelog changes and merge them into `dev`.

The `Release` workflow does the rest when a version without a tag reaches `dev`: it runs the whole
fast suite on every supported Python, builds the wheel and the source archive, pushes the sandbox
image to `ghcr.io`, and creates the tag `vX.Y.Z` and its GitHub Release from the changelog entry. A
push that keeps the version publishes nothing. A published version never changes: a fix gets a new
version. If the workflow fails, nothing is tagged, and it can be run again by hand.

## Installing a published version

GitHub Packages has no Python registry, so a project installs the wheel of a release:

```
pip install https://github.com/geomind-spe-geohackathon-2026/gemini/releases/download/vX.Y.Z/gemini_geothermal_suite_open-X.Y.Z-py3-none-any.whl
```

An application pins this exact version. The sandbox image of the same version is
`ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox:X.Y.Z`. An editable install from a checkout
is for trying a change locally and is not committed.

## Changelog categories

Use these headings when relevant:

- `Added`
- `Changed`
- `Deprecated`
- `Removed`
- `Fixed`
- `Security`

