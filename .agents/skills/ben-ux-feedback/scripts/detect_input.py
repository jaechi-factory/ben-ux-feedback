#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 1단계: 입력 판별
이미지 파일, 이미지 폴더, Figma 링크, http(s) 주소를 받아 종류를 JSON 한 줄로 출력한다.

사용:
  python3 detect_input.py ./shots
  -> {"type": "image", "kind": "folder", "path": "...", "count": 3, "files": [...]}
  python3 detect_input.py "https://www.figma.com/design/KEY/name?node-id=1-2"
  -> {"type": "figma", "file_key": "KEY", "node_id": "1:2"}
  python3 detect_input.py "http://localhost:3000/checkout"
  -> {"type": "live", "url": "http://localhost:3000/checkout", "localhost": true}
알 수 없는 입력이면 {"type": "unknown", "reason": "..."} 를 출력하고 exit 1.
"""
import json
import os
import re
import sys
import urllib.parse

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")


def natural_key(name):
    """2가 10보다 앞에 오는 자연 정렬 키."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_images(folder):
    """폴더 바로 아래의 이미지 파일 이름을 자연 정렬로 돌려준다."""
    names = [n for n in os.listdir(folder)
             if os.path.splitext(n)[1].lower() in IMAGE_EXT
             and os.path.isfile(os.path.join(folder, n))]
    return sorted(names, key=natural_key)


def unknown(reason):
    return {"type": "unknown", "reason": reason}


def detect_url(url):
    if not re.match(r"^https?://", url, re.I):
        local = re.match(r"^(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[^/:?#]+\.local)(?::\d+)?(?:[/?#]|$)", url, re.I)
        url = ("http://" if local else "https://") + url
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()

    if host == "figma.com" or host.endswith(".figma.com"):
        m = re.search(r"/(?:file|design|board|proto|slides)/([A-Za-z0-9]+)", p.path)
        # 브랜치 주소(/design/KEY/branch/BRANCHKEY/...)는 브랜치 키가 실제 파일이다
        mb = re.search(r"/branch/([A-Za-z0-9]+)", p.path)
        if mb:
            m = mb
        node = (urllib.parse.parse_qs(p.query).get("node-id") or [None])[0]
        return {
            "type": "figma",
            "file_key": m.group(1) if m else None,
            "node_id": node.replace("-", ":") if node else None,
        }

    return {
        "type": "live",
        "url": url,
        "localhost": host in LOCAL_HOSTS or host.endswith(".local"),
    }


def detect(arg):
    s = (arg or "").strip()
    if not s:
        return unknown("빈 입력이에요. 이미지 파일, 폴더, Figma 링크, 주소 중 하나를 주세요")
    if re.match(r"^https?://", s, re.I):
        return detect_url(s)

    p = os.path.expanduser(s)
    if os.path.isdir(p):
        files = list_images(p)
        if not files:
            return unknown("폴더에 이미지가 없어요 (지원: png, jpg, jpeg, webp, gif)")
        return {"type": "image", "kind": "folder", "path": os.path.abspath(p),
                "count": len(files), "files": files}
    if os.path.isfile(p):
        if os.path.splitext(p)[1].lower() not in IMAGE_EXT:
            return unknown("이미지 파일이 아니에요 (지원: png, jpg, jpeg, webp, gif)")
        return {"type": "image", "kind": "file", "path": os.path.abspath(p),
                "count": 1, "files": [os.path.basename(p)]}

    # 존재하지 않는 입력: 경로처럼 보이면 경로 오류, 주소처럼 보이면 주소
    looks_like_path = (os.path.splitext(s)[1].lower() in IMAGE_EXT
                       or s.startswith(("/", "./", "../", "~")))
    if looks_like_path:
        return unknown("경로를 찾을 수 없어요")
    host_like = re.match(
        r"^(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?::\d+)?(?:[/?#]|$)", s)
    if host_like:
        return detect_url(s)
    return unknown("이미지 경로도 주소도 아니에요")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용: detect_input.py <이미지 파일|폴더|Figma 링크|주소>")
    result = detect(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
    if result["type"] == "unknown":
        sys.exit(1)
