#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 2단계: Figma 입력 수집(REST)
고유 화면을 자동 감지해 PNG로 전수 렌더하고 capture.json(input_type=figma)을 쓴다.

원칙:
- 토큰은 FIGMA_TOKEN 환경 변수에서만 읽는다. 다른 설정 파일이나 인증 파일은 읽지 않고,
  토큰을 출력하거나 파일에 기록하지 않는다. 읽기 전용(File content: Read-only) 토큰이면 충분하다.
- 화면 분류는 이름이 아니라 치수(너비 최빈 군집)로 추정한다. 최종 검증은 overview 이미지를 직접 보고 한다.
- TEXT 원문은 aux_text로만 저장한다. 지적 근거는 렌더된 이미지에 보이는 것만 쓴다.
- 커넥터가 있으면 from -> to 그래프를 edges로 저장한다.
- Figma에는 아무것도 쓰지 않는다.

사용:
  FIGMA_TOKEN=... python3 figma_capture.py --file-key KEY [--node-id 1:2 | --section-name "이름"] --run ./run
  옵션: --screen-size 390x844 (자동 추정이 틀릴 때) · --scale 2
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

API = "https://api.figma.com/v1"
CONTAINER = {"FRAME", "INSTANCE", "COMPONENT", "GROUP"}


def req(path, tries=3):
    tok = os.environ.get("FIGMA_TOKEN")
    if not tok:
        sys.exit("FIGMA_TOKEN 환경 변수가 없어요. 읽기 전용 개인 액세스 토큰을 환경 변수로 설정하거나 화면을 이미지로 내보내 주세요")
    last = None
    for i in range(tries):
        try:
            r = urllib.request.Request(API + path, headers={"X-Figma-Token": tok})
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403):
                sys.exit(f"Figma API가 {e.code}를 돌려줬어요. 토큰이 만료됐거나 이 파일을 읽을 권한이 없어요")
            if e.code not in (429, 500, 502, 503, 504):
                sys.exit(f"Figma API 오류 {e.code} ({path.split('?')[0]})")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        time.sleep(2 ** i)
    sys.exit(f"Figma API {tries}회 실패({path.split('?')[0]}): {last}. 다시 실행하면 최신 화면을 다시 렌더해요")


def texts(n, acc):
    if n.get("type") == "TEXT":
        ch = (n.get("characters") or "").strip()
        if ch:
            acc.append(ch)
    for c in n.get("children", []) or []:
        texts(c, acc)


def find_target(a):
    """--node-id 우선, 없으면 섹션 목록 안내 또는 --section-name 매칭."""
    if a.node_id:
        d = req(f"/files/{urllib.parse.quote(a.file_key, safe='')}/nodes?ids={urllib.parse.quote(a.node_id)}")
        node = d.get("nodes", {}).get(a.node_id)
        if node:
            return node["document"]
    d2 = req(f"/files/{urllib.parse.quote(a.file_key, safe='')}?depth=2")
    doc = d2["document"]
    secs = [(p.get("name"), c.get("name"), c.get("id"))
            for p in doc.get("children", []) for c in p.get("children", [])
            if c.get("type") == "SECTION"]
    if a.section_name:
        hit = [s for s in secs if s[1] == a.section_name]
        if not hit:
            print("섹션을 못 찾았어요. 가능한 섹션:")
            for p, n, i in secs:
                print(f"  [{p}] {n}  {i}")
            sys.exit(1)
        nid = hit[0][2]
        return req(f"/files/{urllib.parse.quote(a.file_key, safe='')}/nodes?ids={urllib.parse.quote(nid)}")["nodes"][nid]["document"]
    print(f"파일: {doc.get('name')} · 섹션 {len(secs)}개")
    for p, n, i in secs:
        print(f"  [{p}] {n}  {i}")
    print("\n--node-id 또는 --section-name 으로 대상을 지정해주세요.")
    sys.exit(0)


