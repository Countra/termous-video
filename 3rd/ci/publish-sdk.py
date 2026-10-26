"""锁定来源提交，将完整 SDK 组提交至专用分支并发起 PR。"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.pycache_prefix = str(ROOT / "build/cache/pycache")
sys.path.insert(0, str(ROOT / "3rd"))
from lib.platforms import TARGETS
from lib.sdk_manifest import verify_manifest


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def gh(*args):
    return subprocess.check_output(["gh", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def validate_branch(branch):
    if not branch or branch.startswith(("-", "refs/")) or any(c in branch for c in "\r\n\0"):
        raise ValueError("Specify an existing branch name, without refs/heads/ or control characters")
    git("check-ref-format", "refs/heads/" + branch)
    return branch


def remote_head(branch, required=True):
    ref = "refs/heads/" + validate_branch(branch)
    lines = git("ls-remote", "--heads", "origin", ref).splitlines()
    if not lines and not required:
        return None
    if len(lines) != 1 or not re.fullmatch(r"[0-9a-f]{40}\t" + re.escape(ref), lines[0]):
        raise ValueError("The target branch must already exist in this repository")
    return lines[0].split("\t")[0]


def resolve():
    branch = os.environ.get("INPUT_TARGET_BRANCH", "") or os.environ["GITHUB_REF_NAME"]
    if not os.environ.get("INPUT_TARGET_BRANCH") and os.environ.get("GITHUB_REF_TYPE") != "branch":
        raise ValueError("Select a workflow branch or explicitly provide a target branch")
    branch = validate_branch(branch)
    commit = remote_head(branch)
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"branch={branch}\nsha={commit}\nproposal_timestamp={timestamp}\n")
    print(f"SDK build source and PR base branch: {branch} ({commit})")


def proposal_context(base):
    timestamp = os.environ["PROPOSAL_TIMESTAMP"]
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[0-9]{8}_[0-9]{4}", timestamp):
        raise ValueError("Invalid proposal timestamp; expected YYYYMMDD_HHMM in UTC+8")
    try:
        datetime.strptime(timestamp, "%Y%m%d_%H%M")
    except ValueError as error:
        raise ValueError("Invalid proposal timestamp date or time") from error
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository")
    head = f"automation/native-sdk/{timestamp}"
    if head == base:
        raise ValueError("SDK proposal branch must differ from the target branch")
    return repository, head


def find_proposal(repository, head, base):
    proposals = json.loads(gh("pr", "list", "--repo", repository, "--head", head, "--state", "all",
                              "--json", "url,state,baseRefName,headRefOid", "--limit", "10"))
    if not isinstance(proposals, list) or len(proposals) > 1:
        raise ValueError("Expected at most one PR for this SDK proposal branch")
    if not proposals:
        return None
    proposal = proposals[0]
    if proposal["state"] != "OPEN" or proposal["baseRefName"] != base:
        raise ValueError("Existing SDK PR is closed, merged or targets another branch; start a new workflow run")
    return proposal


def report_proposal(url):
    print(f"SDK pull request ready for review: {url}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(f"SDK pull request: {url}\n")


def publish(branch, commit):
    branch = validate_branch(branch)
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or git("rev-parse", "HEAD") != commit:
        raise ValueError("Publication checkout does not match the selected source commit")
    for target in TARGETS:
        verify_manifest(ROOT / "sdk" / target, target, commit)
    if git("diff", "--cached", "--name-only"):
        raise ValueError("Publication requires an empty staging area")
    allowed = tuple("sdk/" + target + "/" for target in TARGETS)
    changed = git("diff", "--name-only").splitlines() + git("ls-files", "--others", "--exclude-standard").splitlines()
    if any(not name.startswith(allowed) for name in changed):
        raise ValueError("Unexpected changes outside platform SDK directories")
    if remote_head(branch) != commit:
        raise ValueError("Target branch advanced during the build; start a new workflow run")
    git("add", "--", *("sdk/" + target for target in TARGETS))
    if not git("diff", "--cached", "--name-only"):
        print("SDK contents are unchanged; no pull request is needed.")
        return
    repository, head = proposal_context(branch)
    proposal = find_proposal(repository, head, branch)
    existing = remote_head(head, required=False)
    if existing:
        # 重试只复用完全一致的提案，不能覆盖已有人工修改或不同产物。
        git("fetch", "--no-tags", "origin", "refs/heads/" + head)
        if (git("rev-parse", "FETCH_HEAD") != existing or
                git("rev-list", "--parents", "-n", "1", "FETCH_HEAD") != f"{existing} {commit}" or
                git("rev-parse", "FETCH_HEAD^{tree}") != git("write-tree")):
            raise ValueError("Existing SDK branch differs from this build; start a new workflow run. No branch was overwritten.")
        if proposal and proposal["headRefOid"] != existing:
            raise ValueError("SDK PR head changed during publication; retry after checking the proposal")
    else:
        if proposal:
            raise ValueError("Existing SDK PR has no source branch; start a new workflow run")
        message = ROOT / "build/publish/sdk-commit-message.txt"
        message.parent.mkdir(parents=True, exist_ok=True)
        message.write_text(
            "chore(sdk): update video dependency SDKs for three platforms\n\n"
            "- Build Windows amd64, Linux amd64 and macOS arm64 from the same source commit\n"
            "- Keep dependency archives separate and verify C and cgo linking\n"
            f"- Record complete file digests and pinned dependency sources from {commit}\n", encoding="utf-8")
        git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-F", str(message))
        # 只推送专用提案分支；目标分支通过 PR 审查合并。
        if remote_head(branch) != commit:
            raise ValueError("Target branch advanced during the build; start a new workflow run")
        git("push", "origin", "HEAD:refs/heads/" + head)
    if proposal:
        report_proposal(proposal["url"])
        return
    body = ROOT / "build/publish/sdk-pr-body.md"
    body.parent.mkdir(parents=True, exist_ok=True)
    body.write_text(
        "Update the OpenH264 and libyuv static SDKs for future Go video adapters.\n\n"
        f"All three SDKs come from source commit `{commit}` and include complete file digests and dependency licenses.\n\n"
        "- Windows amd64: MinGW-w64 GCC.\n"
        "- Linux amd64: GCC.\n"
        "- macOS arm64: Apple Clang, macOS 12 or later.\n"
        "- Validation: native compilation, regular and whole-archive C linking, cgo linking and system dependency checks.\n\n"
        "Validation uses synthetic pixels only. No desktop capture or production Go video API is included.\n",
        encoding="utf-8")
    url = gh("pr", "create", "--repo", repository, "--base", branch, "--head", head,
             "--title", "chore(sdk): update video dependency SDKs for three platforms", "--body-file", str(body))
    report_proposal(url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resolve the SDK source commit or publish the complete SDK set as a PR.")
    parser.add_argument("action", choices=("resolve", "publish"))
    args = parser.parse_args()
    try:
        if args.action == "resolve": resolve()
        else: publish(os.environ["TARGET_BRANCH"], os.environ["SOURCE_COMMIT"])
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"SDK publication stopped: {error}", file=sys.stderr)
        sys.exit(1)
