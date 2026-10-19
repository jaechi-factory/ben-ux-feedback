#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 5단계: 리포트 빌드
RUN/review.json(과 선택 ut)을 읽어 단일 HTML(이미지 내장)과 마크다운을 만든다.
review.json은 바꾸지 않는다. 외부 네트워크 요청이 없고 표준 라이브러리만 쓴다.

사용: python3 build_report.py --run ./run [--format html|md|both] [--out 경로.html]
결과: RUN/report.html (또는 --out 경로), RUN/report.md
"""
import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import BRIEF_FIELDS  # noqa: E402  브리프 항목 이름은 검증기와 같은 것을 쓴다

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}
SEV_ORDER = {"심각": 0, "중간": 1, "낮음": 2}
SEV_VIEW = {"심각": ("sev-high", "개선 필요"), "중간": ("sev-mid", "개선 권장"), "낮음": ("sev-low", "사소한 의견")}
LV_CLASS = {"쉬움": "lv-ok", "보통": "lv-mid", "막힘": "lv-block"}
AXES = (("device", "조작"), ("design", "화면 이해"), ("writing", "문구 이해"))
LEVEL_WORD = {"상": "능숙", "중": "보통", "하": "서툼"}
# 제외 규칙 코드는 메이커가 읽을 말로 바꿔 보여 준다(모르는 값은 적힌 그대로)
EXCLUSION_WORD = {"curly-braces": "중괄호 {} 표기는 실제 값이 들어갈 자리로 봤어요",
                  "dummy-amount-mismatch": "화면마다 다른 더미 금액은 보지 않았어요"}
# '화면'은 모든 지적의 기본값이라 따로 표시하지 않는다
LENS_LABEL = {"문구": "문구", "흐름": "화면 사이 흐름", "접근성": "접근성"}
INPUT_LABEL = {"image": "이미지", "figma": "Figma", "live": "라이브 URL"}
WRITING_LABEL = {"ben-ux-writing": "문구는 ben-ux-writing 기준으로 봤어요",
                 "fallback": "문구는 기본 점검만 했어요(ben-ux-writing 미설치)"}
SIZE_WARN_MB = 20
TOP_MAX = 3
# 외부 요청이 없다는 것을 브라우저가 강제하게 한다(이미지는 data URI, 스타일과 스크립트는 인라인)
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
HERE = os.path.dirname(os.path.abspath(__file__))
AGE_KEYS = {"청년": "youth", "중년": "mid", "노년": "senior"}
AGE_ALT = {"청년": "청년 사용자", "중년": "중년 사용자", "노년": "노년 사용자"}
LENS_ORDER = {"화면": 0, "흐름": 1, "문구": 2, "접근성": 3}
DEFAULT_GUIDELINE = os.path.join(HERE, "..", "references", "guideline.md")


# ── 공통 도우미 ──

def t(v):
    return v if isinstance(v, str) else ""


def esc(v):
    return html.escape(t(v), quote=True)


def dicts(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def strs(v):
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def label_of(table, v):
    """라벨 표에서 찾고, 없으면 값 자체(문자열일 때)나 빈 문자열."""
    if isinstance(v, str):
        return table.get(v, v)
    return ""


def slug(s):
    """앵커용 안전 ID. 영숫자, 하이픈, 밑줄만 남기고 바뀐 경우 해시를 붙여 충돌을 피한다."""
    s = t(s)
    out = re.sub(r"[^A-Za-z0-9_-]", "-", s)
    if out != s or not out:
        out += "-" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:6]
    return out


def safe_shot(run, rel):
    """shot은 RUN/shots 안의 이미지 파일만 허용한다. 절대 경로, .. 탈출, 심볼릭 링크 탈출은 None."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    try:
        base = os.path.realpath(os.path.join(run, "shots"))
        full = os.path.realpath(os.path.join(os.path.realpath(run), rel))
        if not full.startswith(base + os.sep):
            return None
        if os.path.splitext(full)[1].lower() not in MIME or not os.path.isfile(full):
            return None
    except (ValueError, OSError):
        return None
    return full


def data_uri(path):
    mime = MIME[os.path.splitext(path)[1].lower()]
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode("ascii")


def pin_box(f):
    """pin {x, y[, w, h]}: 화면 이미지 안 위치를 0~1 비율로. w, h가 있으면 (x, y)는 상자의 왼쪽 위이고,
    없으면 (x, y)는 점이다. 값이 잘못됐으면 None, w·h가 한쪽만 있거나 0이면 점으로 본다."""
    p = f.get("pin")
    if not isinstance(p, dict):
        return None
    out = []
    for k in ("x", "y", "w", "h"):
        v = p.get(k)
        if v is None and k in ("w", "h"):
            out.append(None)
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        out.append(min(max(float(v), 0.0), 1.0))
    if out[2] is None or out[3] is None or out[2] == 0 or out[3] == 0:
        out[2] = out[3] = None
    else:   # 상자가 이미지 밖으로 나가지 않게 자른다
        out[2] = round(min(out[2], 1.0 - out[0]), 6)
        out[3] = round(min(out[3], 1.0 - out[1]), 6)
        if out[2] <= 0 or out[3] <= 0:
            out[2] = out[3] = None
    return tuple(out)


def pin_point(box):
    """썸네일 번호 핀을 찍을 점. 상자면 왼쪽 변의 가운데(화면 글자를 가리지 않게), 점이면 그 점.
    썸네일 가장자리에서 잘리지 않게 핀 반지름(약 6%)만큼 안쪽으로 둔다."""
    x, y, w, h = box
    px, py = (x, y + h / 2) if w else (x, y)
    return (round(min(max(px, 0.06), 0.94), 6), round(min(max(py, 0.04), 0.96), 6))


def sev_key(f):
    return SEV_ORDER.get(f.get("severity"), 3)


def order_key(f):
    """심각도 → 렌즈(화면, 흐름, 문구, 접근성) 순. 비슷한 지적이 흩어지지 않게 렌즈로 한 번 더 모은다."""
    return (sev_key(f), LENS_ORDER.get(f.get("lens"), 9))


