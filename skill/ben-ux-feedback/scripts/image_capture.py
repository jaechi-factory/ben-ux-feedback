#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 2단계: 이미지 입력 수집
이미지 파일이나 폴더를 실행 폴더의 shots/ 로 복사하고 capture.json(input_type=image)을 쓴다.

사용:
  python3 image_capture.py <이미지 파일|폴더> --run ./runs/my-app
폴더는 바로 아래의 이미지(png, jpg, jpeg, webp, gif)만 읽고 자연 정렬 순서를 화면 순서로 쓴다.
같은 run 폴더에 다시 실행하면 이번 입력에 없는 옛 shots 이미지는 지운다(capture.json과 어긋나지 않게).
capture.json에는 절대 경로를 적지 않는다(파일 또는 폴더 이름과 개수만 적는다).
끝나면 shot 상대 경로를 한 줄씩 출력한다(다음 턴에 capture.json을 다시 읽지 않고 바로 열 수 있게).
"""
import argparse
import json
import os
import re
import shutil
import sys

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def slugify(stem):
    s = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", stem).strip("-_").lower()
    return s


def collect(source):
    """(kind, 이미지 파일 경로 목록)을 돌려준다. 이미지가 없으면 ValueError."""
    src = os.path.expanduser(source)
    if os.path.isdir(src):
        names = sorted((n for n in os.listdir(src)
                        if os.path.splitext(n)[1].lower() in IMAGE_EXT
                        and os.path.isfile(os.path.join(src, n))), key=natural_key)
        if not names:
            raise ValueError("폴더에 이미지가 없어요 (지원: png, jpg, jpeg, webp, gif)")
        return "folder", [os.path.join(src, n) for n in names]
    if os.path.isfile(src):
        if os.path.splitext(src)[1].lower() not in IMAGE_EXT:
            raise ValueError("이미지 파일이 아니에요 (지원: png, jpg, jpeg, webp, gif)")
        return "file", [src]
    raise ValueError("경로를 찾을 수 없어요")


def clean_stale(shots_dir, keep):
    """이번 실행이 만든 파일(keep)이 아닌 옛 이미지를 지우고 지운 이름 목록을 돌려준다."""
    removed = []
    for n in sorted(os.listdir(shots_dir)):
        p = os.path.join(shots_dir, n)
        if n not in keep and os.path.isfile(p) and os.path.splitext(n)[1].lower() in IMAGE_EXT:
            os.remove(p)
            removed.append(n)
    return removed


def capture(source, run):
    kind, files = collect(source)
    shots_dir = os.path.join(run, "shots")
    os.makedirs(shots_dir, exist_ok=True)

    screens, used = [], set()
    for n, path in enumerate(files, 1):
        stem, ext = os.path.splitext(os.path.basename(path))
        base = slugify(stem) or f"screen-{n}"
        sid, k = base, 2
        while sid in used:
            sid = f"{base}-{k}"
            k += 1
        used.add(sid)
        dest = os.path.join(shots_dir, sid + ext.lower())
        if not (os.path.exists(dest) and os.path.samefile(path, dest)):
            shutil.copyfile(path, dest)
        screens.append({"id": sid, "name": stem, "shot": f"shots/{sid}{ext.lower()}"})

    removed = clean_stale(shots_dir, {os.path.basename(s["shot"]) for s in screens})
    if removed:
        print(f"이전 실행의 옛 shot {len(removed)}개를 지웠어요: {', '.join(removed[:5])}")

    src_abs = os.path.abspath(os.path.expanduser(source))
    cap = {
        "input_type": "image",
        "source": {"kind": kind, "name": os.path.basename(src_abs.rstrip(os.sep)), "count": len(screens)},
        "viewport": None,
        "screens": screens,
        "edges": [],
    }
    with open(os.path.join(run, "capture.json"), "w", encoding="utf-8") as fh:
        json.dump(cap, fh, ensure_ascii=False, indent=2)
    return cap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="이미지 파일 또는 폴더")
    ap.add_argument("--run", default="./run")
    a = ap.parse_args()
    try:
        cap = capture(a.source, a.run)
    except ValueError as e:
        sys.exit(str(e))
    print(f"WROTE {os.path.join(a.run, 'capture.json')} · 화면 {len(cap['screens'])}")
    for s in cap["screens"]:
        print(f"  {s['shot']}")


if __name__ == "__main__":
    main()
