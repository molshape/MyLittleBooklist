# Contributing to My Little Booklist

Thanks for your interest in **My Little Booklist**! Contributions are welcome – please read this short note first.

## Keeping it simple

**My Little Booklist** is intentionally small and simple: a few plain Python modules, SQLite, server-rendered templates and no JavaScript framework. It should stay easy to run and simple to understand. New features are weighed against that – a smaller change that covers most of the need is usually preferred over a complete one that adds a lot of code or new dependencies.

## Welcome contributions

- **Bug reports** – please include steps to reproduce and what you expected.
- **Fixes and corrections** – code, texts, typos, documentation.
- **Small improvements** – usability, accessibility, performance.
- **New languages** – see below.

For larger changes or new features, please open an issue first so we can discuss whether and how it fits.

## Adding a language

Follow the steps in the [Translating](README.md#translating) section of the [README.md](README.md):
1. create the catalog with `pybabel init`
2. translate `src/mylittlebooklist/translations/<lang>/LC_MESSAGES/messages.po` using [`messages.pot`](src/mylittlebooklist/translations/messages.pot) as a template
3. and submit the `.po` file. (The compiled `.mo` files are not committed.)

Corrections to existing translations are just as welcome.

## Pull requests

- Branch from `dev` and open the pull request against `dev`.
- Keep each pull request focused on one change.
- Match the style of the surrounding code.
- Mark new UI texts with `_("…")` and update the catalogs (`pybabel extract` and `pybabel update`).
- Run the tests with `uv run pytest` and add a test for new logic.
- Run `uv run ruff check .`, `uv run ruff format .`, `uv run mypy .`, `uv run bandit -r src` and `uv run pip-audit` – all must pass.
- Describe in the pull request what changed and why.

## Branches and releases

- `dev` collects new work. Feature branches are merged into it with `git merge --no-ff` and a merge message listing the changes as `- ` bullets.
- `main` only receives releases and always reflects the latest one.

To make a release:
1. bump the version in `pyproject.toml` on `dev` and run `uv lock`
2. open a pull request from `dev` to `main` and merge it with a merge commit – never squash or rebase
3. tag the merge commit on `main` with `vX.Y.Z` and push the tag, which publishes the `latest` Docker image
4. bring `dev` up to date with `git merge --ff-only main`

An urgent fix branches from `main` and is merged back into `main`. Afterwards, merge `main` into `dev`.