def load_principle_questions(path=None):
    """guideline.md 4절 QA 표에서 {원칙 이름: 검토 질문 한 줄}을 읽는다. 리뷰용이라 3절보다 쉬운 말이다.
    파일이 없거나 깨져도 빈 표를 돌려준다."""
    try:
        with open(path or DEFAULT_GUIDELINE, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    sec4 = re.search(r"^## 4\..*?(?=^## 5\.|\Z)", text, re.M | re.S)
    out = {}
    for mo in re.finditer(r"^\|\s*([A-Za-z][^|]*?)\s*\|\s*([^|]*\?)\s*\|", sec4.group(0) if sec4 else "", re.M):
        out.setdefault(mo.group(1).strip(), mo.group(2).strip())
    return out


def level_word(v):
    return LEVEL_WORD.get(t(v), t(v))


def persona_line(p):
    """누구의 말인지 한 줄로: 노년 · 휴대폰 조작 서툼 · 앱 이해 보통
    사람의 능력은 '휴대폰 조작·앱 이해', 화면마다의 반응은 '조작·화면 이해·문구 이해'로 부른다."""
    return (f'{t(p.get("age_group"))} · 휴대폰 조작 {level_word(p.get("device_level"))} · '
            f'앱 이해 {level_word(p.get("ux_level"))}')


def ask(q):
    """가이드라인 검토 질문(~는가?)을 리포트 말투(~나요?)로."""
    q = t(q)
    return re.sub(r"인가\?$", "인가요?", re.sub(r"[는은]가\?$", "나요?", q))


def top_findings(m):
    """첫 화면에 올릴 '먼저 고칠 것'. summary.top 순서를 지키되 심각을 앞으로, 최대 TOP_MAX개.
    summary.top이 비었으면 전체 지적에서 심각도 순으로 고른다."""
    picked = [m.finding_by_id[x] for x in strs(m.summary.get("top")) if x in m.finding_by_id]
    if not picked:
        picked = list(m.findings)
    seen, uniq = set(), []
    for f in picked:
        if id(f) not in seen:
            seen.add(id(f))
            uniq.append(f)
    uniq.sort(key=sev_key)   # 안정 정렬이라 같은 심각도끼리는 summary.top 순서가 남는다
    return uniq[:TOP_MAX]


class Model:
    """review.json과 capture.json을 리포트용으로 정리한 읽기 전용 묶음."""

    def __init__(self, rev, cap, questions=None):
        self.questions = questions if isinstance(questions, dict) else load_principle_questions()
        self.rev = rev if isinstance(rev, dict) else {}
        self.cap = cap if isinstance(cap, dict) else {}
        self.run = self.rev.get("run") if isinstance(self.rev.get("run"), dict) else {}
        self.summary = self.rev.get("summary") if isinstance(self.rev.get("summary"), dict) else {}
        self.screens = dicts(self.rev.get("screens"))
        self.findings = dicts(self.rev.get("findings"))
        self.strengths = dicts(self.rev.get("strengths"))
        self.checks = dicts(self.rev.get("checks_needed"))
        self.screen_by_id = {t(s.get("id")): s for s in self.screens}
        self.finding_by_id = {t(f.get("id")): f for f in self.findings}
        # 화면을 특정한 것은 지적(흐름 포함)·잘 된 점·반응을 모두 그 화면 아래에 모은다. 화면이 없는 것만 따로 둔다
        def in_screen(x):
            return isinstance(x.get("screen_id"), str) and x["screen_id"] in self.screen_by_id

        self.strengths_by_screen = {}
        for st in self.strengths:
            if in_screen(st):
                self.strengths_by_screen.setdefault(st["screen_id"], []).append(st)
        self.loose_strengths = [st for st in self.strengths if not in_screen(st)]
        self.flow = [f for f in self.findings if not in_screen(f)]
        self.flow.sort(key=order_key)
        self.by_screen = {}
        for f in self.findings:
            if in_screen(f):
                self.by_screen.setdefault(f["screen_id"], []).append(f)
        for lst in self.by_screen.values():
            lst.sort(key=order_key)
        self.ut = self._ut()

    def _ut(self):
        ut = self.rev.get("ut")
        if not isinstance(ut, dict):
            return None
        personas = [p for p in dicts(ut.get("personas")) if t(p.get("id"))]
        if not personas:
            return None
        walks = {t(w.get("persona_id")): w for w in dicts(ut.get("walks"))}
        steps = {}   # (persona_id, screen_id) -> step
        for pid, w in walks.items():
            for st in dicts(w.get("steps")):
                steps.setdefault((pid, t(st.get("screen_id"))), st)
        easy = set()   # (persona_id, screen_id) 세 축이 모두 쉬움이라 step을 생략한 화면
        for pid, w in walks.items():
            for sid in strs(w.get("easy_screens")):
                if (pid, sid) not in steps:
                    easy.add((pid, sid))
        by_finding = {}   # finding id -> [persona id]
        known = {t(p.get("id")) for p in personas}
        for pid, w in walks.items():   # 같은 화면을 다시 지나간 반응까지 모두 본다
            for st in dicts(w.get("steps")):
                for fid in strs(st.get("finding_ids")):
                    if pid not in by_finding.setdefault(fid, []):
                        by_finding[fid].append(pid)
        for f in self.findings:
            for pid in strs(f.get("from_ut")):
                if pid in known and pid not in by_finding.setdefault(t(f.get("id")), []):
                    by_finding[t(f.get("id"))].append(pid)
        step_for = {}   # (finding id, persona id) -> 그 지적을 이은 첫 step
        for pid, w in walks.items():
            for st in dicts(w.get("steps")):
                for fid in strs(st.get("finding_ids")):
                    step_for.setdefault((fid, pid), st)
        return {"personas": personas, "walks": walks, "steps": steps, "easy": easy,
                "by_finding": by_finding, "step_for": step_for,
                "persona_by_id": {t(p["id"]): p for p in personas}}

    def screen_has_content(self, sid):
        walked = bool(self.ut) and any((t(p["id"]), sid) in self.ut["steps"] or (t(p["id"]), sid) in self.ut["easy"]
                                       for p in self.ut["personas"])
        return bool(self.by_screen.get(sid) or self.strengths_by_screen.get(sid) or walked)

    def screen_name(self, sid):
        s = self.screen_by_id.get(sid)
        return t(s.get("name")) if s and t(s.get("name")) else t(sid)

    def counts(self):
        return (len(self.screens), len(self.findings),
                sum(1 for f in self.findings if f.get("severity") == "심각"))


# ── HTML ──

CSS_VARS = """
:root{
--grey-50:#F9FAFB;--grey-100:#F2F4F6;--grey-200:#E5E8EB;--grey-300:#D1D6DB;--grey-400:#B0B8C1;--grey-500:#8B95A1;--grey-600:#6B7684;--grey-700:#4E5968;--grey-800:#333D4B;--grey-900:#191F28;
--blue-50:#E8F3FF;--blue-500:#3182F6;--blue-600:#2272EB;--blue-700:#1B64DA;--blue-800:#1957C2;
--red-50:#FFEEEE;--red-500:#F04452;--red-800:#BC1B2A;
--orange-500:#FE9800;
--yellow-50:#FFF9E7;--yellow-200:#FFE69B;--yellow-600:#FFB331;
--teal-50:#EDF8F8;--teal-700:#0C8585;
--green-50:#F0FAF6;--green-500:#03B26C;--green-900:#027648;
--accent:var(--blue-700);--accent-soft:var(--blue-50);--focus:var(--blue-500);
--font-sans:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
--t1:30px;--t2:26px;--t3:22px;--t4:20px;--t5:17px;
--lh-title:1.5;--lh-body:1.65;
}
"""

# 가독성 기준(BDS·HTML 대원칙): 글자는 모두 t5(17px) 이상이고 위계는 크기(t1 30 → t2 26 → t3 22 → t4 20)와 굵기·색으로 나눈다.
# 여백은 4배수이고 그룹 사이(섹션 72, 화면 64, 카드 24, 카드 안 블록 32)를 그룹 안(라벨→본문 8, 문단 12)보다 크게 둔다.
# 링크·핀 같이 글자를 얹는 액센트는 흰 바탕 대비를 위해 blue-700을 쓴다(blue-500은 초점 표시에만).
CSS_BASE = """
*{box-sizing:border-box;margin:0}
html{-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
body{background:#FFFFFF;color:var(--grey-800);font-family:var(--font-sans);font-size:var(--t5);line-height:var(--lh-body);word-break:keep-all;overflow-wrap:anywhere;-webkit-font-smoothing:antialiased}
.wrap{max-width:880px;margin:0 auto;padding:72px 24px 96px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:16px;top:-64px;background:var(--grey-900);color:#FFFFFF;padding:12px 16px;border-radius:12px;z-index:10}
.skip:focus{top:16px}
a{color:var(--accent);text-underline-offset:4px}
a:hover{color:var(--blue-800)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
h1,h2,h3,h4,h5{color:var(--grey-900);line-height:var(--lh-title);font-weight:700}
h1{font-size:var(--t1)}
h2{font-size:var(--t2)}
h3{font-size:var(--t3)}
h4{font-size:var(--t4)}
h5{font-size:var(--t5)}
ul,ol{padding-left:24px}
.hidden{display:none!important}
.kicker{font-weight:700;color:var(--accent);margin-bottom:8px}
.lead{margin-top:8px;color:var(--grey-700)}
.block{margin-top:72px}
.block>h2+.lead{margin-top:8px}

.hero h1{margin-top:0}
.top-fix{margin-top:40px;padding:32px;border-radius:20px;background:var(--grey-50)}
.top-fix h2{font-size:var(--t3)}
.top-fix ol{margin-top:24px;padding-left:0;list-style:none;display:grid;gap:24px;counter-reset:top}
.top-fix li{display:grid;gap:8px;padding-left:44px;position:relative;counter-increment:top}
.top-fix li::before{content:counter(top);position:absolute;left:0;top:0;width:28px;height:28px;border-radius:50%;background:var(--grey-900);color:#FFFFFF;line-height:28px;font-weight:700;text-align:center}
.top-fix a{font-weight:700}
.top-sub{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;color:var(--grey-700)}
.stats{list-style:none;padding:0;margin-top:32px;display:flex;flex-wrap:wrap;gap:8px 24px;color:var(--grey-700)}
.stats b{color:var(--grey-900)}
.tools{margin-top:24px;display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.fallback{display:block;width:100%;margin-top:12px;min-height:160px;padding:16px;border:1px solid var(--grey-600);border-radius:12px;font:inherit;color:var(--grey-900);background:#FFFFFF}
.meta-wrap{margin-top:24px}
.meta-wrap summary{display:flex;align-items:center;min-height:44px;cursor:pointer;font-weight:700;color:var(--grey-900)}
.meta{margin-top:8px;padding:24px;background:var(--grey-50);border-radius:16px;display:grid;gap:16px;color:var(--grey-700)}
.meta dt{font-weight:700;color:var(--grey-900)}
.meta dd{margin:4px 0 0}
.jump{margin-top:32px;display:flex;flex-wrap:wrap;gap:8px 24px}
.foot-meta{margin-top:72px;padding-top:24px;border-top:1px solid var(--grey-200);color:var(--grey-600)}

.badge{display:inline-flex;align-items:center;gap:8px;padding:4px 12px;border-radius:999px;font-weight:700;line-height:var(--lh-body);background:var(--grey-100);color:var(--grey-700)}
.badge::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor;flex:none}
.sev-high{background:var(--red-50);color:var(--red-800)}
.sev-mid{background:var(--yellow-50);color:var(--grey-900)}
.sev-mid::before{background:var(--yellow-600)}
.sev-low{background:var(--grey-100);color:var(--grey-700)}
.tag{display:inline-block;padding:4px 12px;border-radius:999px;background:var(--accent-soft);color:var(--blue-800)}
.tag.plain{background:var(--grey-100);color:var(--grey-700)}

.screen{margin-top:64px;padding-top:64px;border-top:1px solid var(--grey-200);display:grid;grid-template-columns:240px minmax(0,1fr);gap:32px;align-items:start}
.block>.lead+.screen{margin-top:40px;padding-top:0;border-top:0}
.thumb{position:sticky;top:24px}
.screen-body{min-width:0}
.pinbox{display:block;max-height:720px;overflow:auto;border-radius:16px}
.pinin{position:relative;display:block}
.pinbox img{display:block;width:100%;height:auto;border:1px solid var(--grey-300);border-radius:16px;background:var(--grey-50)}
.pin{position:absolute;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;background:var(--accent);color:#FFFFFF;line-height:28px;font-weight:700;text-align:center;box-shadow:0 0 0 2px #FFFFFF}
.noimg{padding:24px;border:1px dashed var(--grey-400);border-radius:16px;text-align:center;color:var(--grey-700)}
.screen-info h3{margin:0}
.screen-info .verdict{margin-top:12px;color:var(--grey-900)}
.screen-info .sub{margin-top:12px;color:var(--grey-600)}
.progress{margin-top:12px;color:var(--grey-600)}

.cards{margin-top:32px;display:grid;gap:24px}
.card{min-width:0;padding:32px;border:1px solid var(--grey-200);border-left-width:4px;border-radius:20px;scroll-margin-top:24px}
.card.c-sev-high{border-left-color:var(--red-500)}
.card.c-sev-mid{border-left-color:var(--yellow-600)}
.card.c-sev-low{border-left-color:var(--grey-400)}
.card-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.num{display:inline-block;width:28px;height:28px;border-radius:50%;background:var(--accent);color:#FFFFFF;line-height:28px;font-weight:700;text-align:center}
.card h4.title{margin-top:16px}
.crop{display:none;position:relative;margin-top:20px;overflow:hidden;max-width:100%;border:3px solid var(--red-500);border-radius:12px;background:var(--grey-50)}
.crop.ok{display:block}
.crop canvas{display:block;max-width:100%;height:auto}
.crop .pin{background:var(--red-500)}
.part{margin-top:32px}
.part h5+*{margin-top:8px}
.part p+p{margin-top:12px}
.part .where{color:var(--grey-700)}
.crop.ok~.part .where{display:none}
.done{padding:20px 24px;border-radius:16px;background:var(--green-50);color:var(--grey-900)}
.done h5{color:var(--green-900)}
.rule{padding-top:24px;border-top:1px dashed var(--grey-300);color:var(--grey-700)}
.rule h5{color:var(--grey-700)}
.ab{margin-top:16px;display:grid;gap:12px}
.ab>div{padding:20px;border-radius:16px}
.ab .was{background:var(--grey-100)}
.ab .now{background:var(--accent-soft)}
.ab .abk{display:block;font-weight:700;color:var(--grey-900)}
.ab .abk+p{margin-top:8px}
.reacts{margin-top:12px}
.same{color:var(--grey-700)}
.btn{font:inherit;font-weight:500;min-height:44px;padding:0 16px;border-radius:12px;border:1px solid var(--grey-600);background:#FFFFFF;color:var(--grey-800);cursor:pointer}
.btn:hover{background:var(--grey-100)}
.btn.resolve{border-color:var(--green-900);color:var(--green-900)}
.card-actions{margin-top:32px;padding-top:24px;border-top:1px solid var(--grey-200);display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.card .state,.card .act-undo{display:none}
.card.cls-resolve,.card.cls-dismiss{background:var(--grey-50);border-left-color:var(--grey-300)}
.card.cls-resolve>.part,.card.cls-dismiss>.part,.card.cls-resolve>.crop,.card.cls-dismiss>.crop{display:none}
.card.cls-resolve .card-actions,.card.cls-dismiss .card-actions{padding-top:0;border-top:0;margin-top:16px}
.card.cls-resolve .act-open,.card.cls-dismiss .act-open{display:none}
.card.cls-resolve .act-undo,.card.cls-dismiss .act-undo{display:inline-block}
.card.cls-resolve .state-resolve,.card.cls-dismiss .state-dismiss{display:inline-block}

.screen-sub{margin-top:48px}
.bubbles{list-style:none;padding:0;margin-top:20px;display:grid;gap:16px}
.bubble{display:flex;gap:12px;align-items:flex-start;scroll-margin-top:24px}
.avatar{flex:none;display:block;width:36px;height:36px}
.avatar .skin{fill:var(--yellow-200)}
.avatar .ink{fill:var(--grey-900)}
.avatar .line{fill:none;stroke:var(--grey-900);stroke-width:1.2;stroke-linecap:round;stroke-linejoin:round}
.avatar .thin{fill:none;stroke:var(--grey-700);stroke-width:1;stroke-linecap:round}
.avatar .bg-youth{fill:var(--blue-50)}
.avatar .bg-mid{fill:var(--teal-50)}
.avatar .bg-senior{fill:var(--yellow-50)}
.avatar .bg-none{fill:var(--grey-100)}
.avatar .cloth-youth{fill:var(--blue-500)}
.avatar .cloth-mid{fill:var(--teal-700)}
.avatar .cloth-senior{fill:var(--orange-500)}
.avatar .cloth-none{fill:var(--grey-500)}
.avatar .hair-dark{fill:var(--grey-900)}
.avatar .hair-mid{fill:var(--grey-700)}
.avatar .hair-white{fill:var(--grey-200);stroke:var(--grey-500);stroke-width:.8}
.bub{flex:1;min-width:0;padding:16px 20px;border-radius:4px 16px 16px 16px;background:var(--grey-50)}
.who{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 8px;color:var(--grey-700)}
.who b{color:var(--grey-900)}
.say{margin-top:8px;color:var(--grey-900);font-weight:500}
.axes{list-style:none;padding:0;margin-top:12px;display:flex;flex-wrap:wrap;gap:4px 20px}
.axes li{display:flex;align-items:center;gap:8px}
.axes .an{color:var(--grey-700)}
.lv{display:inline-flex;align-items:center;gap:8px;color:var(--grey-900)}
.lv i{display:inline-block;width:12px;height:12px;flex:none}
.lv-ok i{border-radius:50%;background:var(--green-500)}
.lv-mid i{background:var(--yellow-600);transform:rotate(45deg);width:10px;height:10px}
.lv-block i{border-radius:2px;background:var(--red-500)}
.lv-block{font-weight:700}
.cause,.links{margin-top:8px;color:var(--grey-700)}
.plain-list{margin-top:20px;display:grid;gap:12px;list-style:none;padding:0}
.clean{margin-top:64px;padding:24px 32px;background:var(--grey-50);border-radius:20px;color:var(--grey-700)}
.clean-title{font-weight:700;color:var(--grey-900)}
.names{margin-top:16px;padding:0;list-style:none;display:grid;gap:12px}
.names b{display:block;color:var(--grey-900);font-weight:500}

.personas{margin-top:32px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;padding:0;list-style:none}
.persona{padding:24px;border:1px solid var(--grey-200);border-radius:20px;scroll-margin-top:24px}
.persona h3{font-size:var(--t4);margin:0}
.persona .row1{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.persona p{margin-top:12px}
.levels{list-style:none;padding:0;margin-top:12px;display:grid;gap:4px;color:var(--grey-700)}
.levels b{color:var(--grey-900)}
.outcome{padding:12px 16px;border-radius:12px;background:var(--grey-100);color:var(--grey-900)}
.outcome.done{background:var(--green-50)}
.outcome.stop{background:var(--red-50)}
.checks{margin-top:24px;display:grid;gap:24px}
.checks dt{font-weight:700;color:var(--grey-900)}
.checks dd{margin:8px 0 0;color:var(--grey-700)}

@media (max-width:720px){
.wrap{padding:48px 20px 72px}
h1{font-size:var(--t2)}
.top-fix{padding:24px}
.screen{grid-template-columns:minmax(0,1fr);gap:24px}
.thumb{position:static;width:240px;max-width:100%}
.card{padding:24px}
}
"""

CSS = CSS_VARS + CSS_BASE

JS = r"""
(function(){
var KEY=document.body.getAttribute('data-key')||'bf-cls',cls={};
try{cls=JSON.parse(localStorage.getItem(KEY)||'{}')||{};}catch(e){cls={};}
function save(){try{localStorage.setItem(KEY,JSON.stringify(cls));}catch(e){}}
var cards=[].slice.call(document.querySelectorAll('.card[data-fid]'));
var live=document.getElementById('live');
function say(m){if(live)live.textContent=m;}
function state(fid){var c=cls[fid];return c==='resolve'||c==='dismiss'?c:null;}
function apply(){
  var n={resolve:0,dismiss:0},per={};
  cards.forEach(function(c){
    var st=state(c.getAttribute('data-fid'));
    c.classList.toggle('cls-resolve',st==='resolve');
    c.classList.toggle('cls-dismiss',st==='dismiss');
    if(st)n[st]++;
    var s=c.closest('.screen');
    if(s){var k=s.getAttribute('data-sid');per[k]=per[k]||{all:0,done:0};per[k].all++;if(st)per[k].done++;}
  });
  ['resolve','dismiss'].forEach(function(k){var e=document.getElementById('n-'+k);if(e)e.textContent=n[k];});
  [].forEach.call(document.querySelectorAll('.screen[data-sid] .progress'),function(e){
    var p=per[e.closest('.screen').getAttribute('data-sid')];if(!p)return;
    e.textContent='지적 '+p.all+'개 중 '+p.done+'개 정리'+(p.done&&p.done===p.all?' · 이 화면은 다 정리했어요':'');
  });
}
function drawCrop(c){
  var src=document.getElementById(c.getAttribute('data-img')),cv=c.querySelector('canvas');
  if(!src||!cv||!src.naturalWidth||!src.naturalHeight)return;
  var iw=src.naturalWidth,ih=src.naturalHeight;
  var x=+c.getAttribute('data-x')||0,y=+c.getAttribute('data-y')||0;
  var box=c.hasAttribute('data-w'),w=box?+c.getAttribute('data-w'):1,h=box?+c.getAttribute('data-h'):0;
  c.style.width='';c.classList.add('ok');
  var cw=Math.min(c.clientWidth||360,360);   // 카드 안 폭과 360px 중 작은 쪽. 폭을 지운 뒤 재야 resize마다 커지지 않는다
  var scale=Math.min(cw/(iw*w),2);
  if(!h)h=Math.min(1,(cw*0.6)/(ih*scale));
  scale=Math.min(scale,360/(ih*h));   // 너무 긴 상자는 높이 360px 안으로
  var bx=box?x:0,by=box?y:Math.min(Math.max(y-h/2,0),1-h);
  var dw=Math.round(iw*w*scale),dh=Math.round(ih*h*scale),r=window.devicePixelRatio||1;
  cv.width=Math.round(dw*r);cv.height=Math.round(dh*r);cv.style.width=dw+'px';
  c.style.width=(dw+6)+'px';   // 테두리 3px씩 포함(border-box)
  var g=cv.getContext('2d');if(!g){c.classList.remove('ok');return;}
  g.drawImage(src,iw*bx,ih*by,iw*w,ih*h,0,0,cv.width,cv.height);
  var pin=c.querySelector('.pin');
  if(pin){pin.style.left=Math.round(iw*(x-bx)*scale)+'px';pin.style.top=Math.round(ih*(y-by)*scale)+'px';}
}
function drawAll(){[].forEach.call(document.querySelectorAll('.crop'),drawCrop);}
[].forEach.call(document.querySelectorAll('.pinbox img'),function(img){if(!img.complete)img.addEventListener('load',drawAll);});
var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(drawAll,150);});
function flash(b,msg){
  var old=b.getAttribute('data-label')||b.textContent;b.setAttribute('data-label',old);
  b.textContent=msg;clearTimeout(b._t);b._t=setTimeout(function(){b.textContent=old;},2000);
}
function pick(el){
  if(!el)return;
  if(el.select){el.select();return;}
  var r=document.createRange();r.selectNodeContents(el);
  var s=window.getSelection();s.removeAllRanges();s.addRange(r);
}
function copyText(text,btn,sel){
  function ok(){say('복사했어요');flash(btn,'복사했어요');}
  function fail(){say('복사하지 못했어요. 선택된 글을 직접 복사해 주세요');flash(btn,'직접 복사해 주세요');pick(sel());}
  if(navigator.clipboard&&navigator.clipboard.writeText){
    try{navigator.clipboard.writeText(text).then(ok,fail);}catch(e){fail();}
  }else{fail();}
}
function checklist(){
  var box=document.getElementById('cl-data'),items=[];
  try{items=JSON.parse(box.textContent)||[];}catch(e){items=[];}
  var out=items.filter(function(it){return !state(it.fid);}).map(function(it){return it.text;});
  return out.length?'## 남은 지적 '+out.length+'개\n\n'+out.join('\n'):'';
}
document.addEventListener('click',function(ev){
  var cb=ev.target.closest&&ev.target.closest('button[data-copy]');
  if(cb){
    var tid=cb.getAttribute('data-copy');
    if(tid!=='checklist')return;
    var txt=checklist(),fb=document.getElementById('cl-fallback');
    if(!txt){say('남은 지적이 없어요');return;}
    fb.value=txt;
    copyText(txt,cb,function(){fb.classList.remove('hidden');fb.focus();return fb;});
    return;
  }
  var b=ev.target.closest&&ev.target.closest('button[data-act]');
  if(b){
    var c=b.closest('.card');if(!c)return;
    var fid=c.getAttribute('data-fid'),act=b.getAttribute('data-act'),tt=c.querySelector('.title'),nm=tt?tt.textContent:'지적';
    if(act==='undo'){delete cls[fid];say(nm+' · 다시 열었어요');}
    else{cls[fid]=act;say(nm+(act==='resolve'?' · 고쳤어요로 표시했어요':' · 문제 아님으로 표시했어요'));}
    save();apply();
    var nb=c.querySelector(act==='undo'?'.act-open':'.act-undo');if(nb)nb.focus();   // 누른 버튼이 숨으니 포커스를 옮긴다
  }
});
apply();drawAll();
})();
"""


# 연령대 아이콘: 36x36 인라인 SVG. 이 저장소에서 직접 그린 도형이고 MIT로 함께 배포해요.
# 색은 CSS 클래스로 정해진 팔레트 변수만 써요. 외부 파일, 이모지, 글꼴을 쓰지 않아요.
FACE = '<ellipse class="skin" cx="18" cy="16" rx="6.5" ry="7.5"/>'
EYES = '<circle class="ink" cx="15.3" cy="16.8" r=".9"/><circle class="ink" cx="20.7" cy="16.8" r=".9"/>'
SMILE = '<path class="line" d="M15.8 19.8 Q18 21.6 20.2 19.8"/>'
NECK = '<rect class="skin" x="16" y="21" width="4" height="6"/>'

AVATAR_PARTS = {
    # 청년: 짧고 가벼운 머리, 안경 없음, 파란 옷
    "youth": (
        '<path class="hair-dark" d="M11.4 15.2 C10.6 9.6 14 7.6 18 7.6 C22 7.6 25.4 9.6 24.6 15.2 '
        'C23.4 12.6 21 11.4 18 11.4 C15 11.4 12.6 12.6 11.4 15.2 Z"/>'
        '<path class="hair-dark" d="M14.2 10.4 L16.4 8.2 L17.6 10.6 Z"/>'
        + EYES + SMILE),
    # 중년: 귀를 덮는 풍성한 머리, 네모난 안경, 청록 옷
    "mid": (
        '<path class="hair-mid" d="M10.8 19 C9.6 9.6 13.4 7 18 7 C22.6 7 26.4 9.6 25.2 19 '
        'C24.8 14.8 22.8 11.6 18 11.6 C13.2 11.6 11.2 14.8 10.8 19 Z"/>'
        '<rect class="thin" x="12.4" y="14.9" width="5" height="3.8" rx="1"/>'
        '<rect class="thin" x="18.6" y="14.9" width="5" height="3.8" rx="1"/>'
        '<path class="thin" d="M17.4 16.4 L18.6 16.4"/>'
        '<circle class="ink" cx="14.9" cy="16.8" r=".9"/><circle class="ink" cx="21.1" cy="16.8" r=".9"/>'
        + SMILE),
    # 노년: 옅은 머리, 둥근 안경, 얼굴 주름, 주황 옷
    "senior": (
        '<path class="hair-white" d="M11.2 17 C10.2 10 14 7.8 18 7.8 C22 7.8 25.8 10 24.8 17 '
        'C24.4 13.6 22.2 11.6 18 11.6 C13.8 11.6 11.6 13.6 11.2 17 Z"/>'
        '<circle class="thin" cx="14.9" cy="16.9" r="2.9"/><circle class="thin" cx="21.1" cy="16.9" r="2.9"/>'
        '<path class="thin" d="M17.8 16.6 L18.2 16.6"/>'
        '<circle class="ink" cx="14.9" cy="16.9" r=".9"/><circle class="ink" cx="21.1" cy="16.9" r=".9"/>'
        '<path class="thin" d="M13.6 20.4 Q13.2 21.4 13.8 22.2"/><path class="thin" d="M22.4 20.4 Q22.8 21.4 22.2 22.2"/>'
        '<path class="thin" d="M10.8 15.6 L11.8 16.2"/><path class="thin" d="M25.2 15.6 L24.2 16.2"/>'
        + SMILE),
}
SHOULDERS = '<path class="cloth-{k}" d="M7 31 C8.6 27.2 13 25.6 18 25.6 C23 25.6 27.4 27.2 29 31 A18 18 0 0 1 7 31 Z"/>'


def avatar(age_group, decorative=False):
    """연령대(청년, 중년, 노년) 아이콘 SVG 문자열. 모르는 값이면 중립 아이콘.
    옆에 연령대 글이 있으면 decorative=True로 스크린리더에서 숨기고, 아이콘만 있을 때만 title과 label을 둔다."""
    key = AGE_KEYS.get(age_group) if isinstance(age_group, str) else None
    alt = AGE_ALT.get(age_group, "사용자") if key else "사용자"
    k = key or "none"
    face = AVATAR_PARTS.get(key) or (EYES + SMILE)
    if decorative:
        head = 'aria-hidden="true" focusable="false">'
    else:
        head = f'role="img" aria-label="{esc(alt)}" focusable="false"><title>{esc(alt)}</title>'
    return (f'<svg class="avatar" width="36" height="36" viewBox="0 0 36 36" {head}'
            f'<circle class="bg-{k}" cx="18" cy="18" r="18"/>{SHOULDERS.format(k=k)}{NECK}{FACE}{face}</svg>')


def sev_label(sev):
    return SEV_VIEW.get(sev, SEV_VIEW["낮음"])[1]


def sev_badge(sev):
    cls, label = SEV_VIEW.get(sev, SEV_VIEW["낮음"])
    return f'<span class="badge {cls}">{label}</span>'


def finding_link(m, fid):
    """지적을 제목 링크로. id는 메이커에게 의미가 없어서 보이지 않는다. 카드가 없으면 빈 문자열."""
    f = m.finding_by_id.get(fid)
    if f is None:
        return ""
    return f'<a href="#f-{slug(fid)}">{esc(f.get("title") or fid)}</a>'


def render_card(m, f, num, img_id=None):
    """지적 카드. img_id는 화면 썸네일 img의 id(위치 그림을 그 이미지에서 잘라 그린다). 없으면 그림 없이.
    시니어가 옆에서 짚어 주는 순서: 위치 그림 → 문제(영향 포함) → 이렇게 고쳐요 → 고친 뒤 확인할 것 → 검토 기준.
    원칙 영어 이름·사례 번호·지적 id는 내부 검증용이라 보이지 않고, 원칙은 사람 말 질문으로만 남긴다."""
    fid = t(f.get("id"))
    title = t(f.get("title"))
    sev = f.get("severity")
    cls = SEV_VIEW.get(sev, SEV_VIEW["낮음"])[0]
    top = []
    if num:
        top.append(f'<span class="num" aria-hidden="true">{num}</span>')
    top.append(sev_badge(sev))
    sid = t(f.get("screen_id"))
    # 화면이 없는 흐름 지적은 '화면 사이에서 빠진 흐름' 절에 있어서 같은 말의 칩을 또 달지 않는다
    if f.get("lens") in LENS_LABEL and sid in m.screen_by_id:
        top.append(f'<span class="tag plain">{LENS_LABEL[f["lens"]]}</span>')

    ev = f.get("evidence") if isinstance(f.get("evidence"), dict) else {}
    crop = ""
    box = pin_box(f)
    if img_id and box:
        x, y, w, h = box
        attrs = f'data-img="{img_id}" data-x="{x:.4f}" data-y="{y:.4f}"'
        pin = ""
        if w:
            attrs += f' data-w="{w:.4f}" data-h="{h:.4f}"'
        else:
            pin = f'<span class="pin" aria-hidden="true">{num or ""}</span>'
        crop = (f'<div class="crop" {attrs} role="img" aria-label="{esc(m.screen_name(sid))} 화면에서 이 지적이 가리키는 부분">'
                f'<canvas aria-hidden="true"></canvas>{pin}</div>')
    # 위치 그림이 그려지면 CSS가 이 글을 숨긴다. 그림을 못 그릴 때만 위치를 글로 알려 준다
    where = (f'<p class="where">위치: {esc(ev.get("where"))}</p>' if t(ev.get("where")) else "")
    paras = "".join(f'<p>{esc(f.get(k))}</p>' for k in ("observation", "why") if t(f.get(k)))
    reacts = render_reactions(m, fid)
    p1 = (f'<section class="part"><h5>문제</h5>{paras}{where}{reacts}</section>'
          if paras or where or reacts else "")

    p2 = ""
    asis, tobe = t(f.get("asis")), t(f.get("tobe"))
    if t(f.get("fix")) or asis or tobe:
        ab = ""
        if asis or tobe:
            boxes = ""
            if asis:
                boxes += f'<div class="was"><span class="abk">수정 전</span><p>{esc(asis)}</p></div>'
            if tobe:
                boxes += f'<div class="now"><span class="abk">수정 후</span><p>{esc(tobe)}</p></div>'
            ab = f'<div class="ab">{boxes}</div>'
        fixp = f'<p>{esc(f.get("fix"))}</p>' if t(f.get("fix")) else ""
        p2 = f'<section class="part"><h5>이렇게 고쳐요</h5>{fixp}{ab}</section>'

    p3 = (f'<section class="part done"><h5>고친 뒤 확인할 것</h5><p>{esc(f.get("done_when"))}</p></section>'
          if t(f.get("done_when")).strip() else "")
    p4 = (f'<section class="part"><h5>화면만으로는 알 수 없는 것</h5><p>{esc(f.get("confirm_needed"))}</p></section>'
          if t(f.get("confirm_needed")) else "")
    q = ask(m.questions.get(t(f.get("principle")))) if t(f.get("principle")) else ""
    p5 = f'<section class="part rule"><h5>검토 기준</h5><p>{esc(q)}</p></section>' if q else ""

    actions = ""
    if fid:
        name = esc(title or "이 지적")
        actions = ('<div class="card-actions"><span class="tag plain state state-resolve">고쳤어요</span>'
                   '<span class="tag plain state state-dismiss">문제 아님</span>'
                   f'<button type="button" class="btn resolve act-open" data-act="resolve" aria-label="{name} 고쳤어요">고쳤어요</button>'
                   f'<button type="button" class="btn act-open" data-act="dismiss" aria-label="{name} 문제 아님">문제 아님</button>'
                   f'<button type="button" class="btn act-undo" data-act="undo" aria-label="{name} 되돌리기">되돌리기</button></div>')

    return (f'<article class="card c-{cls}" id="f-{slug(fid)}" data-fid="{esc(fid)}">'
            f'<div class="card-top">{"".join(top)}</div>'
            f'<h4 class="title">{esc(title)}</h4>{crop}{p1}{p2}{p3}{p4}{p5}{actions}</article>')


def reaction_anchor(pid, sid):
    return f"ut-r-{slug(pid)}-{slug(sid)}"


def render_reactions(m, fid):
    """지적에 이어진 가상 사용자를 이름으로만 잇는다. 한마디는 그 화면 아래 반응 묶음에 한 번만 둔다."""
    if not m.ut:
        return ""
    links = []
    for pid in m.ut["by_finding"].get(fid, []):
        p = m.ut["persona_by_id"].get(pid)
        if not p:
            continue
        st = m.ut["step_for"].get((fid, pid))
        href = reaction_anchor(pid, t(st.get("screen_id"))) if st else f"ut-p-{slug(pid)}"
        links.append(f'<a href="#{href}">{esc(p.get("name"))}</a>')
    if not links:
        return ""
    return f'<div class="reacts"><p class="same">가상 사용자 반응: {", ".join(links)}</p></div>'


def render_screen_reactions(m, sid):
    """이 화면을 걸어 본 가상 사용자의 세 축과 한마디. 세 가지 모두 쉬움인 사람은 이름만 한 줄로."""
    if not m.ut:
        return ""
    items, easy = [], []
    for p in m.ut["personas"]:
        pid = t(p["id"])
        w = m.ut["walks"].get(pid, {})
        # 같은 화면을 다시 지나간 반응도 모두 그린다. 앵커는 첫 반응에, 멈춘 표시는 그 화면의 마지막 반응에
        sts = [st for st in dicts(w.get("steps")) if t(st.get("screen_id")) == sid]
        if not sts:
            if (pid, sid) in m.ut["easy"]:
                easy.append(f'<a href="#ut-p-{slug(pid)}">{esc(p.get("name"))}</a>')
            continue
        stopped = w.get("outcome") == "이탈" and t(w.get("stopped_at")) == sid
        for i, st in enumerate(sts):
            axes = "".join(f'<li><span class="an">{an}</span><span class="lv {LV_CLASS.get(st.get(key), "")}">'
                           f'<i aria-hidden="true"></i>{esc(st.get(key))}</span></li>' for key, an in AXES)
            stop = ('<p class="links"><span class="tag plain">여기서 멈췄어요</span></p>'
                    if stopped and i == len(sts) - 1 else "")
            cause = f'<p class="cause">원인: {esc(st.get("cause"))}</p>' if t(st.get("cause")) else ""
            fids = strs(st.get("finding_ids"))
            links = f'<p class="links">이어진 지적: {" · ".join(finding_link(m, x) for x in fids)}</p>' if fids else ""
            anchor = f' id="{reaction_anchor(pid, sid)}"' if i == 0 else ""
            items.append(f'<li class="bubble"{anchor}>{avatar(p.get("age_group"), True)}<div class="bub">'
                         f'<p class="who"><b><a href="#ut-p-{slug(pid)}">{esc(p.get("name"))}</a></b>'
                         f'<span>{esc(persona_line(p))}</span></p><p class="say">“{esc(st.get("quote"))}”</p>'
                         f'<ul class="axes">{axes}</ul>{stop}{cause}{links}</div></li>')
    if not items and not easy:
        return ""
    out = '<section class="screen-sub"><h4>가상 사용자 반응</h4>'
    if items:
        out += f'<ul class="bubbles">{"".join(items)}</ul>'
    if easy:
        out += f'<p class="same">세 가지 모두 쉬웠던 사람: {", ".join(easy)}</p>'
    return out + "</section>"


def strength_items(sts):
    """잘 된 점 목록. 원칙 영어 이름은 내부 검증용이라 보이지 않는다."""
    return '<ul class="plain-list">' + "".join(f"<li>{esc(st.get('note'))}</li>" for st in sts) + "</ul>"


def render_screen(m, run, s, items, embedded, missing):
    sid = t(s.get("id"))
    name = m.screen_name(sid)
    path = safe_shot(run, s.get("shot"))
    img_id = f"img-{slug(sid)}"
    pins, nums = [], {}
    for f in items:
        box = pin_box(f)
        if path and box:
            i = nums[id(f)] = len(pins) + 1   # pin이 있는 지적만 이어서 센다
            px, py = pin_point(box)
            pins.append(f'<span class="pin" aria-hidden="true" style="left:{px * 100:.1f}%;top:{py * 100:.1f}%">{i}</span>')
    if path:
        embedded.append(path)
        img = (f'<span class="pinbox"><span class="pinin"><img src="{data_uri(path)}" alt="{esc(name)} 화면 시안" id="{img_id}">'
               f'{"".join(pins)}</span></span>')
    else:
        missing.append(name)
        img = '<div class="noimg">이미지를 불러오지 못했어요</div>'
        img_id = None
    cards = "".join(render_card(m, f, nums.get(id(f)), img_id) for f in items)
    sub = []
    if t(s.get("verdict")):
        sub.append(f'<p class="verdict">{esc(s.get("verdict"))}</p>')
    if t(s.get("screen_goal")):
        sub.append(f'<p class="sub">화면 목표: {esc(s.get("screen_goal"))}</p>')
    if items:
        sub.append(f'<p class="progress">지적 {len(items)}개</p>')
    goods = m.strengths_by_screen.get(sid)
    good_html = (f'<section class="screen-sub"><h4>잘 된 점</h4>{strength_items(goods)}</section>'
                 if goods else "")
    # 왼쪽 화면은 스크롤해도 따라오고, 오른쪽에 진단 → 지적 → 가상 반응 → 잘 된 점이 이어진다
    return (f'<article class="screen" id="sec-{slug(sid)}" data-sid="{esc(slug(sid))}" data-name="{esc(name)}">'
            f'<div class="thumb">{img}</div><div class="screen-body">'
            f'<div class="screen-info"><h3>{esc(name)}</h3>{"".join(sub)}</div>'
            + (f'<div class="cards">{cards}</div>' if cards else "")
            + f'{render_screen_reactions(m, sid)}{good_html}</div></article>')


def render_ut(m):
    ut = m.ut
    out = ['<section class="block" id="ut" aria-labelledby="h-ut"><h2 id="h-ut">가상 사용자</h2>'
           f'<p class="lead">이 {len(ut["personas"])}명이 화면을 본다면 어떻게 반응할지 화면 이미지만 보고 추론했어요. '
           '반응은 각 화면 아래에 있어요.</p>']
    cards = []
    for p in ut["personas"]:
        pid = t(p["id"])
        w = ut["walks"].get(pid, {})
        if w.get("outcome") == "이탈":
            stop_sid = t(w.get("stopped_at"))
            where = esc(m.screen_name(stop_sid))
            if (pid, stop_sid) in ut["steps"]:
                where = f'<a href="#{reaction_anchor(pid, stop_sid)}">{where}</a>'
            out_html = (f'<p class="outcome stop"><b>이탈</b> · {where}에서 멈췄어요. '
                        f'{esc(w.get("stop_reason"))}</p>')
        elif w.get("outcome") == "완주":
            out_html = '<p class="outcome done"><b>완주</b> · 끝까지 걸었어요</p>'
        else:
            out_html = ""
        cards.append(
            f'<li class="persona" id="ut-p-{slug(pid)}"><div class="row1">{avatar(p.get("age_group"), True)}<h3>{esc(p.get("name"))}</h3>'
            f'<span class="tag">{esc(p.get("age_group"))}</span></div>'
            f'<ul class="levels"><li>휴대폰 조작 <b>{esc(level_word(p.get("device_level")))}</b></li>'
            f'<li>앱 이해 <b>{esc(level_word(p.get("ux_level")))}</b></li></ul>'
            f'<p>{esc(p.get("traits"))}</p>'
            + (f'<p>목표: {esc(p.get("goal"))}</p>' if t(p.get("goal")) else "")
            + out_html + '</li>')
    out.append(f'<ul class="personas">{"".join(cards)}</ul>')

    out.append('</section>')
    return "".join(out)


def build_html(m, run):
    n_screens, n_find, n_sev = m.counts()
    headline = t(m.summary.get("headline")) or "UX 리뷰 결과"
    embedded, missing = [], []

    key_src = headline + "|" + ",".join(sorted(m.finding_by_id)) + "|" + ",".join(sorted(m.screen_by_id))
    key = "bf-cls-" + hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:10]

    # 검토 전제는 접어 두고(메이커가 먼저 볼 것은 지적), 같은 뜻의 줄은 하나만 둔다
    meta = []
    src = m.cap.get("source") if isinstance(m.cap.get("source"), dict) else {}
    if t(src.get("name")):
        meta.append(("리뷰 대상", esc(src.get("name"))))
    if t(m.run.get("product_value")):
        meta.append(("제품 핵심 가치", esc(m.run.get("product_value"))))
    brief = m.run.get("brief") if isinstance(m.run.get("brief"), dict) else {}
    if t(m.run.get("goal")) and not t(brief.get("objective")):
        meta.append(("리뷰 목표", esc(m.run.get("goal"))))
    for k, label in BRIEF_FIELDS:
        if t(brief.get(k)):
            meta.append((label, esc(brief.get(k))))
    if brief.get("source") == "inferred":
        meta.append(("전제 출처", "모두 화면을 보고 추론했어요"))
    elif brief.get("source") == "mixed":
        meta.append(("전제 출처", "일부는 화면을 보고 추론했어요"))
    meta_html = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in meta)
    meta_wrap = (f'<details class="meta-wrap"><summary>리뷰 전제 보기</summary><dl class="meta">{meta_html}</dl></details>'
                 if meta else "")
    src_label = label_of(INPUT_LABEL, m.run.get("input_type"))
    foot = [f"{src_label} 화면으로 리뷰했어요." if src_label else "",
            f'{label_of(WRITING_LABEL, m.run.get("writing_judge"))}.' if label_of(WRITING_LABEL, m.run.get("writing_judge")) else ""]
    foot_meta = f'<p class="foot-meta">{esc(" ".join(x for x in foot if x))}</p>' if any(foot) else ""

    top = []
    for f in top_findings(m):
        fid = t(f.get("id"))
        sid = t(f.get("screen_id"))
        where = esc(m.screen_name(sid)) if sid in m.screen_by_id else "화면 사이 흐름"
        top.append(f'<li><a href="#f-{slug(fid)}">{esc(f.get("title"))}</a>'
                   f'<span class="top-sub">{sev_badge(f.get("severity"))}<span>{where}</span></span></li>')
    top_html = (f'<section class="top-fix" aria-labelledby="h-top"><h2 id="h-top">먼저 고칠 것</h2>'
                f'<ol>{"".join(top)}</ol></section>') if top else ""

    tools_html = ""
    if m.findings:
        data = json.dumps(checklist_items(m), ensure_ascii=False).replace("<", "\\u003c")
        tools_html = ('<div class="tools"><button type="button" class="btn" data-copy="checklist">'
                      '남은 지적을 체크리스트로 복사</button></div>'
                      '<textarea class="fallback hidden" id="cl-fallback" readonly '
                      'aria-label="체크리스트 글. 복사하지 못했을 때 직접 복사해요"></textarea>'
                      f'<script type="application/json" id="cl-data">{data}</script>')

    jumps = []
    shown_screens = [s for s in m.screens if m.screen_has_content(t(s.get("id")))]
    if shown_screens:
        jumps.append('<a href="#screens">화면별 리뷰</a>')
    if m.flow:
        jumps.append('<a href="#flow">화면 사이에서 빠진 흐름</a>')
    if m.ut:
        jumps.append('<a href="#ut">가상 사용자</a>')
    if m.loose_strengths:
        jumps.append('<a href="#strengths">잘 된 점</a>')
    if m.checks:
        jumps.append('<a href="#checks">확인이 필요한 것</a>')
    jump_html = f'<nav class="jump" aria-label="리포트 목차">{"".join(jumps)}</nav>' if jumps else ""

    progress = ('<li>고쳤어요 <b id="n-resolve">0</b>개</li><li>문제 아님 <b id="n-dismiss">0</b>개</li>'
                if m.findings else "")
    header = (f'<header class="hero"><p class="kicker">UX 리뷰 결과</p><h1>{esc(headline)}</h1>'
              f'{top_html}{tools_html}'
              f'<ul class="stats"><li>화면 <b>{n_screens}</b>개</li><li>지적 <b>{n_find}</b>개</li>'
              f'<li>개선 필요 <b>{n_sev}</b>개</li>{progress}</ul>'
              f'{meta_wrap}{jump_html}</header>')

    parts = [header]

    if shown_screens:
        sec = ['<section class="block" id="screens" aria-labelledby="h-screens"><h2 id="h-screens">화면별 리뷰</h2>'
               f'<p class="lead">화면마다 지적{", 가상 사용자 반응" if m.ut else ""}, 잘 된 점을 모았어요. '
               '지적은 급한 것부터 보여요. 고쳤어요를 누르면 접히고, 이 브라우저에만 기억해요.</p>']
        for s in shown_screens:
            sec.append(render_screen(m, run, s, m.by_screen.get(t(s.get("id")), []), embedded, missing))
        clean = [s for s in m.screens if not m.screen_has_content(t(s.get("id")))]
        if clean:
            # 같은 문제를 다른 화면 지적에 묶어 둔 화면도 있어서, 이름과 한 줄 진단을 함께 보여 준다
            names = "".join(f'<li><b>{esc(m.screen_name(t(s.get("id"))))}</b>'
                            + (f'<span>{esc(s.get("verdict"))}</span>' if t(s.get("verdict")) else "") + "</li>"
                            for s in clean)
            sec.append(f'<div class="clean"><p class="clean-title">지적을 따로 붙이지 않은 화면 {len(clean)}개</p>'
                       f'<ul class="names">{names}</ul></div>')
        sec.append('</section>')
        parts.append("".join(sec))
    elif m.screens:
        names = [m.screen_name(t(s.get("id"))) for s in m.screens]
        names = "".join(f"<li><b>{esc(n)}</b></li>" for n in names)
        parts.append(f'<div class="clean block"><p class="clean-title">모든 화면에 따로 붙인 지적이 없어요</p><ul class="names">{names}</ul></div>')

    if m.flow:
        cards = "".join(render_card(m, f, None) for f in m.flow)
        parts.append('<section class="block" id="flow" aria-labelledby="h-flow"><h2 id="h-flow">화면 사이에서 빠진 흐름</h2>'
                     '<p class="lead">어느 한 화면에서 시작한다고 보기 어려운 빈틈이에요.</p>'
                     f'<div class="cards">{cards}</div></section>')

    if m.ut:
        parts.append(render_ut(m))

    if m.loose_strengths:
        parts.append('<section class="block" id="strengths" aria-labelledby="h-str"><h2 id="h-str">잘 된 점</h2>'
                     '<p class="lead">여러 화면에 걸쳐 잘 된 점이에요.</p>'
                     f'{strength_items(m.loose_strengths)}</section>')

    if m.checks:
        items = "".join(f"<div><dt>{esc(c.get('what'))}</dt><dd>{esc(c.get('how'))}</dd></div>" for c in m.checks)
        parts.append('<section class="block" id="checks" aria-labelledby="h-chk"><h2 id="h-chk">확인이 필요한 것</h2>'
                     '<p class="lead">화면만으로는 알 수 없었어요. 알려 주시면 해당 지적을 다시 볼게요.</p>'
                     f'<dl class="checks">{items}</dl></section>')
    parts.append(foot_meta)

    doc = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
           '<meta http-equiv="Content-Security-Policy" content="' + CSP + '">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{esc(headline)}</title><style>{CSS}</style></head>'
           f'<body data-key="{key}"><a class="skip" href="#main">본문으로 건너뛰기</a>'
           f'<main class="wrap" id="main">{"".join(parts)}</main>'
           '<p class="sr" id="live" role="status" aria-live="polite"></p>'
           f'<script>{JS}</script></body></html>')
    return doc, len(embedded), missing


