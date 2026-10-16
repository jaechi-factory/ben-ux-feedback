"""공개 패키지 검사: 생성물 일치, 금지 문구, LICENSE, 설치 스크립트 동작.

실행: python3 -m unittest discover -s tests -v
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build  # noqa: E402

FORBIDDEN = ["/users/", "/home/", "_legacy", "sprint-design-qa", "chihun", "chihoon", "자비스", "—"]
SKIP_DIRS = {"__pycache__"}
SKIP_NAMES = {".DS_Store"}
DOCS = ["README.md", "NOTICE.md", "AGENTS.md", "CHANGELOG.md", "VERSION", "docs/DESIGN_DECISIONS.md"]


def run(script, *args, home=None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True, env=env)


def tree(path):
    path = Path(path)
    return sorted(str(p.relative_to(path)) for p in path.rglob("*")) if path.exists() else []


def public_files():
    files = []
    for d in build.GENERATED_DIRS:
        base = ROOT / d
        files += [p for p in base.rglob("*") if p.is_file()] if base.is_dir() else []
    files.append(ROOT / build.MANIFEST)
    return files


class BuildTest(unittest.TestCase):
    def test_build_check_passes(self):
        r = run("build.py", "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_expected_outputs_are_deterministic_and_clean(self):
        a, b = build.expected_outputs(), build.expected_outputs()
        self.assertEqual(a, b)
        for rel in a:
            parts = Path(rel).parts
            self.assertFalse(SKIP_DIRS & set(parts), rel)
            self.assertNotIn(Path(rel).name, SKIP_NAMES)
            self.assertFalse(rel.endswith(".pyc"), rel)

    def test_chat_files_exist_with_required_content(self):
        for name in ["00_START_HERE.md", "PROJECT_INSTRUCTIONS.md", "KNOWLEDGE.md", "KNOWLEDGE_APPENDIX.md", "REQUEST_EXAMPLES.md"]:
            self.assertTrue((ROOT / "chat" / name).is_file(), name)
        examples = (ROOT / "chat" / "REQUEST_EXAMPLES.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(examples.count("\n## "), 5)

    def test_manifest_hashes_match_files(self):
        manifest = json.loads((ROOT / build.MANIFEST).read_text(encoding="utf-8"))
        self.assertTrue(manifest["files"])
        for rel, digest in manifest["files"].items():
            data = (ROOT / rel).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, rel)


class PublicContentTest(unittest.TestCase):
    def check_text(self, path):
        text = path.read_text(encoding="utf-8").lower()
        for word in FORBIDDEN:
            self.assertNotIn(word, text, f"{path.relative_to(ROOT)}: {word!r}")

    def test_generated_files_have_no_private_or_legacy_text(self):
        for path in public_files():
            self.check_text(path)

    def test_source_and_docs_have_no_private_or_legacy_text(self):
        for path in (ROOT / "skill").rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py", ".json", ".svg", ".html"}:
                self.check_text(path)
        for rel in DOCS:
            path = ROOT / rel
            self.assertTrue(path.is_file(), rel)
            self.check_text(path)

    def test_readme_chat_docs_and_skill_have_no_forbidden_text(self):
        """README, chat, docs, skill 전체에 같은 금지어 검사를 해요.
        이 테스트 파일은 검사 대상이 아니라서 금지어 목록 줄은 따로 예외 처리할 필요가 없어요."""
        paths = [ROOT / "README.md"]
        for d in ("chat", "docs", "skill"):
            paths += [p for p in (ROOT / d).rglob("*") if p.is_file() and p.name not in SKIP_NAMES
                      and "__pycache__" not in p.parts and p.suffix in {".md", ".py", ".json", ".svg", ".html", ".txt"}]
        self.assertTrue(any(p.parent.name == "chat" for p in paths))
        for path in paths:
            self.check_text(path)

    def test_license_and_version(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("jaechi", text)
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "0.2.1")

    def test_gitignore_keeps_local_files_out(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
        for item in ["notes.md", "runs/", "__pycache__/", ".ben-ux-feedback-backups/"]:
            self.assertIn(item, lines)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        self.home.mkdir()
        self.proj.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def dests(self):
        return [self.proj / ".claude/skills/ben-ux-feedback", self.proj / ".agents/skills/ben-ux-feedback"]

    def test_dry_run_writes_nothing(self):
        before = tree(self.tmp)
        for args in (["--scope", "user"], ["--scope", "project", "--project", str(self.proj)]):
            r = run("install.py", *args, home=self.home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("--apply", r.stdout)
        self.assertEqual(tree(self.tmp), before)

    def test_apply_copies_source_files(self):
        r = run("install.py", "--scope", "project", "--project", str(self.proj), "--apply", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        expected = sorted(build.collect_source())
        for dest in self.dests():
            got = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
            self.assertEqual(got, expected)

    def test_user_scope_target_paths(self):
        r = run("install.py", "--target", "claude", "--apply", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.home / ".claude/skills/ben-ux-feedback/SKILL.md").is_file())
        self.assertFalse((self.home / ".agents").exists())
        r = run("install.py", "--target", "codex", "--apply", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.home / ".agents/skills/ben-ux-feedback/SKILL.md").is_file())

    def test_existing_is_kept_without_flag_and_backed_up_with_flag(self):
        args = ["--target", "claude", "--scope", "project", "--project", str(self.proj)]
        self.assertEqual(run("install.py", *args, "--apply", home=self.home).returncode, 0)
        dest = self.dests()[0]
        marker = dest / "MY_LOCAL_EDIT.txt"
        marker.write_text("keep me", encoding="utf-8")

        r = run("install.py", *args, "--apply", home=self.home)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(marker.is_file())
        r = run("install.py", *args, home=self.home)
        self.assertEqual(r.returncode, 1)

        r = run("install.py", *args, "--apply", "--replace-with-backup", home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(marker.exists())
        self.assertTrue((dest / "SKILL.md").is_file())
        backups = list((dest.parent / ".ben-ux-feedback-backups").glob("*/ben-ux-feedback/MY_LOCAL_EDIT.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "keep me")

    def test_dangerous_paths_are_refused(self):
        for bad in (self.home, Path("/"), self.tmp):
            r = run("install.py", "--scope", "project", "--project", str(bad), "--apply", home=self.home)
            self.assertNotEqual(r.returncode, 0, str(bad))
        self.assertEqual(tree(self.home), [])
        r = run("install.py", "--scope", "project", "--project", str(ROOT), "--apply", home=self.home)
        self.assertNotEqual(r.returncode, 0)

    def test_project_scope_requires_project(self):
        r = run("install.py", "--scope", "project", home=self.home)
        self.assertNotEqual(r.returncode, 0)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink 미지원")
    def test_symlinks_are_refused(self):
        link = self.tmp / "link"
        try:
            link.symlink_to(self.proj, target_is_directory=True)
        except OSError:
            self.skipTest("symlink를 만들 수 없어요")
        r = run("install.py", "--scope", "project", "--project", str(link), "--apply", home=self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(tree(self.proj), [])

        other = self.tmp / "elsewhere"
        other.mkdir()
        (self.proj / ".claude").symlink_to(other, target_is_directory=True)
        r = run("install.py", "--scope", "project", "--project", str(self.proj), "--apply", home=self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(tree(other), [])


if __name__ == "__main__":
    unittest.main()
