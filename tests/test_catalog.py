import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from tools import catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copyfile(catalog.ROOT / "LICENSE", self.root / "LICENSE")
        shutil.copytree(catalog.ROOT / "mods", self.root / "mods")
        self.oras = os.environ.get("ORAS", "oras")
        for args in (
            ("init", "-q"),
            ("config", "user.name", "Catalog test"),
            ("config", "user.email", "test@example.invalid"),
            ("add", "."),
            ("commit", "-qm", "Initial source"),
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True)

    def test_payload_round_trip_and_reproducible_artifact(self):
        first = catalog.build(self.root, self.root / "one", "ren-launcher/mods", self.oras)
        second = catalog.build(self.root, self.root / "two", "ren-launcher/mods", self.oras)
        self.assertEqual(first, second)
        expected = {
            "bionic-fflush-ebadf": {"game/00bionic_fflush_fix.rpy"},
            "hello-world": {
                "game/hello_world.rpy",
            },
            "variable-editor": {
                "game/variable_editor/editor.rpy",
                "game/variable_editor/adjust.svg",
                "game/variable_editor/search.svg",
            },
        }
        self.assertEqual({p["id"] for p in first["packages"]}, set(expected))
        for package in first["packages"]:
            artifact = package["artifact"]
            package_dir = self.root / "one" / package["id"]
            pulled = self.root / "pulled" / package["id"]
            subprocess.run(
                [
                    self.oras,
                    "pull",
                    "--oci-layout",
                    f"{package_dir / 'oci'}@{artifact['digest']}",
                    "--output",
                    str(pulled),
                ],
                check=True,
            )
            bundle = (pulled / "mod.zip").read_bytes()
            self.assertEqual("sha256:" + hashlib.sha256(bundle).hexdigest(), artifact["zipDigest"])
            manifest = json.loads((package_dir / "manifest.json").read_text())
            self.assertEqual(manifest["artifactType"], "application/vnd.renpy.mod.v1")
            self.assertEqual(manifest["layers"][0]["digest"], artifact["zipDigest"])
            with zipfile.ZipFile(pulled / "mod.zip") as archive:
                self.assertEqual(set(archive.namelist()), expected[package["id"]])
                original = self.root / "mods" / package["id"] / "files"
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), (original / name).read_bytes())

    def test_incremental_build_reuses_changes_adds_and_removes_packages(self):
        repository = "ren-launcher/mods"
        first = catalog.build(self.root, self.root / "published", repository, self.oras)
        unchanged_dir = self.root / "unchanged"
        unchanged = catalog.build(self.root, unchanged_dir, repository, self.oras, first)
        self.assertEqual(unchanged, first)
        self.assertEqual(json.loads((unchanged_dir / "publish.json").read_text()), [])
        self.assertFalse((unchanged_dir / "hello-world").exists())
        self.assertFalse((unchanged_dir / "variable-editor").exists())

        hello = self.root / "mods/hello-world"
        script = hello / "files/game/hello_world.rpy"
        script.write_text(script.read_text() + "\n# modified\n")
        with self.assertRaisesRegex(ValueError, "requires a version"):
            catalog.build(self.root, self.root / "rejected", repository, self.oras, first)
        readme = hello / "README.md"
        readme.write_text(re.sub(r"version: \d+\.\d+\.\d+", "version: 99.0.0", readme.read_text()))
        shutil.copytree(hello, self.root / "mods/new-mod")
        changed_dir = self.root / "changed"
        second = catalog.build(self.root, changed_dir, repository, self.oras, first)
        entries = {package["id"]: package for package in second["packages"]}
        old_entries = {package["id"]: package for package in first["packages"]}
        self.assertEqual(entries["variable-editor"], old_entries["variable-editor"])
        self.assertNotEqual(
            entries["hello-world"]["artifact"], old_entries["hello-world"]["artifact"]
        )
        self.assertEqual(
            json.loads((changed_dir / "publish.json").read_text()), ["hello-world", "new-mod"]
        )

        # The same published baseline is used after a failed publication, so changes are retried.
        retry = catalog.build(self.root, self.root / "retry", repository, self.oras, first)
        self.assertEqual(retry, second)
        shutil.rmtree(hello)
        removed_dir = self.root / "removed"
        third = catalog.build(self.root, removed_dir, repository, self.oras, second)
        self.assertEqual({p["id"] for p in third["packages"]}, {"bionic-fflush-ebadf", "new-mod", "variable-editor"})
        self.assertEqual(json.loads((removed_dir / "publish.json").read_text()), [])

        with patch("tools.catalog.subprocess.run") as run:
            catalog.publish(changed_dir, self.oras)
        copied = [call.args[0] for call in run.call_args_list if call.args[0][1] == "cp"]
        fetched = [call.args[0] for call in run.call_args_list if call.args[0][1] == "manifest"]
        self.assertEqual(len(copied), 2)
        self.assertEqual(len(fetched), 4)
        self.assertEqual(
            {command[-1].split(":")[0] for command in copied},
            {
                "ghcr.io/ren-launcher/mods/hello-world",
                "ghcr.io/ren-launcher/mods/new-mod",
            },
        )

    def test_unrelated_commit_does_not_change_artifacts(self):
        first = catalog.build(self.root, self.root / "one", "ren-launcher/mods", self.oras)
        (self.root / "DEVELOPMENT.md").write_text("Documentation only.\n")
        subprocess.run(["git", "add", "DEVELOPMENT.md"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "Docs", "--date=2030-01-01T00:00:00Z"],
            cwd=self.root,
            check=True,
            env={**os.environ, "GIT_COMMITTER_DATE": "2030-01-01T00:00:00Z"},
        )
        second = catalog.build(self.root, self.root / "two", "ren-launcher/mods", self.oras)
        self.assertEqual(first, second)

    def test_catalog_404_is_initial_publication_other_errors_fail(self):
        url = "https://example.invalid/catalog.json"
        with patch(
            "tools.catalog.urlopen", side_effect=HTTPError(url, 404, "Not found", Message(), None)
        ):
            self.assertEqual(catalog.fetch_catalog(url), {"schemaVersion": 1, "packages": []})
        with (
            patch(
                "tools.catalog.urlopen",
                side_effect=HTTPError(url, 503, "Unavailable", Message(), None),
            ),
            self.assertRaises(HTTPError),
        ):
            catalog.fetch_catalog(url)

    def test_recipe_rejects_invalid_version(self):
        path = self.root / "mods/variable-editor/README.md"
        path.write_text(re.sub(r"version: \d+\.\d+\.\d+", "version: latest", path.read_text()))
        with self.assertRaises(ValueError):
            catalog.recipes(self.root)

    def test_recipe_rejects_missing_version(self):
        path = self.root / "mods/variable-editor/README.md"
        path.write_text("# Editor\n\nDescription.\n")
        with self.assertRaises(ValueError):
            catalog.recipes(self.root)

    def test_recipe_derives_identity_and_description(self):
        directory = self.root / "mods/variable-editor"
        (directory / "README.md").write_text(
            "---\nversion: 2.3.4\n---\n\n# Example Editor\n\nFirst line\nsecond line.\n\nUsage.\n"
        )
        self.assertEqual(
            catalog.read_recipe(directory),
            {
                "id": "variable-editor",
                "version": "2.3.4",
                "name": "Example Editor",
                "description": "First line second line.",
            },
        )

    def test_payload_rejects_symlink_and_reserved_save_path(self):
        directory = self.root / "mods/variable-editor"
        link = directory / "files/escape"
        link.symlink_to(self.root / "LICENSE")
        with self.assertRaisesRegex(ValueError, "symlink"):
            catalog.payload_files(directory)
        link.unlink()
        save = directory / "files/saves/persistent"
        save.parent.mkdir()
        save.write_text("should not be packaged")
        with self.assertRaisesRegex(ValueError, "saves"):
            catalog.payload_files(directory)

    def test_changed_payload_requires_a_version_increase(self):
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

        recipe = self.root / "mods/variable-editor/README.md"
        recipe.write_text(re.sub(r"version: \d+\.\d+\.\d+", "version: 0.1.0", recipe.read_text()))
        git("init", "-q")
        git("config", "user.name", "Catalog test")
        git("config", "user.email", "test@example.invalid")
        git("add", ".")
        git("commit", "-qm", "Initial recipe")
        base = git("rev-parse", "HEAD")
        catalog.check_versions(self.root, base, catalog.recipes(self.root))
        recipe.write_text(recipe.read_text() + "\nAdditional usage instructions.\n")
        catalog.check_versions(self.root, base, catalog.recipes(self.root))
        recipe.write_text(recipe.read_text().replace("# Variable Editor", "# Renamed Editor"))
        with self.assertRaisesRegex(ValueError, "requires a version"):
            catalog.check_versions(self.root, base, catalog.recipes(self.root))
        recipe.write_text(recipe.read_text().replace("# Renamed Editor", "# Variable Editor"))
        source = self.root / "mods/variable-editor/files/game/variable_editor/editor.rpy"
        source.write_text(source.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(ValueError, "requires a version"):
            catalog.check_versions(self.root, base, catalog.recipes(self.root))
        recipe.write_text(recipe.read_text().replace("version: 0.1.0", "version: 0.1.1"))
        catalog.check_versions(self.root, base, catalog.recipes(self.root))


if __name__ == "__main__":
    unittest.main()
