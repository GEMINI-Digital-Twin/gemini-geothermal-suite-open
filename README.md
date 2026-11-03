# GEMINI geothermal suite

Composable geothermal equipment, plants built from data, in-memory data, and one finite engine for
simulation, historical replay, and externally scheduled live updates.

## Install

gemini runs on Python 3.11 to 3.14. Install the wheel of a release, with the version you want:

```bash
pip install https://github.com/geomind-spe-geohackathon-2026/gemini/releases/download/vX.Y.Z/gemini_geothermal_suite_open-X.Y.Z-py3-none-any.whl
```

## Test

From a clone of the repository:

```bash
uv pip install . --group dev
make test           # the tests of what changed and of what imports it
make test-release   # every tier on the full-year dataset
make lint           # flake8, black and isort
```

## Documents

- [Guide](docs/guide.md): a tour of the package.
- [Rules](docs/rules.md): every rule of the project.
- [Changelog](docs/CHANGELOG.md): what changed in each version.
