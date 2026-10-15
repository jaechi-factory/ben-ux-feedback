#!/usr/bin/env python3
"""ben-ux-feedback 스킬을 Claude Code나 Codex 폴더에 설치해요.

기본은 계획만 출력해요(dry-run). --apply가 있어야 복사해요.

  python3 scripts/install.py                                  사용자 범위, 둘 다, 계획만
  python3 scripts/install.py --target claude --apply          ~/.claude/skills/ben-ux-feedback/
  python3 scripts/install.py --target codex --apply           ~/.agents/skills/ben-ux-feedback/
  python3 scripts/install.py --scope project --project PATH --apply
                                                              PATH/.claude/skills/, PATH/.agents/skills/
  python3 scripts/install.py --apply --replace-with-backup    이미 있으면 백업 폴더로 옮기고 교체

이미 있는 폴더는 --replace-with-backup 없이는 덮어쓰지 않아요.
백업은 skills 폴더 안의 .ben-ux-feedback-backups/<시각>/ 에 둬요.
홈 폴더, 루트 같은 위험한 경로와 심볼릭 링크는 거절해요.
"""
import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

SKILL_NAME = build.SKILL_NAME
BACKUP_DIR = ".ben-ux-feedback-backups"
SUBDIRS = {"claude": ".claude/skills", "codex": ".agents/skills"}
SYSTEM_DIRS = {
    "/bin", "/sbin", "/usr", "/etc", "/var", "/opt", "/lib", "/lib64", "/boot", "/dev",
    "/proc", "/sys", "/tmp", "/private", "/System", "/Library", "/Applications", "/Users", "/home", "/root",
}


class InstallError(Exception):
    pass


def danger_reason(project):
    """프로젝트 경로가 위험하면 이유를, 괜찮으면 None을 돌려줘요."""
    real = Path(os.path.realpath(project))
    home = Path(os.path.realpath(Path.home()))
    if real == Path(real.anchor):
        return "루트 폴더예요"
    if real == home:
        return "홈 폴더예요. 프로젝트 폴더를 따로 정해요"
    if real in home.parents:
        return "홈 폴더의 상위 폴더예요"
    if str(real) in SYSTEM_DIRS:
        return "시스템 폴더예요"
    if real == build.ROOT:
        return "이 저장소예요. 이 저장소의 .claude, .agents는 build.py가 관리해요"
    return None


def symlink_reason(base, dest, check_base):
    """base에서 dest까지 심볼릭 링크가 있으면 그 경로를 돌려줘요."""
    if check_base and base.is_symlink():
        return str(base)
    current = base
    for part in dest.relative_to(base).parts:
        current = current / part
        if current.is_symlink():
            return str(current)
    return None


def resolve_destinations(target, scope, project):
    names = ["claude", "codex"] if target == "both" else [target]
    if scope == "user":
        base, check_base = Path.home(), False
    else:
        if not project:
            raise InstallError("--scope project는 --project PATH가 필요해요")
        base = Path(os.path.abspath(os.path.expanduser(project)))
        check_base = True
        if not base.is_dir():
            raise InstallError(f"프로젝트 폴더가 없어요: {base}")
        reason = danger_reason(base)
        if reason:
            raise InstallError(f"위험한 경로라서 거절해요: {base} ({reason})")
    items = []
    for name in names:
        dest = base / SUBDIRS[name] / SKILL_NAME
        link = symlink_reason(base, dest, check_base)
        if link:
            raise InstallError(f"심볼릭 링크가 있어서 거절해요: {link}")
        items.append((name, dest))
    return items


def plan_one(name, dest, replace):
    if dest.is_symlink():
        return {"name": name, "dest": dest, "action": "refuse", "note": "심볼릭 링크라서 거절해요"}
    if not dest.exists():
        return {"name": name, "dest": dest, "action": "install", "note": "새로 설치해요"}
    if not replace:
        return {"name": name, "dest": dest, "action": "refuse",
                "note": "이미 있어서 덮지 않아요. 바꾸려면 --replace-with-backup을 붙여요"}
    return {"name": name, "dest": dest, "action": "replace", "note": f"기존 폴더를 {BACKUP_DIR}/ 로 옮기고 교체해요"}


def backup_path(dest):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = dest.parent / BACKUP_DIR
    candidate = root / stamp / dest.name
    n = 1
    while candidate.exists():
        n += 1
        candidate = root / f"{stamp}-{n}" / dest.name
    return candidate


def apply_one(item, files):
    dest = item["dest"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".ben-ux-feedback-tmp-", dir=dest.parent))
    try:
        for rel, data in files.items():
            path = tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.chmod(tmp, 0o755)
        backup = None
        if item["action"] == "replace":
            backup = backup_path(dest)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(backup))
        tmp.rename(dest)
        return backup
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="ben-ux-feedback 스킬 설치 도우미(기본은 계획만 출력)")
    parser.add_argument("--target", choices=["claude", "codex", "both"], default="both")
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--project", help="--scope project일 때 대상 프로젝트 폴더")
    parser.add_argument("--apply", action="store_true", help="실제로 복사해요(없으면 계획만 출력)")
    parser.add_argument("--replace-with-backup", action="store_true", help="이미 있으면 백업 폴더로 옮기고 교체해요")
    args = parser.parse_args(argv)

    try:
        destinations = resolve_destinations(args.target, args.scope, args.project)
    except InstallError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    files = build.collect_source()
    plans = [plan_one(n, d, args.replace_with_backup) for n, d in destinations]
    mode = "설치" if args.apply else "계획만 출력(dry-run)"
    print(f"{mode}: 파일 {len(files)}개")
    for p in plans:
        print(f"- {p['name']}: {p['dest']}  [{p['note']}]")

    refused = [p for p in plans if p["action"] == "refuse"]
    if refused:
        print("거절된 대상이 있어서 아무것도 복사하지 않아요.", file=sys.stderr)
        return 1
    if not args.apply:
        print("실제로 복사하려면 --apply를 붙여요. 아무것도 쓰지 않았어요.")
        return 0

    for p in plans:
        backup = apply_one(p, files)
        print(f"설치했어요: {p['dest']}")
        if backup:
            print(f"  이전 폴더는 여기에 있어요: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
