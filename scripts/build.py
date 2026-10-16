#!/usr/bin/env python3
"""정본(skill/ben-ux-feedback/)에서 생성물을 만들어요.

생성물:
  .claude/skills/ben-ux-feedback/   Claude Code 프로젝트 범위 복사본
  .agents/skills/ben-ux-feedback/   Codex 프로젝트 범위 복사본
  chat/                             채팅형 LLM용 파일
  build-manifest.json               생성물 경로와 SHA-256

사용:
  python3 scripts/build.py          생성물을 만들고 매니페스트를 갱신해요
  python3 scripts/build.py --check  생성물이 정본과 같은지만 검사해요(다르면 exit 1)

생성물은 직접 고치지 않아요. 정본이나 이 스크립트, chat_templates.py를 고친 뒤 다시 실행해요.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chat_templates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "ben-ux-feedback"
SRC = ROOT / "skill" / SKILL_NAME
COPY_DIRS = [f".claude/skills/{SKILL_NAME}", f".agents/skills/{SKILL_NAME}"]
CHAT_DIR = "chat"
MANIFEST = "build-manifest.json"
GENERATED_DIRS = COPY_DIRS + [CHAT_DIR]

SKIP_DIRS = {"__pycache__"}
SKIP_NAMES = {".DS_Store"}
SKIP_SUFFIXES = (".pyc",)
# 예시 run에서 다시 만들 수 있는 리포트는 복사하지 않아요.
SKIP_RELS = {"examples/sample-run/report.html", "examples/sample-run/report.md",
             "examples/sample-compare/compare.html"}

# 채팅 지식 파일 안에서 references/ 경로를 채팅 파일 이름으로 바꿔요.
CHAT_REF = {
    "guideline": "KNOWLEDGE.md",
    "procedure": "KNOWLEDGE.md",
    "writing": "KNOWLEDGE.md",
    "personas": "KNOWLEDGE.md",
    "output-contract": "KNOWLEDGE.md",
    "appendix": "KNOWLEDGE_APPENDIX.md",
    "cases": "KNOWLEDGE_APPENDIX.md",
}
MD_OUTPUT_HEADING = "## 마크다운 출력 형식"


def collect_source():
    """정본 파일을 {상대 경로(posix): bytes}로 모아요. 이름순이라 결정적이에요."""
    if not SRC.is_dir():
        raise SystemExit(f"정본 폴더가 없어요: {SRC}")
    files = {}
    for path in sorted(SRC.rglob("*")):
        rel_parts = path.relative_to(SRC).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if path.name in SKIP_NAMES or path.name.endswith(SKIP_SUFFIXES):
            continue
        if path.is_symlink():
            raise SystemExit(f"정본에 심볼릭 링크가 있어요: {path}")
        if not path.is_file():
            continue
        rel = "/".join(rel_parts)
        if rel in SKIP_RELS:
            continue
        files[rel] = path.read_bytes()
    if "SKILL.md" not in files:
        raise SystemExit("정본에 SKILL.md가 없어요")
    return files


def read_ref(source, name):
    return source[f"references/{name}.md"].decode("utf-8").strip("\n")


def retarget(text):
    def sub(match):
        return CHAT_REF.get(match.group(1), match.group(0))

    return re.sub(r"references/([a-z\-]+)\.md", sub, text)


def markdown_output_part(contract):
    idx = contract.find(MD_OUTPUT_HEADING)
    if idx < 0:
        raise SystemExit("output-contract.md에서 마크다운 출력 형식 절을 못 찾았어요")
    return contract[idx:]


def join_docs(title, intro, parts):
    chunks = [f"<!-- 생성 파일이에요. 직접 고치지 말고 정본을 고친 뒤 python3 scripts/build.py를 실행해요. -->\n# {title}\n\n{intro}"]
    for label, body in parts:
        chunks.append(f"<!-- 출처: {label} -->\n\n{retarget(body)}")
    return ("\n\n---\n\n".join(chunks) + "\n").encode("utf-8")


def build_chat(source):
    knowledge = join_docs(
        "ben-ux-feedback 지식 파일",
        "채팅형 LLM의 프로젝트 파일로 올려요. 아래 순서대로 가이드라인, 판정 절차, 문구 판정, 가상 UT 페르소나, 마크다운 출력 형식이 들어 있어요. 스크립트 실행 안내가 나와도 채팅에서는 건너뛰고 손으로 같은 결과를 만들어요.",
        [
            ("references/guideline.md", read_ref(source, "guideline")),
            ("references/procedure.md", read_ref(source, "procedure")),
            ("references/writing.md", read_ref(source, "writing")),
            ("references/personas.md", read_ref(source, "personas")),
            ("references/output-contract.md (마크다운 출력 형식 절)", markdown_output_part(read_ref(source, "output-contract"))),
        ],
    )
    appendix = join_docs(
        "ben-ux-feedback 부록 지식 파일",
        "원칙별 상세 규칙과 사례예요. 길어서 올리기 어려우면 빼도 돼요. 필요한 원칙이나 사례 번호만 찾아 읽어요.",
        [
            ("references/appendix.md", read_ref(source, "appendix")),
            ("references/cases.md", read_ref(source, "cases")),
        ],
    )
    return {
        f"{CHAT_DIR}/00_START_HERE.md": chat_templates.START_HERE.encode("utf-8"),
        f"{CHAT_DIR}/PROJECT_INSTRUCTIONS.md": chat_templates.PROJECT_INSTRUCTIONS.encode("utf-8"),
        f"{CHAT_DIR}/KNOWLEDGE.md": knowledge,
        f"{CHAT_DIR}/KNOWLEDGE_APPENDIX.md": appendix,
        f"{CHAT_DIR}/REQUEST_EXAMPLES.md": chat_templates.REQUEST_EXAMPLES.encode("utf-8"),
    }


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_version():
    path = ROOT / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else "unknown"


def expected_outputs():
    """만들어야 할 모든 파일을 {저장소 기준 상대 경로: bytes}로 돌려줘요(매니페스트 포함)."""
    source = collect_source()
    outputs = {}
    for dest in COPY_DIRS:
        for rel, data in source.items():
            outputs[f"{dest}/{rel}"] = data
    outputs.update(build_chat(source))
    manifest = {
        "version": read_version(),
        "generator": "scripts/build.py",
        "source": f"skill/{SKILL_NAME}",
        "files": {path: sha256(data) for path, data in sorted(outputs.items())},
    }
    outputs[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return outputs


def actual_outputs():
    """디스크에 있는 생성물을 같은 모양으로 읽어요."""
    found = {}
    for d in GENERATED_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.is_symlink():
                parts = path.relative_to(ROOT).parts
                if any(part in SKIP_DIRS for part in parts) or path.name in SKIP_NAMES or path.name.endswith(SKIP_SUFFIXES):
                    continue
                found["/".join(parts)] = path.read_bytes()
    manifest = ROOT / MANIFEST
    if manifest.is_file():
        found[MANIFEST] = manifest.read_bytes()
    return found


def check():
    expected = expected_outputs()
    actual = actual_outputs()
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(p for p in set(expected) & set(actual) if expected[p] != actual[p])
    if not (missing or extra or changed):
        print(f"OK: 생성물 {len(expected)}개가 정본과 같아요")
        return 0
    for label, items in (("없는 파일", missing), ("정본에 없는 파일", extra), ("내용이 다른 파일", changed)):
        for item in items:
            print(f"{label}: {item}")
    print("python3 scripts/build.py 로 다시 만들어요")
    return 1


def safe_remove(rel):
    target = ROOT / rel
    if target.is_symlink():
        target.unlink()
    elif target.is_dir():
        if ROOT not in target.resolve().parents:
            raise SystemExit(f"저장소 밖 경로는 지우지 않아요: {target}")
        shutil.rmtree(target)


def build():
    outputs = expected_outputs()
    for d in GENERATED_DIRS:
        safe_remove(d)
    for rel, data in outputs.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f"생성물 {len(outputs) - 1}개와 {MANIFEST}를 만들었어요")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="정본에서 생성물을 만들어요")
    parser.add_argument("--check", action="store_true", help="생성물이 정본과 같은지만 검사해요")
    args = parser.parse_args(argv)
    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())