# ── 마크다운 ──

def mt(v):
    """마크다운 한 줄용. 공백을 접고 HTML 태그, 링크와 이미지 문법, 자동 링크가 살아나지 않게 한다."""
    s = re.sub(r"\s+", " ", t(v)).strip()
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"([\\\[\]()!*_`])", r"\\\1", s)
    # http://, https://는 자동 링크와 이미지 요청이 되지 않게 ://를 끊는다(보이는 글은 그대로)
    return re.sub(r"(?i)\b(https?):(?=//)", "\\1:\u200b", s)


def mc(v):
    return mt(v).replace("|", "\\|")


def code(v):
    return "`" + t(v).replace("`", "'").replace("\n", " ") + "`"


def checklist_items(m):
    """남은 지적 체크리스트 항목을 심각도 순으로. sid는 화면 섹션 키(slug), 화면이 없는 지적은 빈 문자열.
    HTML의 [남은 지적을 체크리스트로 복사]가 이 목록에서 고쳤어요·문제 아님으로 표시한 지적(fid)을 빼요."""
    items = []
    for f in sorted(m.findings, key=order_key):
        fid = t(f.get("id"))
        sid = t(f.get("screen_id"))
        in_screen = sid in m.screen_by_id
        scr = mt(m.screen_name(sid)) if in_screen else "화면 사이 흐름"
        lines = [f"- [ ] [{sev_label(f.get('severity'))}] {mt(f.get('title'))} ({scr})"]
        for label, key in (("고치기", "fix"), ("수정 후", "tobe"), ("확인 기준", "done_when")):
            if mt(f.get(key)):
                lines.append(f"  - {label}: {mt(f.get(key))}")
        items.append({"sid": slug(sid) if in_screen else "", "fid": fid, "text": "\n".join(lines)})
    return items


