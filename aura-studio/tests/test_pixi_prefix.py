"""The small repair script for a Pixi environment whose checkout moved."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "fix-pixi-prefix.py")


class PixiPrefixTest(unittest.TestCase):
    def test_rewrites_text_files_and_keeps_binaries(self):
        with tempfile.TemporaryDirectory(prefix="aura-pixi-prefix-") as directory:
            old_project = os.path.join(directory, "old", "aura-studio")
            new_project = os.path.join(directory, "new", "aura-studio")
            environment = os.path.join(new_project, ".pixi", "envs", "default")
            metadata = os.path.join(environment, "conda-meta")
            os.makedirs(metadata)
            old_environment = os.path.join(
                old_project, ".pixi", "envs", "default")

            with open(os.path.join(metadata, "pixi_env_prefix"), "w",
                      encoding="utf-8") as handle:
                handle.write(old_environment + "/conda-meta\n")
            with open(os.path.join(metadata, "pixi"), "w", encoding="utf-8") as handle:
                json.dump({"manifest_path": os.path.join(old_project, "pixi.toml")},
                          handle)

            script = os.path.join(environment, "bin", "python-config")
            os.makedirs(os.path.dirname(script))
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(f"prefix={old_environment}\n")
            binary = os.path.join(environment, "lib", "libthing.so")
            os.makedirs(os.path.dirname(binary))
            with open(binary, "wb") as handle:
                handle.write(b"\0" + old_project.encode() + b"\0")

            result = subprocess.run(
                [sys.executable, SCRIPT, environment],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

            with open(script, encoding="utf-8") as handle:
                self.assertIn(new_project, handle.read())
            with open(os.path.join(metadata, "pixi"), encoding="utf-8") as handle:
                self.assertIn(new_project, handle.read())
            with open(os.path.join(metadata, "pixi_env_prefix"),
                      encoding="utf-8") as handle:
                self.assertIn(new_project, handle.read())
            with open(binary, "rb") as handle:
                self.assertIn(old_project.encode(), handle.read())


if __name__ == "__main__":
    unittest.main()
