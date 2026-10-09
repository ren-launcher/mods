# Mod distribution design

## Scope and ownership

A mod is a ZIP overlay relative to the game root. This repository owns mod sources, recipes, packaging, and catalog publication. The launcher owns installation, backups, and installed state. Running Ren’Py store and persistent objects own game variables.

| Fact | Source of truth | Derived output |
| --- | --- | --- |
| Package ID | `mods/<id>/` | Catalog ID |
| Version, name, description | README front matter, title, first paragraph | Config and catalog metadata |
| Installation content | `files/` | ZIP layer |
| Available packages | Main-branch recipes | Catalog |
| Installed files and backups | Launcher installation module | Launcher UI |
| Game values | Running store/persistent | Editor UI |

Commands change the owner. Derived views never maintain another authoritative copy.

## Recipes and artifacts

Recipes have no separate metadata file or installation script. Historical READMEs without versions are not published recipes. License information comes from the repository LICENSE and is excluded from ZIP payloads. Compatibility is documented per mod; general-purpose does not mean compatible with every engine.

ZIP entries have sorted paths, fixed timestamps and permissions, and use ZIP STORE for reproducible bytes. ORAS creates a local OCI layout and copies it unchanged to GHCR.

- Artifact type: `application/vnd.renpy.mod.v1`.
- Config type: `application/vnd.renpy.mod.config.v1+json`.
- One `application/zip` layer named `mod.zip`.
- Annotations include source, version, license, and the last relevant Git commit timestamp.

Registry paths are `ghcr.io/<owner>/<repo>/<mod-id>`. Catalog references use full manifest digests. A `sha256-<full-digest>` tag keeps the artifact reachable; there are no moving latest or version aliases. Manifest and ZIP digests verify different objects.

## Catalog and publication

The generated catalog uses schema version 1. Each package includes metadata, `sourceDigest`, and:

```json
{
  "artifact": {
    "repository": "ghcr.io/ren-launcher/mods/variable-editor",
    "digest": "sha256:<manifest-digest>",
    "zipDigest": "sha256:<zip-digest>",
    "size": 12345
  }
}
```

Git preserves recipe history; GHCR preserves artifacts. Clients discover current versions through the catalog rather than registry tag enumeration.

CI compares source digests with the last successfully deployed catalog. Unchanged entries reuse existing artifacts; new or changed packages enter the upload plan, and removed recipes leave the catalog. Publication follows validation, build, upload, anonymous verification, then catalog deployment. Failures leave the deployed catalog unchanged. Same-branch publications run serially without cancellation.

New GHCR packages require public visibility. Anonymous verification uses an empty authentication configuration so CI credentials cannot conceal client access failures. Removing a recipe does not remove installed mods or historical artifacts.

## Android client contract

The client uses HTTP without Docker or ORAS:

1. Fetch and validate the catalog at the network boundary.
2. Request the manifest by digest and handle the registry Bearer challenge. Public packages do not require a user PAT.
3. Verify raw manifest bytes, artifact type, and the single ZIP layer’s digest and size.
4. Download and verify the ZIP, then pass it to the existing mod importer.

Redirect URLs are temporary, not package identities. Authentication headers stay with the intended registry. Validation belongs at network and extraction boundaries; internal code trusts established constraints. Digests identify content, while trust comes from the selected catalog publisher.

RenDroid has URL downloads and ZIP import, but OCI retrieval remains future work. Downloads should converge on the existing importer. Installation records own catalog source, package ID, version, and manifest digest. The online catalog does not own installed state. The initial integration uses one official catalog and retains manual ZIP import; dependency solving and automatic updates are outside the current scope.

## Installation lifecycle

Downloading can happen independently. Enabling writes game files and must use the existing game-running state and file-access owner. Updating must disable the old overlay, replace package content, reapply the enabled state, and retain backup and recovery behavior within that installation module. Directly copying a new ZIP over an old one leaves deleted files behind.

Ren’Py generates `.rpyc` files. Uninstallation must remove generated files belonging to the mod as well as tracked payload files. This belongs to the installation module, not the catalog. Uninstallation does not undo saved variable edits.

## Variable editor

The editor loads through Ren’Py scripts and runs on its interaction thread. UI state contains paths, search terms, and uncommitted drafts rather than copied object graphs. Reads and writes resolve the current store/persistent path each time.

Dictionaries, lists, and objects with instance dictionaries can be browsed. Only bool, int, float, and string leaves can be edited. Object traversal reads public instance fields without invoking properties or methods. Input is parsed according to the existing type; invalid numbers show errors without changing values, and no eval is used.

Assignments target the original object. Ordinary writes retain immediate-save behavior; persistent writes call `save_persistent()`. Game-specific business rules remain outside the generic editor.

## Verification

Local checks cover reproducible artifacts, real ORAS round trips, payload validation, version changes, incremental reuse and deletion, retries after failed publication, and initial HTTP 404 handling. Real games are checked manually. Remote registry access, Pages deployment, Android behavior, and additional engine versions require independent verification.

## References

- [Homebrew formula cookbook](https://docs.brew.sh/Formula-Cookbook)
- [Homebrew bottle API](https://formulae.brew.sh/docs/api/)
- [ORAS push](https://oras.land/docs/commands/oras_push/)
- [GitHub container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Ren’Py persistent data](https://www.renpy.org/doc/html/persistent.html)
- [Ren’Py saves and rollback](https://www.renpy.org/doc/html/save_load_rollback.html)
