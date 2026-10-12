# Development and publishing

## Local tools

Use Python 3.11+, uv, and ORAS 1.3.4. Docker is not required.

```sh
uv sync --locked
uv run python tools/catalog.py validate
uv run python tools/catalog.py build --repository ren-launcher/mods
uv run python -m unittest discover -s tests -v
uv run ruff check .
```

Pass `--oras /path/to/oras` when ORAS is outside PATH. Tests accept `ORAS=/path/to/oras`.

Build outputs under ignored `dist/` include each mod’s ZIP, derived config, manifest and OCI layout, the complete `site/catalog.json`, and `publish.json` listing packages to upload. Building does not upload packages or modify games.

## Adding and updating mods

Create `mods/<id>/README.md` and `files/`. Payload paths are relative to the game root. Symlinks, `_mods/`, and `saves/` are forbidden. A simple mod can use `files/game/<mod-name>.rpy`; multiple files can share their own directory under `game/`.

README front matter contains a three-part version and optional `games` keywords and a `renpy` version constraint. The heading supplies the name and the first paragraph supplies the description. Put all remaining text in named sections.

```markdown
---
version: 1.0.0
games:
  - example game
renpy: "==7.3.5"
---

# Example

A short description.

## Usage

Instructions specific to this mod.
```

`games` lists literal game-name keywords, not wildcard patterns. Clients compare each keyword with the original game name using substring matching after case folding and removing whitespace, hyphens, and underscores from both values. Any match recommends the mod; missing `games` means a general-purpose mod. Matching does not guarantee version compatibility or restrict manual installation.

Game keywords and runtime constraints belong to the catalog, not the OCI config. Changing them updates recommendations while reusing the existing artifact and does not require a mod version increase.

`renpy` is an optional quoted constraint. Use `==7.3.5` for an exact version or `>=7.3.5,<8.0.0` for a range. Comparisons support `==`, `!=`, `>=`, `<=`, `>`, and `<`, with three-part versions; comma-separated comparisons must all match. Omission means no declared runtime restriction, not verified compatibility. Clients compare the detected runtime version.

The directory supplies the package ID. The root LICENSE supplies the license; do not copy it into payloads. Build arguments supply the source repository. Artifact timestamps come from the last commit affecting the mod or LICENSE, so unrelated commits do not change artifacts.

Increase the version when changing the name, description, or payload. Usage-only changes do not require a release. Validate against an earlier commit with:

```sh
uv run python tools/catalog.py validate --base <previous-commit>
```

## Catalog and incremental publishing

GitHub Pages serves the generated catalog at `https://ren-launcher.github.io/mods/catalog.json`. Availability depends on a successful deployment. The catalog is generated, never edited or committed manually. RenDroid’s OCI download integration is not implemented yet.

CI reads the last deployed catalog. Set repository variable `CATALOG_URL` for a custom domain. HTTP 404 starts an initial full build; other HTTP errors fail publication.

`sourceDigest` covers derived README metadata, payload paths and contents, and the repository license. Unchanged packages reuse published entries without rebuilding or uploading. Changed packages require a higher version. Deleted recipes disappear from the catalog; historical registry artifacts remain.

The upload plan contains only new or changed packages. Publication checks anonymous access to every catalog entry before deploying the complete catalog. Failed publication does not advance the baseline.

```sh
uv run python tools/catalog.py build --repository ren-launcher/mods --previous /path/to/catalog.json
uv run python tools/catalog.py build --repository ren-launcher/mods --previous-url <catalog-url>
python3 -m json.tool dist/site/catalog.json
```

## Remote setup

Enable GitHub Pages with GitHub Actions as its source. Main-branch pushes and manual runs publish; pull requests only validate and build. The workflow uses `GITHUB_TOKEN` to upload its original OCI artifacts without repackaging.

New GHCR packages must be made public after their first upload, with the repository granted Actions access. A public Git repository does not make its packages public. If anonymous verification fails on first publication, change package visibility and rerun the failed job. Clients do not need a publishing token.

For local publishing, authenticate with `oras login ghcr.io`, then run:

```sh
uv run python tools/catalog.py publish
```

Verify the deployed catalog and ZIP downloads without authentication and check their digests. Local lint and OCI round trips do not replace remote permission and deployment checks.

## Game verification

Install into a clean game copy and manually check the UI, ordinary and persistent variable writes, save/load, and restart behavior. Android and other runtime versions require their own verification.
