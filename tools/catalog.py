"""Build Mod ZIPs and OCI artifacts; publish those exact artifacts with ORAS."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_TYPE = "application/vnd.renpy.mod.v1"
CONFIG_TYPE = "application/vnd.renpy.mod.config.v1+json"
ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_readme(text, mod_id):
    match = re.match(
        r"\A---\nversion: ((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\n"
        r"---\n\s*# ([^\n]+)\n\s*([^\n]+(?:\n[^\n]+)*)",
        text,
    )
    if not match:
        raise ValueError(
            f"{mod_id}: README requires version front matter, a title and a description"
        )
    version, name, description = match.groups()
    return {
        "id": mod_id,
        "version": version,
        "name": name,
        "description": " ".join(description.split()),
    }


def read_recipe(directory):
    if not ID_PATTERN.fullmatch(directory.name):
        raise ValueError(f"Invalid Mod ID: {directory.name}")
    return parse_readme((directory / "README.md").read_text(), directory.name)


def payload_files(directory):
    root = directory / "files"
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Mod payload cannot contain a symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative.split("/")[0] in {"_mods", "saves"}:
                raise ValueError(f"Payload overwrites launcher data or saves: {relative}")
            files.append((path, relative))
    if not files:
        raise ValueError(f"Empty Mod payload: {directory}")
    return files


def recipes(root):
    return [
        (path.parent, read_recipe(path.parent))
        for path in sorted((root / "mods").glob("*/README.md"))
    ]


def write_zip(files, destination):
    # Small script bundles use STORE: identical bytes across Python/zlib versions.
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, relative in files:
            entry = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())


def check_versions(root, base, items):
    for directory, recipe in items:
        recipe_path = (directory / "README.md").relative_to(root).as_posix()
        existed = subprocess.check_output(
            ["git", "ls-tree", "--name-only", base, "--", recipe_path], cwd=root, text=True
        ).strip()
        if not existed:
            continue
        previous_text = subprocess.check_output(
            ["git", "show", f"{base}:{recipe_path}"], cwd=root, text=True
        )
        # An unversioned README does not declare a package in the base revision.
        if not previous_text.startswith("---\n"):
            continue
        previous = parse_readme(previous_text, recipe["id"])
        changed = subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                base,
                "--",
                (directory / "files").relative_to(root).as_posix(),
            ],
            cwd=root,
            check=False,
        )
        if changed.returncode not in (0, 1):
            changed.check_returncode()
        if changed.returncode == 1 or previous != recipe:
            old = tuple(map(int, previous["version"].split(".")))
            new = tuple(map(int, recipe["version"].split(".")))
            if new <= old:
                raise ValueError(
                    f"{recipe['id']}: changed package requires a version above {previous['version']}"
                )


def fetch_catalog(url):
    try:
        with urlopen(Request(url, headers={"Cache-Control": "no-cache"})) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return {"schemaVersion": 1, "packages": []}
        raise


def published_packages(previous, repository):
    if previous["schemaVersion"] != 1:
        raise ValueError("Unsupported catalog schemaVersion")
    packages = {}
    for package in previous["packages"]:
        mod_id = package["id"]
        artifact = package["artifact"]
        if not ID_PATTERN.fullmatch(mod_id) or mod_id in packages:
            raise ValueError(f"Invalid or duplicate published Mod ID: {mod_id}")
        if artifact["repository"] != f"ghcr.io/{repository}/{mod_id}":
            raise ValueError(f"Published package belongs to another repository: {mod_id}")
        for value in (package["sourceDigest"], artifact["digest"], artifact["zipDigest"]):
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
                raise ValueError(f"Invalid published digest: {mod_id}")
        packages[mod_id] = package
    return packages


def source_digest(recipe, files, license_name):
    return digest(
        json_bytes(
            {
                "recipe": recipe,
                "license": license_name,
                "files": [(relative, digest(path.read_bytes())) for path, relative in files],
            }
        )
    )


def build(root, output, repository, oras, previous=None):
    if not re.fullmatch(r"[a-z0-9-]+/[a-z0-9._-]+", repository):
        raise ValueError("Repository must be a lowercase GitHub owner/repository")
    output = output.resolve()
    license_name = (root / "LICENSE").read_text().splitlines()[0].removesuffix(" License")
    published = published_packages(previous, repository) if previous is not None else {}
    catalog = {"schemaVersion": 1, "packages": []}
    changed = []
    for directory, recipe in recipes(root):
        files = payload_files(directory)
        source = source_digest(recipe, files, license_name)
        old = published.get(recipe["id"])
        if old is not None:
            if old["sourceDigest"] == source:
                catalog["packages"].append(old)
                continue
            if tuple(map(int, recipe["version"].split("."))) <= tuple(
                map(int, old["version"].split("."))
            ):
                raise ValueError(
                    f"{recipe['id']}: changed package requires a version above {old['version']}"
                )
        changed.append(recipe["id"])
        created = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", str(directory.relative_to(root)), "LICENSE"],
            cwd=root,
            text=True,
        ).strip()
        package_dir = output / recipe["id"]
        package_dir.mkdir(parents=True, exist_ok=True)
        archive_path = package_dir / "mod.zip"
        write_zip(files, archive_path)
        metadata = {**recipe, "created": created, "license": license_name, "sourceDigest": source}
        (package_dir / "config.json").write_bytes(json_bytes(metadata))
        subprocess.run(
            [
                oras,
                "push",
                "--oci-layout",
                f"{package_dir / 'oci'}:{recipe['version']}",
                "--artifact-type",
                ARTIFACT_TYPE,
                "--config",
                f"config.json:{CONFIG_TYPE}",
                "--annotation",
                f"org.opencontainers.image.created={created}",
                "--annotation",
                f"org.opencontainers.image.version={recipe['version']}",
                "--annotation",
                f"org.opencontainers.image.source=https://github.com/{repository}",
                "--annotation",
                f"org.opencontainers.image.licenses={license_name}",
                "--export-manifest",
                "manifest.json",
                "mod.zip:application/zip",
            ],
            cwd=package_dir,
            check=True,
        )
        manifest = (package_dir / "manifest.json").read_bytes()
        archive = archive_path.read_bytes()
        catalog["packages"].append(
            {
                **metadata,
                "artifact": {
                    "repository": f"ghcr.io/{repository}/{recipe['id']}",
                    "digest": digest(manifest),
                    "zipDigest": digest(archive),
                    "size": len(archive),
                },
            }
        )
    site = output / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / "catalog.json").write_bytes(json_bytes(catalog))
    (output / "publish.json").write_bytes(json_bytes(changed))
    print(
        f"Built {len(changed)} packages; reused {len(catalog['packages']) - len(changed)} published packages"
    )
    return catalog


def publish(output, oras):
    catalog = json.loads((output / "site/catalog.json").read_text())
    changed = set(json.loads((output / "publish.json").read_text()))
    # Visibility is a registry contract: prove anonymous access before deploying the index.
    with tempfile.TemporaryDirectory() as temp:
        anonymous_config = Path(temp) / "registry.json"
        anonymous_config.write_text('{"auths": {}}')
        for package in catalog["packages"]:
            artifact = package["artifact"]
            reference = f"{artifact['repository']}@{artifact['digest']}"
            local = output.resolve() / package["id"] / "oci"
            # A content-addressed tag keeps the artifact reachable without a mutable version alias.
            tag = artifact["digest"].replace(":", "-")
            if package["id"] in changed:
                subprocess.run(
                    [
                        oras,
                        "cp",
                        "--from-oci-layout",
                        f"{local}@{artifact['digest']}",
                        f"{artifact['repository']}:{tag}",
                    ],
                    check=True,
                )
            subprocess.run(
                [
                    oras,
                    "manifest",
                    "fetch",
                    "--registry-config",
                    str(anonymous_config),
                    reference,
                ],
                stdout=subprocess.DEVNULL,
                check=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument(
        "--base", help="Previous Git revision; changed packages must increase version"
    )
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    build_parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build_parser.add_argument("--oras", default="oras")
    baseline = build_parser.add_mutually_exclusive_group()
    baseline.add_argument("--previous", type=Path, help="Last successfully published catalog")
    baseline.add_argument(
        "--previous-url", help="Pages catalog URL; HTTP 404 means first publication"
    )
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--output", type=Path, default=ROOT / "dist")
    publish_parser.add_argument("--oras", default="oras")
    args = parser.parse_args()
    if args.command == "validate":
        items = recipes(ROOT)
        for directory, _ in items:
            payload_files(directory)
        if args.base:
            check_versions(ROOT, args.base, items)
        print(f"Validated {len(items)} Mod recipes")
    elif args.command == "build":
        previous = None
        if args.previous:
            previous = json.loads(args.previous.read_text())
        elif args.previous_url:
            previous = fetch_catalog(args.previous_url)
        result = build(ROOT, args.output, args.repository, args.oras, previous)
        print(f"Catalog contains {len(result['packages'])} packages in {args.output}")
    else:
        publish(args.output, args.oras)


if __name__ == "__main__":
    main()
