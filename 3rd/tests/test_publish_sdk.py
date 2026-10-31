"""离线验证 PR 重试、分支变化和拒绝覆盖；所有 Git/GitHub 操作均为模拟。"""

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("publish_sdk", REPOSITORY / "3rd/ci/publish-sdk.py")
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)
COMMIT = "1" * 40
PROPOSAL = "2" * 40
TREE = "3" * 40
TIMESTAMP = "20261009_1301"
HEAD = "automation/native-sdk/" + TIMESTAMP
URL = "https://github.com/Countra/termous-video/pull/42"


class PublicationTests(unittest.TestCase):
    def setUp(self):
        build = REPOSITORY / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="sdk-pr-test-", dir=build)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "build/publish").mkdir(parents=True)
        self.calls = []
        self.staged = False
        self.has_changes = True
        self.changed = "sdk/windows/amd64/manifest.json"
        self.remotes = {"main": COMMIT, "develop": COMMIT, "release/sdk": COMMIT}
        self.remote_tree = TREE
        self.remote_parent = COMMIT
        self.proposals = []
        self.create_error = None
        # 捕获模拟发布输出，避免 CI 日志把测试仓库链接显示成实际发布结果。
        self.output = io.StringIO()
        for change in (
            patch("sys.stdout", self.output),
            patch.object(publish, "ROOT", self.root),
            patch.object(publish, "git", side_effect=self.git),
            patch.object(publish, "gh", side_effect=self.gh),
            patch.dict(os.environ, {
                "PROPOSAL_TIMESTAMP": TIMESTAMP, "GITHUB_REPOSITORY": "Countra/termous-video",
                "GITHUB_STEP_SUMMARY": str(self.root / "summary.md"),
            }),
        ):
            change.start()
            self.addCleanup(change.stop)
        change = patch.object(publish, "verify_manifest")
        self.verify = change.start()
        self.addCleanup(change.stop)

    def git(self, *args):
        self.calls.append(("git", *args))
        if args == ("rev-parse", "HEAD"): return COMMIT
        if args[0] == "check-ref-format": return ""
        if args[0] == "ls-remote":
            commit = self.remotes.get(args[-1].removeprefix("refs/heads/"))
            return f"{commit}\t{args[-1]}" if commit else ""
        if args == ("diff", "--cached", "--name-only"):
            return self.changed if self.staged and self.has_changes else ""
        if args == ("diff", "--name-only"): return self.changed if self.has_changes else ""
        if args[0] == "ls-files": return ""
        if args[0] == "add":
            self.staged = True
            return ""
        if args == ("rev-parse", "FETCH_HEAD"): return PROPOSAL
        if args == ("rev-parse", "FETCH_HEAD^{tree}"): return self.remote_tree
        if args == ("write-tree",): return TREE
        if args == ("rev-list", "--parents", "-n", "1", "FETCH_HEAD"):
            return f"{PROPOSAL} {self.remote_parent}"
        if args[0] == "fetch" or "commit" in args: return ""
        if args[0] == "push":
            self.assertEqual(args, ("push", "origin", "HEAD:refs/heads/" + HEAD))
            self.remotes[HEAD] = PROPOSAL
            return ""
        raise AssertionError(f"Unexpected Git command: {args}")

    def gh(self, *args):
        self.calls.append(("gh", *args))
        if args[:2] == ("pr", "list"): return json.dumps(self.proposals)
        if args[:2] == ("pr", "create"):
            if self.create_error:
                raise self.create_error
            self.proposals = [{"url": URL, "state": "OPEN", "baseRefName": args[args.index("--base") + 1], "headRefOid": PROPOSAL}]
            return URL
        raise AssertionError(f"Unexpected GitHub command: {args}")

    def assert_no_remote_write(self):
        self.assertFalse(any(c[:2] == ("git", "push") or c[:3] == ("gh", "pr", "create") for c in self.calls))

    def test_creates_pr_from_timestamp_branch_to_selected_base(self):
        publish.publish("release/sdk", COMMIT)
        self.assertEqual(self.verify.call_count, 3)
        self.assertTrue(all(call.args[0].is_relative_to(self.root / "sdk")
                            for call in self.verify.call_args_list))
        self.assertIn(("git", "add", "--", "sdk/windows/amd64", "sdk/linux/amd64",
                       "sdk/darwin/arm64"), self.calls)
        commits = [c for c in self.calls if c[0] == "git" and "commit" in c]
        self.assertEqual(len(commits), 1)
        self.assertIn("-F", commits[0])
        self.assertIn(("git", "push", "origin", "HEAD:refs/heads/" + HEAD), self.calls)
        create = next(c for c in self.calls if c[:3] == ("gh", "pr", "create"))
        self.assertEqual(create[create.index("--repo") + 1], "Countra/termous-video")
        self.assertEqual(create[create.index("--head") + 1], HEAD)
        self.assertEqual(create[create.index("--base") + 1], "release/sdk")
        body = Path(create[create.index("--body-file") + 1]).read_text(encoding="utf-8")
        self.assertIn(COMMIT, body)
        self.assertIn("OpenH264 decodes these sequences", body)
        self.assertIn("encoder-only link check excludes OpenH264", body)
        self.assertIn("\n\n", body)
        self.assertIn(URL, (self.root / "summary.md").read_text(encoding="utf-8"))
        self.assertIn(f"SDK pull request ready for review: {URL}", self.output.getvalue())

    def test_retry_reuses_identical_branch_and_open_pr(self):
        publish.publish("main", COMMIT)
        self.calls.clear()
        self.staged = False
        publish.publish("main", COMMIT)
        self.assert_no_remote_write()
        self.assertFalse(any("commit" in c for c in self.calls))

    def test_retry_recovers_after_pr_creation_failed(self):
        self.create_error = subprocess.CalledProcessError(1, ["gh", "pr", "create"])
        with self.assertRaises(subprocess.CalledProcessError):
            publish.publish("main", COMMIT)
        self.assertIn(HEAD, self.remotes)
        self.calls.clear()
        self.staged = False
        self.create_error = None
        publish.publish("main", COMMIT)
        self.assertFalse(any(c[:2] == ("git", "push") or "commit" in c for c in self.calls))
        self.assertEqual(sum(c[:3] == ("gh", "pr", "create") for c in self.calls), 1)

    def test_changed_or_rebased_proposal_branch_is_not_overwritten(self):
        self.remotes[HEAD] = PROPOSAL
        for field in ("remote_tree", "remote_parent"):
            with self.subTest(field=field), patch.object(self, field, "9" * 40):
                self.staged = False
                with self.assertRaisesRegex(ValueError, "differs from this build"):
                    publish.publish("main", COMMIT)
                self.assert_no_remote_write()

    def test_closed_or_retargeted_pr_is_not_reopened(self):
        for state, base in (("CLOSED", "main"), ("MERGED", "main"), ("OPEN", "develop")):
            with self.subTest(state=state, base=base):
                self.staged = False
                self.proposals = [{"url": URL, "state": state, "baseRefName": base, "headRefOid": PROPOSAL}]
                with self.assertRaisesRegex(ValueError, "closed, merged or targets"):
                    publish.publish("main", COMMIT)
                self.assert_no_remote_write()

    def test_unchanged_sdk_does_not_create_branch_or_pr(self):
        self.has_changes = False
        publish.publish("main", COMMIT)
        self.assert_no_remote_write()
        self.assertFalse(any(c[0] == "gh" for c in self.calls))

    def test_changed_target_or_unrelated_files_stop_publication(self):
        self.remotes["main"] = "9" * 40
        with self.assertRaisesRegex(ValueError, "advanced"):
            publish.publish("main", COMMIT)
        self.remotes["main"] = COMMIT
        self.changed = "go.mod"
        with self.assertRaisesRegex(ValueError, "outside platform SDK"):
            publish.publish("main", COMMIT)
        self.assertFalse(any(c[:2] == ("git", "add") for c in self.calls))
        self.assert_no_remote_write()

    def test_invalid_sdk_stops_before_writing(self):
        self.verify.side_effect = ValueError("Invalid SDK")
        with self.assertRaisesRegex(ValueError, "Invalid SDK"):
            publish.publish("main", COMMIT)
        self.assert_no_remote_write()

    def test_default_and_explicit_base_branch(self):
        for target, expected in (("", "develop"), ("release/sdk", "release/sdk")):
            output = self.root / "github-output"
            with self.subTest(target=target), patch.dict(os.environ, {
                "INPUT_TARGET_BRANCH": target, "GITHUB_REF_NAME": "develop",
                "GITHUB_REF_TYPE": "branch", "GITHUB_OUTPUT": str(output),
            }):
                publish.resolve()
                self.assertIn(f"branch={expected}\n", output.read_text(encoding="utf-8"))

    def test_branch_input_cannot_inject_output_lines(self):
        with self.assertRaises(ValueError):
            publish.validate_branch("main\nsha=evil")
        self.assertEqual(self.calls, [])

    def test_nonexistent_branch_rejected(self):
        with self.assertRaisesRegex(ValueError, "already exist"):
            publish.remote_head("missing")

    def test_resolve_records_beijing_timestamp_once(self):
        output = self.root / "github-output"
        with patch.dict(os.environ, {
            "INPUT_TARGET_BRANCH": "main", "GITHUB_OUTPUT": str(output),
        }), patch.object(publish, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = lambda tz: datetime(2026, 10, 8, 23, 1, tzinfo=UTC).astimezone(tz)
            publish.resolve()
            clock.now.assert_called_once_with(timezone(timedelta(hours=8)))
        self.assertEqual(output.read_text(encoding="utf-8"),
                         f"branch=main\nsha={COMMIT}\nproposal_timestamp=20261009_0701\n")

    def test_invalid_timestamp_and_self_target_rejected(self):
        for value in ("12345", "20261009_1301\n", "20260230_1301", "20261009_2400", "20261009_1360"):
            with self.subTest(value=value), patch.dict(os.environ, {"PROPOSAL_TIMESTAMP": value}), \
                    self.assertRaisesRegex(ValueError, "timestamp"):
                publish.proposal_context("main")
        with self.assertRaisesRegex(ValueError, "differ from the target"):
            publish.proposal_context(HEAD)


if __name__ == "__main__":
    unittest.main()