def detect_screens(kids, a):
    """치수로 화면을 추정한다. 같은 문구라도 서로 다른 노드는 유지한다."""
    cand = []
    for c in kids:
        if c.get("type") not in CONTAINER:
            continue
        bb = c.get("absoluteBoundingBox") or {}
        w, h = round(bb.get("width") or 0), round(bb.get("height") or 0)
        if w <= 0 or h <= 0:
            continue
        acc = []
        texts(c, acc)
        cand.append({"node": c, "w": w, "h": h, "x": round(bb.get("x") or 0),
                     "y": round(bb.get("y") or 0), "lines": acc})

    forced = []
    if a.screen_size:
        for part in a.screen_size.lower().split(","):
            m = re.fullmatch(r"\s*(\d+)x(\d+)\s*", part)
            if not m:
                sys.exit(f"--screen-size 형식 오류: {part!r}. WxH 또는 콤마 나열이에요 (예: 390x844,1280x800)")
            forced.append((int(m.group(1)), int(m.group(2))))

    if forced:
        sset = [c for c in cand
                if any(abs(c["w"] - fw) <= max(8, fw * .06) for fw, _fh in forced)]
    elif cand:
        widths = Counter(c["w"] for c in cand)
        modal_w, _ = widths.most_common(1)[0]
        tol = max(8, modal_w * 0.06)
        # 텍스트 없는 프레임(로딩, 빈 상태, 아이콘 화면)도 치수가 맞으면 화면이다
        sset = [c for c in cand
                if abs(c["w"] - modal_w) <= tol and c["h"] >= c["w"] * 0.9]
        if len(sset) < 3:  # 폴백: 면적 상위(가로형 데스크톱 등)
            amax = max((c["w"] * c["h"]) for c in cand)
            sset = [c for c in cand if c["w"] * c["h"] >= amax * 0.5]
    else:
        sset = []

    ids = {id(c) for c in sset}
    screens, seen = [], set()
    for c in cand:
        if id(c) not in ids:
            continue
        nid = c["node"].get("id")
        if nid in seen:
            continue
        seen.add(nid)
        screens.append({"id": c["node"].get("id"), "name": c["node"].get("name", ""),
                        "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"],
                        "aux_text": c["lines"]})
    screens.sort(key=lambda s: (s["y"] // 650, s["x"]))
    guess = forced[0][0] if forced else (Counter(c["w"] for c in cand).most_common(1)[0][0] if cand else None)
    chosen = {s["id"] for s in screens}
    dropped = [{"id": c["node"].get("id"), "name": c["node"].get("name", ""),
                "w": c["w"], "h": c["h"]}
               for c in cand if c["node"].get("id") not in chosen][:60]
    return screens, guess, dropped


def connector_edges(target):
    namemap = {}

    def walk(n):
        ft = []
        texts(n, ft)
        namemap[n.get("id")] = (ft[0] if ft else n.get("name", ""))[:40]
        for c in n.get("children", []) or []:
            walk(c)
    walk(target)
    edges = []

    def scan(n):
        for c in n.get("children", []) or []:
            if c.get("type") == "CONNECTOR":
                st = (c.get("connectorStart") or {}).get("endpointNodeId")
                en = (c.get("connectorEnd") or {}).get("endpointNodeId")
                if st and en:
                    edges.append({"from": namemap.get(st, st), "to": namemap.get(en, en),
                                  "label": (c.get("characters") or "").strip()})
            scan(c)  # 중첩 그룹의 커넥터까지 재귀로
    scan(target)
    return edges


def render(file_key, node_ids, run, scale):
    shots = os.path.join(run, "shots")
    os.makedirs(shots, exist_ok=True)
    out, todo = {}, list(dict.fromkeys(node_ids))
    urls = {}
    for k in range(0, len(todo), 18):
        grp = todo[k:k + 18]
        q = urllib.parse.quote(",".join(grp))
        d = req(f"/images/{urllib.parse.quote(file_key, safe='')}?ids={q}&scale={scale}&format=png")
        urls.update(d.get("images", {}))
        print(f"  rendered {min(k + 18, len(todo))}/{len(todo)}")
    for nid, u in urls.items():
        if not u:
            continue
        p = os.path.join(shots, nid.replace(":", "-") + ".png")
        try:
            urllib.request.urlretrieve(u, p)
            out[nid] = os.path.relpath(p, run).replace(os.sep, "/")
        except Exception as e:
            print("다운로드 실패", nid, e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-key", required=True)
    ap.add_argument("--node-id")
    ap.add_argument("--section-name")
    ap.add_argument("--run", default="./run")
    ap.add_argument("--screen-size")
    ap.add_argument("--scale", type=float, default=2)
    a = ap.parse_args()
    os.makedirs(a.run, exist_ok=True)

    target = find_target(a)
    screens, guess, dropped = detect_screens(target.get("children", []) or [], a)
    edges = connector_edges(target)

    # 개요 이미지와 고유 화면을 현재 원본에서 항상 다시 렌더한다
    ov = render(a.file_key, [target.get("id")], a.run, 0.25)
    shots = render(a.file_key, [s["id"] for s in screens], a.run, a.scale)
    for s in screens:
        s["shot"] = shots.get(s["id"])

    cap = {
        "input_type": "figma",
        "source": {"file_key": a.file_key, "node_id": target.get("id"), "name": target.get("name")},
        "viewport": f"{guess}w(추정)" if guess else None,
        "overview": ov.get(target.get("id")),
        "screens": screens,
        "edges": edges,
        "candidates_dropped": dropped,  # 자동 감지에서 탈락한 후보. overview와 대조해 교정할 때 쓴다
        "_note": "화면 자동 감지는 추정이에요. overview와 shots를 직접 보고 검증하세요. "
                 "aux_text는 보조 근거일 뿐, 지적은 이미지에 보이는 것만 근거로 해요.",
    }
    p = os.path.join(a.run, "capture.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cap, fh, ensure_ascii=False, indent=2)
    print(f"WROTE {p} · 고유 화면 {len(screens)} (렌더 {len(shots)}) · 엣지 {len(edges)} · 너비≈{guess}")
    if len(shots) < len(screens):
        print(f"렌더 누락 {len(screens) - len(shots)}건. shot이 없는 화면은 검토 대상에서 빼고 그 사실을 보고하세요")


if __name__ == "__main__":
    main()
