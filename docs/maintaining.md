# Maintaining

## Branches

- `dev` collects new work. Feature branches are merged into it with `git merge --no-ff` and a merge message listing the changes as `- ` bullets.
- `main` only receives releases and always reflects the latest one.

## Making a release

1. bump the version in `pyproject.toml` on `dev` and run `uv lock`, and update `Project-Id-Version` in the translation catalogs (`messages.po`)
2. open a pull request from `dev` to `main` and merge it with a merge commit – never squash or rebase
3. tag the merge commit on `main` with `vX.Y.Z` and push the tag, which publishes the `latest` Docker image
4. once the image is built, create a GitHub release for the tag with the changes and upgrade notes
5. bring `dev` up to date with `git merge --ff-only main`

## Urgent fixes

An urgent fix branches from `main` and is merged back into `main`. Afterwards, merge `main` into `dev`.