def render_checklist(items, skip_fids=()):
    """체크리스트 마크다운. skip_fids에 든 지적은 뺀다. 남은 것이 없으면 빈 문자열."""
    kept = [it["text"] for it in items if it["fid"] not in skip_fids]
    if not kept:
        return ""
    return f"## 남은 지적 {len(kept)}개\n\n" + "\n".join(kept)


def build_md(m):
    """채팅이나 문서에 붙여 쓰는 마크다운 리포트. HTML과 같은 말과 같은 규칙(내부 표기 없음)을 쓴다."""
    L = []
    headline = mt(m.summary.get("headline")) or "UX 리뷰 결과"
    L += ["# UX 리뷰 결과", "", "## 총평", f"**{headline}**"]
    # HTML 첫 화면과 같은 규칙: 개선 필요를 앞으로 올려 최대 TOP_MAX개
    top = [mt(f.get("title")) for f in top_findings(m)]
    if top:
        L.append("먼저 고칠 것: " + ", ".join(top))
    n_screens, n_find, n_sev = m.counts()
    L += ["", f"화면 {n_screens}개 · 지적 {n_find}개 · 개선 필요 {n_sev}개", ""]
    src_label = label_of(INPUT_LABEL, m.run.get("input_type"))
    cond = [f"{src_label} 화면으로 리뷰했어요." if src_label else "",
            f"{label_of(WRITING_LABEL, m.run.get('writing_judge'))}." if label_of(WRITING_LABEL, m.run.get("writing_judge")) else ""]
    if any(cond):
        L.append("리뷰 조건: " + mt(" ".join(x for x in cond if x)))
    if t(m.run.get("product_value")):
        L.append(f"제품 핵심 가치: {mt(m.run.get('product_value'))}")
    if t(m.run.get("goal")):
        L.append(f"목표: {mt(m.run.get('goal'))}")
    brief = m.run.get("brief") if isinstance(m.run.get("brief"), dict) else {}
    for k, label in BRIEF_FIELDS:
        if t(brief.get(k)):
            L.append(f"{label}: {mt(brief.get(k))}")
    if brief.get("source") in ("inferred", "mixed"):
        L.append("전제 출처: 일부나 전부를 화면을 보고 추론했어요")
    ex = [mt(EXCLUSION_WORD.get(x, x)) for x in strs(m.run.get("exclusions"))]
    if ex:
        L.append("리뷰에서 뺀 것: " + " / ".join(ex))

    L += ["", "## 화면"]
    for s in m.screens:
        L += ["", f"### {mt(s.get('name'))}",
              f"- 화면 목표: {mt(s.get('screen_goal'))}", f"- 한 줄 진단: {mt(s.get('verdict'))}"]

    L += ["", "## 지적"]
    for f in sorted(m.findings, key=order_key):
        L += ["", f"### [{sev_label(f.get('severity'))}] {mt(f.get('title'))}"]
        ev = f.get("evidence") if isinstance(f.get("evidence"), dict) else {}
        sid = t(f.get("screen_id"))
        scr = mt(m.screen_name(sid)) if sid in m.screen_by_id else "화면 사이 흐름"
        where = f" · {mt(ev.get('where'))}" if t(ev.get("where")) else ""
        kind = f" ({LENS_LABEL[f['lens']]})" if f.get("lens") in LENS_LABEL and sid in m.screen_by_id else ""
        L.append(f"- 화면: {scr}{where}{kind}")
        for label, key in (("문제", "observation"), ("왜 문제인가", "why"), ("이렇게 고쳐요", "fix"),
                           ("수정 전", "asis"), ("수정 후", "tobe"), ("고친 뒤 확인할 것", "done_when"),
                           ("화면만으로는 알 수 없는 것", "confirm_needed")):
            if t(f.get(key)):
                L.append(f"- {label}: {mt(f.get(key))}")
        q = ask(m.questions.get(t(f.get("principle")))) if t(f.get("principle")) else ""
        if q:
            L.append(f"- 검토 기준: {mt(q)}")
        if m.ut:
            names = [mt(m.ut["persona_by_id"][p].get("name")) for p in m.ut["by_finding"].get(t(f.get("id")), [])
                     if p in m.ut["persona_by_id"]]
            if names:
                L.append("- 가상 사용자 반응: " + ", ".join(names))

    if m.ut:
        ut = m.ut
        L += ["", "## 가상 사용자 (화면 이미지만 보고 추론한 반응이에요)", "", "### 사람"]
        for p in ut["personas"]:
            L.append(f"- {mt(p.get('name'))} ({mt(persona_line(p))}): {mt(p.get('traits'))} 목표: {mt(p.get('goal'))}")
        links = []
        for p in ut["personas"]:
            pid = t(p["id"])
            w = ut["walks"].get(pid, {})
            head = f"### {mt(p.get('name'))}: {mt(w.get('outcome'))}"
            if w.get("outcome") == "이탈":
                head += f"  ({mt(m.screen_name(t(w.get('stopped_at'))))}에서 멈춤, 이유: {mt(w.get('stop_reason'))})"
            L += ["", head]
            if dicts(w.get("steps")):
                L += ["| 화면 | " + " | ".join(an for _k, an in AXES) + " | 한마디 |", "|---|---|---|---|---|"]
            for st in dicts(w.get("steps")):
                sid = t(st.get("screen_id"))
                quote = f"\"{mc(st.get('quote'))}\""
                if t(st.get("cause")):
                    quote += f" 원인: {mc(st.get('cause'))}"
                L.append(f"| {mc(m.screen_name(sid))} | {mc(st.get('device'))} | "
                         f"{mc(st.get('design'))} | {mc(st.get('writing'))} | {quote} |")
                fids = strs(st.get("finding_ids"))
                weak = [f"{an} {st.get(k)}" for k, an in AXES if st.get(k) in ("보통", "막힘")]
                if fids and weak:
                    ft = ", ".join(mt(m.finding_by_id[x].get("title")) for x in fids if x in m.finding_by_id)
                    links.append(f"- {mt(p.get('name'))} · {mt(m.screen_name(sid))}: {', '.join(weak)} → {ft}")
            easy = [s for s in strs(w.get("easy_screens")) if (pid, s) not in ut["steps"]]
            if easy:
                L += ["", "나머지는 세 가지 모두 쉬움: " + ", ".join(mc(m.screen_name(s)) for s in easy)]
        if links:
            L += ["", "### 반응에서 나온 지적"] + links

    if m.strengths:
        L += ["", "## 잘 된 점"]
        for st in m.strengths:
            sid = t(st.get("screen_id"))
            tail = f" ({mt(m.screen_name(sid))})" if sid in m.screen_by_id else ""
            L.append(f"- {mt(st.get('note'))}{tail}")
    if m.checks:
        L += ["", "## 확인이 필요한 것"]
        for c in m.checks:
            L.append(f"- {mt(c.get('what'))}: {mt(c.get('how'))}")
    cl = render_checklist(checklist_items(m))
    if cl:
        L += ["", cl]
    return "\n".join(L) + "\n"


