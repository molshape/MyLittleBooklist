# Contributing to My Little Booklist

Thanks for your interest in **My Little Booklist**! Contributions are welcome – please read this short note first.

## Keeping it simple

**My Little Booklist** is intentionally small and simple: one Flask file, SQLite, server-rendered templates and no JavaScript framework. It should stay easy to run and simple to understand. New features are weighed against that – a smaller change that covers most of the need is usually preferred over a complete one that adds a lot of code or new dependencies.

## Welcome contributions

- **Bug reports** – please include steps to reproduce and what you expected.
- **Fixes and corrections** – code, texts, typos, documentation.
- **Small improvements** – usability, accessibility, performance.
- **New languages** – see below.

For larger changes or new features, please open an issue first so we can discuss whether and how it fits.

## Adding a language

Follow the steps in the [Translating](README.md#translating) section of the [README.md](README.md):
1. create the catalog with `pybabel init`
2. translate `translations/<lang>/LC_MESSAGES/messages.po` using [`messages.pot`](translations/messages.pot) as a template
3. and submit the `.po` file. (The compiled `.mo` files are not committed.)

Corrections to existing translations are just as welcome.

## Pull requests

- Keep each pull request focused on one change.
- Match the style of the surrounding code.
- Mark new UI texts with `_("…")` and update the catalogs (`pybabel extract` and `pybabel update`).
- Run the tests with `uv run pytest` and add a test for new logic.
- Describe in the pull request what changed and why.
