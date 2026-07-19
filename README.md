[![Test workflow status](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/actions/workflows/python_test.yaml/badge.svg)](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/actions/workflows/python_test.yaml)
[![Lint workflow status](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/actions/workflows/python_lint.yaml/badge.svg)](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/actions/workflows/python_lint.yaml)
[![Docs workflow status](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/actions/workflows/docs.yaml/badge.svg)](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/actions/workflows/docs.yaml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# GEMINI Geothermal Suite (Open Source)

Open-source repository for the GEMINI Geothermal Digital Twin platform, developed in the
context of the *Nieuwe Warmte Nu* innovation program.

## Documentation

Public documentation is built from `src/gemini_documentation` and published via GitHub Pages.

- Main branch docs:  
  <https://gemini-digital-twin.github.io/gemini-geothermal-suite-open/main/>
- Branch docs (pattern):  
  `https://gemini-digital-twin.github.io/gemini-geothermal-suite-open/<branch-name>/`

> Branch names are sanitized for deployment (`/` is replaced with `-`).

## Quick start

### Prerequisites

- Python 3.11
- Poetry
- Docker + Docker Compose (for containerized services)

### Local development setup

```bash
python -m pip install --upgrade pip
pip install poetry
poetry lock
poetry install
```

### Run checks locally

```bash
poetry run flake8 src unit_test --count --show-source --max-line-length=100 --statistics
poetry run black --check --diff src unit_test
poetry run pytest -v --cov -p no:faulthandler
```

## Repository structure

- `src/gemini_framework` - framework/runtime logic
- `src/gemini_model` - domain and physics models
- `src/gemini_application` - application-level features
- `src/gemini_interface` - interface components
- `src/gemini_documentation` - Sphinx docs source and build output
- `ci/linux` - CI helper scripts used by GitHub Actions

## CI and branch documentation workflow

- **Test** workflow: `.github/workflows/python_test.yaml`
- **Lint** workflow: `.github/workflows/python_lint.yaml`
- **Docs** workflow: `.github/workflows/docs.yaml`

On every push, the Docs workflow builds Sphinx docs and deploys to `gh-pages` under a
branch-specific folder, enabling side-by-side docs per branch.

## Versioning and release notes

- Versioning policy: [VERSIONING.md](./VERSIONING.md)
- Release notes / change history: [CHANGELOG.md](./CHANGELOG.md)

## Contribution

Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a pull request.

For bugs, feature requests, and technical discussions, open an
[issue](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/issues).

## License

This content is released under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0) License.


## Acknowledgments
This project is sponsored by NWM innovatie: Datagedreven optimalisatie aardwarmtesystemen
(https://nwn.nu/projecten/innovaties/datagedreven-optimalisatie-aardwarmte-systemen)

Organization: TNO, Gaia Energy, HVC, Well Engineering Partners (WEP), Helin