# ── 실행 ──

def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise ValueError(f"{os.path.basename(path)} JSON 파싱 실패: {e.lineno}행, {e.msg}")


def build(run, fmt="both", out=None):
    """RUN의 리포트를 만들고 쓴 파일 경로 목록을 돌려준다.
    out은 HTML을 쓸 경로(없으면 RUN/report.html). report.md는 늘 RUN에 쓴다."""
    rev_path = os.path.join(run, "review.json")
    if not os.path.isfile(rev_path):
        raise ValueError(f"review.json이 없어요 ({rev_path}). 샤딩이면 먼저 validate.py를 돌려 합쳐요")
    rev = load_json(rev_path)
    if not isinstance(rev, dict):
        raise ValueError("review.json 최상위는 객체여야 해요")
    cap_path = os.path.join(run, "capture.json")
    cap = load_json(cap_path) if os.path.isfile(cap_path) else {}
    m = Model(rev, cap)
    written = []
    if fmt in ("html", "both"):
        doc, n_img, missing = build_html(m, run)
        p = os.path.expanduser(out) if out else os.path.join(run, "report.html")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(doc)
        written.append(p)
        size = os.path.getsize(p)
        print(f"WROTE {p} ({size // 1024}KB, 내장 이미지 {n_img})")
        if missing:
            print(f"경고: 이미지를 넣지 못한 화면 {len(missing)}개: {', '.join(missing[:5])}. "
                  "shot은 RUN/shots/ 아래 이미지 파일이어야 해요")
        if size > SIZE_WARN_MB * 1024 * 1024:
            print(f"경고: 리포트가 {size // (1024 * 1024)}MB예요. 캡처를 작게 다시 떠 보세요")
    if fmt in ("md", "both"):
        p = os.path.join(run, "report.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(build_md(m))
        written.append(p)
        print(f"WROTE {p}")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="./run")
    ap.add_argument("--format", choices=("html", "md", "both"), default="both")
    ap.add_argument("--out", help="HTML을 쓸 경로. 기본은 RUN/report.html")
    a = ap.parse_args()
    try:
        build(a.run, a.format, out=a.out)
    except (ValueError, OSError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
