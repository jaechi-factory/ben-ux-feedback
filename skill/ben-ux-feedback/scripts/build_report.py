#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 5단계: 리포트 빌드
RUN/review.json(과 선택 ut)을 읽어 단일 HTML(이미지 내장)과 마크다운을 만든다.
review.json은 바꾸지 않는다. 외부 네트워크 요청이 없고 표준 라이브러리만 쓴다.

사용: python3 build_report.py --run ./run [--format html|md|both]
결과: RUN/report.html, RUN/report.md
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

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}
SEV_ORDER = {"심각": 0, "중간": 1, "낮음": 2}
SEV_VIEW = {"심각": ("sev-high", "먼저 고쳐요"), "중간": ("sev-mid", "고치면 좋아요"),
            "낮음": ("sev-low", "여유 있을 때 봐요")}
LV_CLASS = {"쉬움": "lv-ok", "보통": "lv-mid", "막힘": "lv-block"}
AXES = (("device", "디바이스"), ("design", "시안"), ("writing", "라이팅"))
INPUT_LABEL = {"image": "이미지", "figma": "Figma", "live": "라이브 URL"}
WRITING_LABEL = {"ben-ux-writing": "ben-ux-writing 기준",
                 "fallback": "기본 점검 (ben-ux-writing 미적용)"}
SIZE_WARN_MB = 20
TOP_MAX = 3
# 외부 요청이 없다는 것을 브라우저가 강제하게 한다(이미지는 data URI, 스타일과 스크립트는 인라인)
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CASES = os.path.join(HERE, "..", "references", "cases.md")
AGE_KEYS = {"청년": "youth", "중년": "mid", "노년": "senior"}
AGE_ALT = {"청년": "청년 사용자", "중년": "중년 사용자", "노년": "노년 사용자"}


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


def pin_xy(f):
    p = f.get("pin")
    if not isinstance(p, dict):
        return None
    x, y = p.get("x"), p.get("y")
    for v in (x, y):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
    return min(max(x, 0), 1), min(max(y, 0), 1)


def sev_key(f):
    return SEV_ORDER.get(f.get("severity"), 3)


def load_case_index(path=None):
    """cases.md에서 {C###: (제목, 출처 URL 또는 "")}을 읽는다. 파일이 없거나 깨져도 빈 표를 돌려준다."""
    try:
        with open(path or DEFAULT_CASES, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    index = {}
    for block in re.split(r"^(?=###\s+C\d{3}\b)", text, flags=re.M):
        head = re.match(r"###\s+(C\d{3})\.?\s*(.*)", block)
        if not head:
            continue
        url = re.search(r"^출처:.*?(https://[^\s)]+)", block, re.M)
        index[head.group(1)] = (head.group(2).strip(), url.group(1) if url else "")
    return index


def persona_line(p):
    """누구의 말인지 한 줄로: 노년 · 디바이스 하 · UX 이해도 중"""
    return f'{t(p.get("age_group"))} · 디바이스 {t(p.get("device_level"))} · UX 이해도 {t(p.get("ux_level"))}'


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

    def __init__(self, rev, cap, cases=None):
        self.cases = cases if isinstance(cases, dict) else {}
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
        def in_screen(f):
            return f.get("lens") != "흐름" and isinstance(f.get("screen_id"), str) and bool(f["screen_id"])

        self.flow = [f for f in self.findings if not in_screen(f)]
        self.flow.sort(key=sev_key)
        self.by_screen = {}
        for f in self.findings:
            if in_screen(f):
                self.by_screen.setdefault(f["screen_id"], []).append(f)
        for lst in self.by_screen.values():
            lst.sort(key=sev_key)
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
        reached = {sid for (_pid, sid) in steps}
        cols = [s for s in self.screens if t(s.get("id")) in reached]
        by_finding = {}   # finding id -> [persona id]
        known = {t(p.get("id")) for p in personas}
        for (pid, _sid), st in steps.items():
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
        return {"personas": personas, "walks": walks, "steps": steps, "cols": cols,
                "by_finding": by_finding, "step_for": step_for,
                "persona_by_id": {t(p["id"]): p for p in personas}}

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
--blue-50:#E8F3FF;--blue-500:#3182F6;--blue-700:#1B64DA;--blue-800:#1957C2;
--red-50:#FFEEEE;--red-500:#F04452;--red-800:#BC1B2A;
--orange-50:#FFF3E0;--orange-500:#FE9800;
--yellow-50:#FFF9E7;--yellow-200:#FFE69B;
--teal-50:#EDF8F8;--teal-700:#0C8585;
--green-50:#F0FAF6;--green-500:#03B26C;--green-900:#027648;
--accent:var(--blue-700);--accent-soft:var(--blue-50);--focus:var(--blue-500);
--font-sans:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
--t1:30px;--t2:26px;--t3:22px;--t4:20px;--t5:17px;--t6:15px;--t7:13px;
--lh-title:1.5;--lh-body:1.65;
}
"""

STACK_TMPL = """
&{display:block}
& thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
& tbody,& tr,& th,& td{display:block;width:100%}
& tr{margin-top:24px;padding:20px;border:1px solid var(--grey-200);border-radius:16px}
& th{padding:0 0 16px;border:0}
& td{padding:16px 0 0;border:0;border-top:1px solid var(--grey-200)}
& td+td{margin-top:16px}
& td::before{content:attr(data-label);display:block;margin-bottom:8px;font-size:var(--t6);font-weight:700;color:var(--grey-900)}
"""


def stack_css(prefix):
    return STACK_TMPL.replace("&", prefix)


CSS_BASE = """
*{box-sizing:border-box;margin:0}
html{-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
body{background:#FFFFFF;color:var(--grey-800);font-family:var(--font-sans);font-size:var(--t5);line-height:var(--lh-body);word-break:keep-all;overflow-wrap:anywhere;-webkit-font-smoothing:antialiased}
.wrap{max-width:880px;margin:0 auto;padding:64px 24px 72px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:16px;top:-64px;background:var(--grey-900);color:#FFFFFF;padding:12px 16px;border-radius:12px;z-index:10}
.skip:focus{top:16px}
a{color:var(--accent);text-underline-offset:3px}
a:hover{color:var(--blue-800)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
h1,h2,h3,h4{color:var(--grey-900);line-height:var(--lh-title)}
h1{font-size:var(--t1);font-weight:700}
h2{font-size:var(--t2);font-weight:700}
h3{font-size:var(--t3);font-weight:700}
h4{font-size:var(--t5);font-weight:700}
ul,ol{padding-left:24px}
.kicker{font-size:var(--t6);font-weight:700;color:var(--accent);margin-bottom:8px}
.lead{margin-top:8px;color:var(--grey-700)}
.block{margin-top:72px}
.block>h2+*{margin-top:16px}

.hero h1{margin-top:0}
.stats{list-style:none;padding:0;margin-top:32px;display:flex;flex-wrap:wrap;gap:4px 24px;font-size:var(--t6);color:var(--grey-700)}
.stats b{color:var(--grey-900)}
.meta{margin-top:24px;padding:24px;background:var(--grey-50);border-radius:16px;display:grid;gap:8px;font-size:var(--t6);color:var(--grey-700)}
.meta div{display:flex;flex-wrap:wrap;gap:8px}
.meta dt{font-weight:700;color:var(--grey-900)}
.meta dd{margin:0}
.top-fix{margin-top:40px;padding:24px;border:1px solid var(--grey-200);border-radius:16px}
.top-fix h2{font-size:var(--t4)}
.top-fix ol{margin-top:16px;padding-left:0;list-style:none;display:grid;gap:16px;counter-reset:top}
.top-fix li{display:grid;gap:4px;padding-left:40px;position:relative;counter-increment:top}
.top-fix li::before{content:counter(top);position:absolute;left:0;top:2px;width:24px;height:24px;border-radius:50%;background:var(--grey-900);color:#FFFFFF;font-size:var(--t7);line-height:24px;font-weight:700;text-align:center}
.top-fix a{font-size:var(--t5);font-weight:700}
.top-sub{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;font-size:var(--t6);color:var(--grey-700)}
.tools{margin-top:24px;display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.fallback{display:block;width:100%;margin-top:12px;min-height:160px;padding:16px;border:1px solid var(--grey-600);border-radius:12px;font:inherit;font-size:var(--t6);color:var(--grey-900);background:#FFFFFF}
.jump{margin-top:32px;display:flex;flex-wrap:wrap;gap:8px 24px;font-size:var(--t6)}
.filters{margin-top:32px;display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding-top:24px;border-top:1px solid var(--grey-200)}
.filters .flabel{font-size:var(--t6);font-weight:700;color:var(--grey-900)}
.chipbtn{font:inherit;font-size:var(--t6);min-height:44px;padding:0 16px;border-radius:999px;border:1px solid var(--grey-600);background:#FFFFFF;color:var(--grey-800);cursor:pointer}
.chipbtn b{margin-left:8px}
.chipbtn:hover:not(:disabled){background:var(--grey-100)}
.chipbtn[aria-pressed="true"]{background:var(--grey-900);border-color:var(--grey-900);color:#FFFFFF}
.chipbtn:disabled{opacity:.4;cursor:default}
.filters:focus{outline:none}

.badge{display:inline-flex;align-items:center;gap:8px;padding:4px 12px;border-radius:999px;font-size:var(--t6);line-height:var(--lh-body);font-weight:500;background:var(--grey-100);color:var(--grey-700)}
.badge::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor;flex:none}
.sev-high{background:var(--red-50);color:var(--red-800);font-weight:700}
.sev-mid{background:var(--orange-50);color:var(--grey-900);font-weight:700}
.sev-mid::before{background:var(--orange-500)}
.sev-low{background:var(--grey-100);color:var(--grey-700)}
.tag{display:inline-block;padding:4px 12px;border-radius:999px;font-size:var(--t6);background:var(--accent-soft);color:var(--blue-800)}
.tag.plain{background:var(--grey-100);color:var(--grey-700)}

.screen{margin-top:64px}
.screen:first-of-type{margin-top:32px}
.screen.hidden,.hidden{display:none!important}
.screen-head{display:flex;gap:32px;align-items:flex-start}
.thumb{flex:0 0 200px}
.pinbox{position:relative;display:block}
.pinbox img{display:block;width:100%;height:auto;border:1px solid var(--grey-300);border-radius:16px;background:var(--grey-50)}
.pin{position:absolute;width:24px;height:24px;margin:-12px 0 0 -12px;border-radius:50%;background:var(--accent);color:#FFFFFF;font-size:var(--t7);line-height:24px;font-weight:700;text-align:center;box-shadow:0 0 0 2px #FFFFFF}
.noimg{padding:24px;border:1px dashed var(--grey-400);border-radius:16px;text-align:center;color:var(--grey-700);font-size:var(--t6)}
.screen-info{flex:1;min-width:0}
.screen-info h3{margin:0}
.screen-info p{margin-top:8px}
.screen-info .sub{font-size:var(--t6);color:var(--grey-700)}
.actions{margin-top:24px;display:flex;flex-wrap:wrap;gap:12px}
.btn{font:inherit;font-size:var(--t6);font-weight:500;min-height:44px;padding:0 16px;border-radius:12px;border:1px solid var(--grey-600);background:#FFFFFF;color:var(--grey-800);cursor:pointer}
.btn:hover{background:var(--grey-100)}
.btn.resolve{border-color:var(--green-900);color:var(--green-900)}
.when-done{display:none}
.screen.cls-resolve .when-open,.screen.cls-dismiss .when-open{display:none}
.screen.cls-resolve .when-done,.screen.cls-dismiss .when-done{display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.done-dismiss{display:none}
.screen.cls-dismiss .done-dismiss{display:inline-block}
.screen.cls-dismiss .done-resolve{display:none}

.cards{margin-top:32px;display:grid;gap:24px}
.card{padding:24px;border:1px solid var(--grey-200);border-left-width:4px;border-radius:16px;scroll-margin-top:24px}
.card.c-sev-high{border-left-color:var(--red-500)}
.card.c-sev-mid{border-left-color:var(--orange-500)}
.card.c-sev-low{border-left-color:var(--grey-400)}
.card-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.num{display:inline-block;width:24px;height:24px;border-radius:50%;background:var(--accent);color:#FFFFFF;font-size:var(--t7);line-height:24px;font-weight:700;text-align:center}
.fid{font-size:var(--t7);color:var(--grey-700)}
.card h3,.card h4.title{margin-top:16px;font-size:var(--t4)}
.part{margin-top:24px;padding-top:24px;border-top:1px solid var(--grey-200)}
.card h4.title+.part{margin-top:16px;padding-top:0;border-top:0}
.part h5{font-size:var(--t6);line-height:var(--lh-title);font-weight:700;color:var(--grey-900)}
.part p{margin-top:8px}
.part h5+p{margin-top:4px}
.part .where{font-size:var(--t6);color:var(--grey-700)}
.part .where b{color:var(--grey-900)}
.chips{margin-top:8px;display:flex;flex-wrap:wrap;gap:8px}
.chips .tag{margin:0}
.chips a.tag{text-decoration:none}
.chips a.tag:hover{text-decoration:underline}
.done{padding:16px;border-radius:12px;background:var(--green-50);color:var(--grey-900)}
.done h5{color:var(--green-900)}
.reacts{margin-top:16px}
.reacts .vflag{margin-top:0}
.bubbles{list-style:none;padding:0;margin-top:12px;display:grid;gap:12px}
.bubble{display:flex;gap:12px;align-items:flex-start}
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
.bub{flex:1;min-width:0;padding:12px 16px;border-radius:4px 16px 16px 16px;background:var(--grey-100)}
.who{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 8px;font-size:var(--t6);color:var(--grey-700)}
.who b{color:var(--grey-900)}
.say{margin-top:4px;color:var(--grey-900)}
.vflag{display:inline-block;margin-top:8px;padding:4px 12px;border:1px dashed var(--grey-600);border-radius:999px;background:var(--grey-50);color:var(--grey-900);font-size:var(--t6);font-weight:700}
.fix p{margin-top:4px}
.copyrow{margin-top:12px}
.btn.small{min-height:44px;font-size:var(--t6)}
.ab{margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.ab.single{grid-template-columns:1fr}
.ab>div{padding:16px;border-radius:12px}
.ab .was{background:var(--grey-100)}
.ab .now{background:var(--accent-soft)}
.ab .abk{display:block;font-size:var(--t6);font-weight:700;color:var(--grey-900)}
.ab p{margin-top:4px}
.foot{margin-top:24px;display:grid;gap:8px;font-size:var(--t6);color:var(--grey-700)}
.foot b{color:var(--grey-900)}
.react{margin-top:16px;font-size:var(--t6);color:var(--grey-700)}
.clean{margin-top:64px;padding:24px;background:var(--grey-50);border-radius:16px;font-size:var(--t6);color:var(--grey-700)}
.clean b{color:var(--grey-900)}
.empty{margin-top:32px;padding:24px;background:var(--grey-50);border-radius:16px;color:var(--grey-700)}

.ut-flag{display:inline-block;margin-top:16px;padding:8px 16px;border:1px dashed var(--grey-600);border-radius:12px;background:var(--grey-50);color:var(--grey-900);font-size:var(--t6);font-weight:700}
.personas{margin-top:32px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;padding:0;list-style:none}
.persona{padding:24px;border:1px solid var(--grey-200);border-radius:16px;scroll-margin-top:24px}
.persona h3{font-size:var(--t4);margin:0}
.persona .row1{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.persona p{margin-top:12px;font-size:var(--t6)}
.levels{list-style:none;padding:0;margin-top:12px;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:var(--t6);color:var(--grey-700)}
.levels b{color:var(--grey-900)}
.outcome{padding:12px 16px;border-radius:12px;background:var(--grey-100);color:var(--grey-900)}
.outcome.done{background:var(--green-50)}
.outcome.stop{background:var(--red-50)}
.ut-wrap h3.tbl{margin-top:48px;font-size:var(--t4)}
.ut-table{margin-top:16px;width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;font-size:var(--t6)}
.ut-table caption{text-align:left;color:var(--grey-700);padding-bottom:8px}
.ut-table th,.ut-table td{padding:16px;vertical-align:top;text-align:left;border-top:1px solid var(--grey-200)}
.ut-table thead th{font-weight:700;color:var(--grey-900);border-top:0;border-bottom:1px solid var(--grey-300)}
.ut-table tbody th{font-weight:700;color:var(--grey-900)}
.ut-table tbody th small{display:block;font-weight:400;color:var(--grey-700)}
.rowhead{display:flex;gap:12px;align-items:flex-start}
.axes{list-style:none;padding:0;display:grid;gap:4px}
.axes li{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}
.axes .an{color:var(--grey-700);min-width:56px}
.lv{display:inline-flex;align-items:center;gap:8px;color:var(--grey-900)}
.lv i{display:inline-block;width:12px;height:12px;flex:none}
.lv-ok i{border-radius:50%;background:var(--green-500)}
.lv-mid i{background:var(--orange-500);transform:rotate(45deg);width:10px;height:10px}
.lv-block i{border-radius:2px;background:var(--red-500)}
.lv-block{font-weight:700}
.quote{margin-top:12px;color:var(--grey-900)}
.cause,.links,.skipped{margin-top:8px;color:var(--grey-700)}
.skipped{color:var(--grey-700)}
.legend{margin-top:16px;display:flex;flex-wrap:wrap;gap:8px 24px;font-size:var(--t6);color:var(--grey-700)}
.plain-list{margin-top:16px;display:grid;gap:12px;list-style:none;padding:0}
.plain-list li{padding-left:0}
.checks{margin-top:16px;display:grid;gap:16px}
.checks dt{font-weight:700;color:var(--grey-900)}
.checks dd{margin:4px 0 0}

@media (max-width:720px){
.wrap{padding:48px 20px 64px}
h1{font-size:var(--t2)}
.screen-head{flex-direction:column;gap:24px}
.thumb{flex:none;width:200px;max-width:100%}
.ab{grid-template-columns:1fr}
.card{padding:20px}
.stats{gap:24px}
}
"""

CSS = CSS_VARS + CSS_BASE + "@media (max-width:720px){" + stack_css(".ut-table") + "}" + stack_css(".ut-table.stack")

JS = r"""
(function(){
var KEY=document.body.getAttribute('data-key')||'bf-cls',cls={},reveal={resolve:false,dismiss:false};
try{cls=JSON.parse(localStorage.getItem(KEY)||'{}')||{};}catch(e){cls={};}
function save(){try{localStorage.setItem(KEY,JSON.stringify(cls));}catch(e){}}
var screens=[].slice.call(document.querySelectorAll('.screen'));
var live=document.getElementById('live'),bar=document.getElementById('filters');
function apply(){
  var n={resolve:0,dismiss:0};
  screens.forEach(function(s){var c=cls[s.getAttribute('data-sid')];if(c==='resolve'||c==='dismiss')n[c]++;});
  ['resolve','dismiss'].forEach(function(k){
    if(!n[k])reveal[k]=false;
    var b=document.querySelector('[data-chip="'+k+'"]');
    if(!b)return;
    b.disabled=!n[k];b.setAttribute('aria-pressed',reveal[k]?'true':'false');
    b.querySelector('b').textContent=n[k];
  });
  var any=reveal.resolve||reveal.dismiss,shown=0;
  screens.forEach(function(s){
    var c=cls[s.getAttribute('data-sid')];if(c!=='resolve'&&c!=='dismiss')c=null;
    var show=any?!!(c&&reveal[c]):!c;
    s.classList.toggle('hidden',!show);
    s.classList.toggle('cls-resolve',c==='resolve');
    s.classList.toggle('cls-dismiss',c==='dismiss');
    if(show)shown++;
  });
  var e=document.getElementById('all-cleared');
  if(e)e.classList.toggle('hidden',shown>0||!screens.length);
  var cl=document.querySelector('.clean');if(cl)cl.classList.toggle('hidden',any);
}
function say(m){if(live)live.textContent=m;}
function park(){if(bar)bar.focus({preventScroll:true});}
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
  var out=items.filter(function(it){var c=it.sid?cls[it.sid]:null;return c!=='resolve'&&c!=='dismiss';})
    .map(function(it){return it.text;});
  return out.length?'## 남은 지적 '+out.length+'개\n\n'+out.join('\n'):'';
}
document.addEventListener('click',function(ev){
  var cb=ev.target.closest&&ev.target.closest('button[data-copy]');
  if(cb){
    var tid=cb.getAttribute('data-copy');
    if(tid==='checklist'){
      var txt=checklist(),fb=document.getElementById('cl-fallback');
      if(!txt){say('남은 지적이 없어요');return;}
      fb.value=txt;
      copyText(txt,cb,function(){fb.classList.remove('hidden');fb.focus();return fb;});
    }else{
      var src=document.getElementById(tid);if(!src)return;
      copyText(src.textContent.trim(),cb,function(){return src;});
    }
    return;
  }
  var b=ev.target.closest&&ev.target.closest('button[data-act]');
  if(b){
    var s=b.closest('.screen');if(!s)return;
    var sid=s.getAttribute('data-sid'),act=b.getAttribute('data-act'),nm=s.getAttribute('data-name');
    if(act==='undo'){delete cls[sid];say(nm+' 화면을 다시 보이게 했어요');}
    else{cls[sid]=act;say(nm+(act==='resolve'?' 화면을 해결됨으로 옮겼어요':' 화면을 문제 아님으로 옮겼어요'));}
    save();apply();park();return;
  }
  var c=ev.target.closest&&ev.target.closest('button[data-chip]');
  if(c){var k=c.getAttribute('data-chip');reveal[k]=!reveal[k];apply();return;}
  var a=ev.target.closest&&ev.target.closest('a[href^="#"]');
  if(a){
    var el=document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));
    var sc=el&&el.closest('.screen');
    if(sc&&sc.classList.contains('hidden')){
      var cc=cls[sc.getAttribute('data-sid')];if(cc){reveal[cc]=true;apply();}
    }
  }
});
apply();
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


def sev_badge(sev):
    cls, hint = SEV_VIEW.get(sev, ("sev-low", ""))
    label = esc(sev) if sev in SEV_VIEW else "낮음"
    h = f" · {hint}" if hint else ""
    return f'<span class="badge {cls}">{label}{h}</span>'


def finding_link(m, fid):
    """지적 id를 카드 링크로. 카드가 없으면 글자만."""
    f = m.finding_by_id.get(fid)
    if f is None:
        return esc(fid)
    return f'<a href="#f-{slug(fid)}">{esc(fid)}</a>'


def render_card(m, f, num):
    fid = t(f.get("id"))
    sev = f.get("severity")
    cls = SEV_VIEW.get(sev, ("sev-low",))[0]
    top = []
    if num:
        top.append(f'<span class="num" aria-hidden="true">{num}</span>')
    top.append(sev_badge(sev))
    top.append(f'<span class="tag plain">{esc(f.get("lens"))}</span>')
    if fid:
        top.append(f'<span class="fid">{esc(fid)}</span>')
    if m.ut and (f.get("from_ut") or []):
        top.append('<span class="tag">가상 사용자 반응에서 나왔어요</span>')
    ev = f.get("evidence") if isinstance(f.get("evidence"), dict) else {}
    if ev.get("type") in ("console", "dom"):
        top.append(f'<span class="tag plain">보조 근거 · {"콘솔" if ev["type"] == "console" else "DOM"}</span>')

    # 메이커가 움직이는 순서: ① 무엇이 문제인가 ② 사용자에게 생기는 일 ③ 이렇게 고쳐요 ④ 근거 ⑤ 확인 기준
    sid = t(f.get("screen_id"))
    where = ""
    if t(ev.get("where")):
        place = f'{esc(m.screen_name(sid))} · ' if sid in m.screen_by_id else ""
        where = f'<p class="where"><b>화면 위치</b> {place}{esc(ev.get("where"))}</p>'
    obs = f'<p>{esc(f.get("observation"))}</p>' if t(f.get("observation")) else ""
    p1 = f'<section class="part"><h5>무엇이 문제인가</h5>{obs}{where}</section>' if obs or where else ""

    why = f'<p>{esc(f.get("why"))}</p>' if t(f.get("why")) else ""
    reacts = render_reactions(m, fid)
    p2 = f'<section class="part"><h5>사용자에게 생기는 일</h5>{why}{reacts}</section>' if why or reacts else ""

    p3 = ""
    asis, tobe = t(f.get("asis")), t(f.get("tobe"))
    if t(f.get("fix")) or asis or tobe:
        ab = ""
        if asis or tobe:
            boxes = ""
            if asis:
                boxes += f'<div class="was"><span class="abk">수정 전</span><p>{esc(asis)}</p></div>'
            if tobe:
                tid = f"tobe-{slug(fid)}"
                boxes += (f'<div class="now"><span class="abk">수정 후</span><p id="{tid}">{esc(tobe)}</p>'
                          f'<div class="copyrow"><button type="button" class="btn small" data-copy="{tid}" '
                          f'aria-label="{esc(fid)} 수정 후 문구 복사">복사</button></div></div>')
            ab = f'<div class="ab{"" if asis and tobe else " single"}">{boxes}</div>'
        fixp = f'<p>{esc(f.get("fix"))}</p>' if t(f.get("fix")) else ""
        p3 = f'<section class="part"><h5>이렇게 고쳐요</h5>{fixp}{ab}</section>'

    chips = []
    if t(f.get("principle")):
        chips.append(f'<span class="tag">{esc(f.get("principle"))}</span>')
    chips.append(case_chip(m, f))
    chips = [c for c in chips if c]
    conf = f'<p>화면만으로는 확인하지 못한 것: {esc(f.get("confirm_needed"))}</p>' if t(f.get("confirm_needed")) else ""
    chip_html = f'<div class="chips">{"".join(chips)}</div>' if chips else ""
    p4 = f'<section class="part"><h5>근거</h5>{chip_html}{conf}</section>' if chips or conf else ""

    p5 = (f'<section class="part done"><h5>고쳤는지 확인하는 기준</h5><p>{esc(f.get("done_when"))}</p></section>'
          if t(f.get("done_when")).strip() else "")

    return (f'<article class="card c-{cls}" id="f-{slug(fid)}" data-fid="{esc(fid)}">'
            f'<div class="card-top">{"".join(top)}</div>'
            f'<h4 class="title">{esc(f.get("title"))}</h4>{p1}{p2}{p3}{p4}{p5}</article>')


def case_chip(m, f):
    """사례 번호 칩. cases.md에서 출처 URL을 찾으면 링크로, 못 찾으면 글자만. 번호가 없으면 빈 문자열."""
    c = t(f.get("case"))
    if not c:
        return ""
    title, url = m.cases.get(c, ("", ""))
    label = f"사례 {c}" + (f" · {title}" if title else "")
    if url.startswith("https://"):
        return (f'<a class="tag plain" href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}'
                f'<span class="sr"> (새 탭에서 열려요)</span></a>')
    return f'<span class="tag plain">{esc(label)}</span>'


def render_reactions(m, fid):
    """지적에 이어진 가상 사용자 반응을 아이콘과 한마디로. 연결된 반응이 없으면 빈 문자열."""
    if not m.ut:
        return ""
    items = []
    for pid in m.ut["by_finding"].get(fid, []):
        p = m.ut["persona_by_id"].get(pid)
        if not p:
            continue
        st = m.ut["step_for"].get((fid, pid))
        say = f'<p class="say">“{esc(st.get("quote"))}”</p>' if st and t(st.get("quote")) else ""
        items.append(
            f'<li class="bubble">{avatar(p.get("age_group"), True)}<div class="bub"><p class="who">'
            f'<b><a href="#ut-p-{slug(pid)}">{esc(p.get("name"))}</a></b>'
            f'<span>{esc(persona_line(p))}</span></p>{say}</div></li>')
    if not items:
        return ""
    return ('<div class="reacts"><p class="vflag">가상 사용자 반응 · 실제 조사 아님</p>'
            f'<ul class="bubbles">{"".join(items)}</ul></div>')


def render_screen(m, run, s, items, embedded, missing):
    sid = t(s.get("id"))
    name = m.screen_name(sid)
    path = safe_shot(run, s.get("shot"))
    pins, nums = [], {}
    for i, f in enumerate(items, 1):
        xy = pin_xy(f)
        if path and xy:
            nums[id(f)] = i
            pins.append(f'<span class="pin" aria-hidden="true" style="left:{xy[0] * 100:.1f}%;top:{xy[1] * 100:.1f}%">{i}</span>')
    if path:
        embedded.append(path)
        img = (f'<span class="pinbox"><img src="{data_uri(path)}" alt="{esc(name)} 화면 시안">'
               f'{"".join(pins)}</span>')
    else:
        missing.append(name)
        img = '<div class="noimg">이미지를 불러오지 못했어요</div>'
    cards = "".join(render_card(m, f, nums.get(id(f))) for f in items)
    sub = []
    if t(s.get("screen_goal")):
        sub.append(f'<p class="sub">화면 목표: {esc(s.get("screen_goal"))}</p>')
    if t(s.get("verdict")):
        sub.append(f'<p>{esc(s.get("verdict"))}</p>')
    return (f'<article class="screen" id="sec-{slug(sid)}" data-sid="{esc(slug(sid))}" data-name="{esc(name)}">'
            f'<div class="screen-head"><div class="thumb">{img}</div>'
            f'<div class="screen-info"><h3>{esc(name)}</h3>{"".join(sub)}'
            f'<div class="actions when-open">'
            f'<button type="button" class="btn resolve" data-act="resolve">문제를 해결했어요</button>'
            f'<button type="button" class="btn" data-act="dismiss">문제가 아니에요</button></div>'
            f'<div class="actions when-done"><span class="tag plain"><span class="done-resolve">해결했어요</span>'
            f'<span class="done-dismiss">문제가 아니라고 했어요</span></span>'
            f'<button type="button" class="btn" data-act="undo">되돌리기</button></div>'
            f'</div></div><div class="cards">{cards}</div></article>')


def render_ut(m):
    ut = m.ut
    out = ['<section class="block ut-wrap" id="ut" aria-labelledby="h-ut"><h2 id="h-ut">가상 사용자 반응</h2>'
           '<span class="ut-flag">가상 사용자 반응 · 실제 조사 아님</span>'
           '<p class="lead">화면 이미지를 보고 추론한 반응이에요. 점수나 비율은 만들지 않았어요.</p>']
    cards = []
    for p in ut["personas"]:
        pid = t(p["id"])
        w = ut["walks"].get(pid, {})
        if w.get("outcome") == "이탈":
            where = m.screen_name(t(w.get("stopped_at")))
            out_html = (f'<p class="outcome stop"><b>이탈</b> · {esc(where)}에서 멈췄어요. '
                        f'{esc(w.get("stop_reason"))}</p>')
        elif w.get("outcome") == "완주":
            out_html = '<p class="outcome done"><b>완주</b> · 끝까지 걸었어요</p>'
        else:
            out_html = ""
        cards.append(
            f'<li class="persona" id="ut-p-{slug(pid)}"><div class="row1">{avatar(p.get("age_group"), True)}<h3>{esc(p.get("name"))}</h3>'
            f'<span class="tag">{esc(p.get("age_group"))}</span></div>'
            f'<ul class="levels"><li>디바이스 적응도 <b>{esc(p.get("device_level"))}</b></li>'
            f'<li>UX 이해도 <b>{esc(p.get("ux_level"))}</b></li></ul>'
            f'<p>{esc(p.get("traits"))}</p>'
            + (f'<p>목표: {esc(p.get("goal"))}</p>' if t(p.get("goal")) else "")
            + out_html + '</li>')
    out.append(f'<ul class="personas">{"".join(cards)}</ul>')

    cols = ut["cols"]
    out.append('<h3 class="tbl">페르소나 × 화면</h3>'
               '<p class="legend"><span class="lv lv-ok"><i></i>쉬움</span>'
               '<span class="lv lv-mid"><i></i>보통</span><span class="lv lv-block"><i></i>막힘</span>'
               '<span>세 가지를 디바이스, 시안, 라이팅 순서로 보여요</span></p>')
    head = "".join(f'<th scope="col" role="columnheader">{esc(m.screen_name(t(c.get("id"))))}</th>' for c in cols)
    body = []
    for p in ut["personas"]:
        pid = t(p["id"])
        w = ut["walks"].get(pid, {})
        tds = []
        for c in cols:
            sid = t(c.get("id"))
            label = esc(m.screen_name(sid))
            st = ut["steps"].get((pid, sid))
            if st is None:
                tds.append(f'<td role="cell" data-label="{label}"><p class="skipped">걷지 않았어요</p></td>')
                continue
            lis = []
            for key, an in AXES:
                v = st.get(key)
                lc = LV_CLASS.get(v, "")
                lis.append(f'<li><span class="an">{an}</span>'
                           f'<span class="lv {lc}"><i aria-hidden="true"></i>{esc(v)}</span></li>')
            cell = f'<ul class="axes">{"".join(lis)}</ul>'
            if w.get("outcome") == "이탈" and t(w.get("stopped_at")) == sid:
                cell += '<p class="links"><span class="tag plain">여기서 멈췄어요</span></p>'
            cell += f'<p class="quote">“{esc(st.get("quote"))}”</p>'
            if t(st.get("cause")):
                cell += f'<p class="cause">원인: {esc(st.get("cause"))}</p>'
            fids = strs(st.get("finding_ids"))
            if fids:
                cell += f'<p class="links">이어진 지적: {" · ".join(finding_link(m, x) for x in fids)}</p>'
            tds.append(f'<td role="cell" data-label="{label}">{cell}</td>')
        body.append(f'<tr role="row"><th scope="row" role="rowheader"><div class="rowhead">{avatar(p.get("age_group"), True)}<div>{esc(p.get("name"))}'
                    f'<small>{esc(persona_line(p))}</small></div></div></th>'
                    f'{"".join(tds)}</tr>')
    stack = " stack" if len(cols) > 3 else ""
    # 모바일에서 display:block으로 쌓아도 표 의미가 남도록 role을 명시한다
    out.append(f'<table class="ut-table{stack}" role="table"><caption>가상 반응이에요. 실제 사용자 조사가 아니에요</caption>'
               f'<thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">페르소나</th>{head}</tr></thead>'
               f'<tbody role="rowgroup">{"".join(body)}</tbody></table>')
    out.append('</section>')
    return "".join(out)


def build_html(m, run):
    n_screens, n_find, n_sev = m.counts()
    headline = t(m.summary.get("headline")) or "UX 검토 결과"
    embedded, missing = [], []

    key_src = headline + "|" + ",".join(sorted(m.finding_by_id)) + "|" + ",".join(sorted(m.screen_by_id))
    key = "bf-cls-" + hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:10]

    meta = []
    src = m.cap.get("source") if isinstance(m.cap.get("source"), dict) else {}
    if t(src.get("name")):
        meta.append(("검토 대상", esc(src.get("name"))))
    meta.append(("입력 방식", esc(label_of(INPUT_LABEL, m.run.get("input_type")) or "알 수 없음")))
    meta.append(("문구 판정 방식", esc(label_of(WRITING_LABEL, m.run.get("writing_judge")) or "알 수 없음")))
    if t(m.run.get("product_value")):
        meta.append(("제품 핵심 가치", esc(m.run.get("product_value"))))
    if t(m.run.get("goal")):
        meta.append(("검토 목표", esc(m.run.get("goal"))))
    meta_html = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in meta)

    top = []
    for f in top_findings(m):
        fid = t(f.get("id"))
        sid = t(f.get("screen_id"))
        where = esc(m.screen_name(sid)) if sid in m.screen_by_id and f.get("lens") != "흐름" else "여러 화면에 걸친 흐름"
        top.append(f'<li><a href="#f-{slug(fid)}">{esc(f.get("title"))}</a>'
                   f'<span class="top-sub">{sev_badge(f.get("severity"))}<span>{where}</span>'
                   f'<span class="fid">{esc(fid)}</span></span></li>')
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
    shown_screens = [s for s in m.screens if m.by_screen.get(t(s.get("id")))]
    if shown_screens:
        jumps.append('<a href="#screens">화면별 지적</a>')
    if m.flow:
        jumps.append('<a href="#flow">빠진 흐름·분기</a>')
    if m.ut:
        jumps.append('<a href="#ut">가상 사용자 반응</a>')
    if m.strengths:
        jumps.append('<a href="#strengths">잘 된 점</a>')
    if m.checks:
        jumps.append('<a href="#checks">확인 필요</a>')
    jump_html = f'<nav class="jump" aria-label="리포트 목차">{"".join(jumps)}</nav>' if jumps else ""

    filters = ('<div class="filters" id="filters" tabindex="-1" role="group" aria-label="정리한 화면 보기">'
               '<span class="flabel">정리한 화면</span>'
               '<button type="button" class="chipbtn" data-chip="resolve" aria-pressed="false" disabled>해결됨<b>0</b></button>'
               '<button type="button" class="chipbtn" data-chip="dismiss" aria-pressed="false" disabled>문제 아님<b>0</b></button>'
               '</div>') if shown_screens else ""

    header = (f'<header class="hero"><p class="kicker">UX 검토 결과</p><h1>{esc(headline)}</h1>'
              f'{top_html}{tools_html}'
              f'<ul class="stats"><li>화면 <b>{n_screens}</b>개</li><li>지적 <b>{n_find}</b>개</li>'
              f'<li>심각 <b>{n_sev}</b>개</li></ul>'
              f'<dl class="meta">{meta_html}</dl>{jump_html}{filters}</header>')

    parts = [header]

    if shown_screens:
        sec = ['<section class="block" id="screens" aria-labelledby="h-screens"><h2 id="h-screens">화면별 지적</h2>'
               '<p class="lead">화면마다 심각한 것부터 보여요. 정리한 화면은 숨기고, 이 브라우저에만 기억해요.</p>']
        for s in shown_screens:
            sec.append(render_screen(m, run, s, m.by_screen[t(s.get("id"))], embedded, missing))
        sec.append('<p class="empty hidden" id="all-cleared">모든 화면을 정리했어요. 위 칩을 눌러 다시 볼 수 있어요.</p>')
        clean = [m.screen_name(t(s.get("id"))) for s in m.screens if not m.by_screen.get(t(s.get("id")))]
        if clean:
            sec.append(f'<p class="clean"><b>화면 안 지적이 없는 화면 {len(clean)}개</b> · {esc(" · ".join(clean))}</p>')
        sec.append('</section>')
        parts.append("".join(sec))
    elif m.screens:
        names = [m.screen_name(t(s.get("id"))) for s in m.screens]
        parts.append(f'<p class="clean block"><b>화면 안 지적이 없어요</b> · {esc(" · ".join(names))}</p>')

    if m.flow:
        cards = []
        for f in m.flow:
            where = ""
            sid = t(f.get("screen_id"))
            if sid and sid in m.screen_by_id:
                nm = esc(m.screen_name(sid))
                where = (f'<p class="react">시작 화면: <a href="#sec-{slug(sid)}">{nm}</a></p>'
                         if m.by_screen.get(sid) else f'<p class="react">시작 화면: {nm}</p>')
            cards.append(render_card(m, f, None).replace("</article>", where + "</article>"))
        parts.append('<section class="block" id="flow" aria-labelledby="h-flow"><h2 id="h-flow">빠진 흐름·분기</h2>'
                     '<p class="lead">화면과 화면 사이, 화면 밖에 있는 빈틈이에요.</p>'
                     f'<div class="cards">{"".join(cards)}</div></section>')

    if m.ut:
        parts.append(render_ut(m))

    if m.strengths:
        lis = []
        for st in m.strengths:
            tail = [esc(st.get("principle"))] if t(st.get("principle")) else []
            sid = t(st.get("screen_id"))
            if sid in m.screen_by_id:
                tail.append(esc(m.screen_name(sid)))
            extra = f' <span class="fid">{" · ".join(tail)}</span>' if tail else ""
            lis.append(f"<li>{esc(st.get('note'))}{extra}</li>")
        parts.append('<section class="block" id="strengths" aria-labelledby="h-str"><h2 id="h-str">잘 된 점</h2>'
                     f'<ul class="plain-list">{"".join(lis)}</ul></section>')

    if m.checks:
        items = "".join(f"<div><dt>{esc(c.get('what'))}</dt><dd>{esc(c.get('how'))}</dd></div>" for c in m.checks)
        parts.append('<section class="block" id="checks" aria-labelledby="h-chk"><h2 id="h-chk">확인 필요</h2>'
                     '<p class="lead">화면만으로는 알 수 없어서 남겨 둔 것이에요.</p>'
                     f'<dl class="checks">{items}</dl></section>')

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
    """남은 지적 체크리스트 항목을 심각도 순으로. sid는 화면 섹션 키(slug), 흐름 지적은 빈 문자열.
    HTML의 [남은 지적을 체크리스트로 복사]가 이 목록에서 해결됨·문제 아님 화면의 항목을 빼요."""
    items = []
    for f in sorted(m.findings, key=sev_key):
        fid = t(f.get("id"))
        sid = t(f.get("screen_id"))
        in_screen = f.get("lens") != "흐름" and bool(sid)
        scr = mt(m.screen_name(sid)) if sid in m.screen_by_id else "여러 화면에 걸친 흐름"
        lines = [f"- [ ] [{mt(f.get('severity'))}] {mt(fid)} {mt(f.get('title'))} ({scr})"]
        for label, key in (("고치기", "fix"), ("수정 후", "tobe"), ("확인 기준", "done_when")):
            if mt(f.get(key)):
                lines.append(f"  - {label}: {mt(f.get(key))}")
        items.append({"sid": slug(sid) if in_screen else "", "fid": fid, "text": "\n".join(lines)})
    return items


def render_checklist(items, skip_sids=()):
    """체크리스트 마크다운. skip_sids에 든 화면의 항목은 뺀다. 남은 것이 없으면 빈 문자열."""
    kept = [it["text"] for it in items if not (it["sid"] and it["sid"] in skip_sids)]
    if not kept:
        return ""
    return f"## 남은 지적 {len(kept)}개\n\n" + "\n".join(kept)


def build_md(m):
    L = []
    headline = mt(m.summary.get("headline")) or "UX 검토 결과"
    L += ["# UX 검토 결과", "", "## 총평", f"**{headline}**"]
    # HTML 첫 화면과 같은 규칙: 심각을 앞으로 올려 최대 TOP_MAX개
    top = [f"{mt(f.get('id'))} {mt(f.get('title'))}" for f in top_findings(m)]
    if top:
        L.append("먼저 고칠 것: " + ", ".join(top))
    n_screens, n_find, n_sev = m.counts()
    L += ["", f"화면 {n_screens}개 · 지적 {n_find}개 · 심각 {n_sev}개", ""]
    L.append(f"검토 조건: 입력 {mt(label_of(INPUT_LABEL, m.run.get('input_type')))} · "
             f"문구 판정 {mt(label_of(WRITING_LABEL, m.run.get('writing_judge')))}")
    if t(m.run.get("product_value")):
        L.append(f"제품 핵심 가치: {mt(m.run.get('product_value'))}")
    if t(m.run.get("goal")):
        L.append(f"목표: {mt(m.run.get('goal'))}")
    ex = [mt(x) for x in strs(m.run.get("exclusions"))]
    if ex:
        L.append("제외 규칙: " + ", ".join(ex))

    L += ["", "## 화면"]
    for s in m.screens:
        L += ["", f"### {mt(s.get('name'))} ({code(s.get('id'))})",
              f"- 화면 목표: {mt(s.get('screen_goal'))}", f"- 한 줄 진단: {mt(s.get('verdict'))}"]

    L += ["", "## 지적"]
    for f in sorted(m.findings, key=sev_key):
        L += ["", f"### [{mt(f.get('severity'))}] {mt(f.get('id'))} {mt(f.get('title'))}  (렌즈: {mt(f.get('lens'))})"]
        ev = f.get("evidence") if isinstance(f.get("evidence"), dict) else {}
        sid = t(f.get("screen_id"))
        scr = code(sid) if sid else "여러 화면에 걸친 흐름"
        where = f" · {mt(ev.get('where'))}" if t(ev.get("where")) else ""
        L.append(f"- 화면: {scr}{where} (근거 유형: {mt(ev.get('type'))})")
        for label, key in (("관찰", "observation"), ("왜 문제인가", "why")):
            if t(f.get(key)):
                L.append(f"- {label}: {mt(f.get(key))}")
        if t(f.get("principle")):
            L.append(f"- 근거 원칙: {mt(f.get('principle'))} {mt(f.get('case'))}".rstrip())
        for label, key in (("제안", "fix"), ("수정 전", "asis"), ("수정 후", "tobe"),
                           ("고쳤는지 확인하는 기준", "done_when"), ("확인 필요", "confirm_needed")):
            if t(f.get(key)):
                L.append(f"- {label}: {mt(f.get(key))}")
        if m.ut:
            names = [mt(m.ut["persona_by_id"][p].get("name")) for p in strs(f.get("from_ut"))
                     if p in m.ut["persona_by_id"]]
            if names:
                L.append("- 가상 UT에서 나온 지적: " + ", ".join(names))

    if m.ut:
        ut = m.ut
        L += ["", "## 가상 UT (실제 사용자 조사가 아니라 화면을 보고 추론한 가상 반응이에요)", "", "### 페르소나"]
        for p in ut["personas"]:
            L.append(f"- {mt(p.get('name'))} ({code(p.get('id'))}, {mt(p.get('age_group'))}, "
                     f"디바이스 적응도 {mt(p.get('device_level'))}, UX 이해도 {mt(p.get('ux_level'))}): "
                     f"{mt(p.get('traits'))} 목표: {mt(p.get('goal'))}")
        links = []
        for p in ut["personas"]:
            pid = t(p["id"])
            w = ut["walks"].get(pid, {})
            head = f"### {mt(p.get('name'))}: {mt(w.get('outcome'))}"
            if w.get("outcome") == "이탈":
                head += f"  ({code(w.get('stopped_at'))}에서 멈춤, 이유: {mt(w.get('stop_reason'))})"
            L += ["", head, "| 화면 | 디바이스 | 시안 이해 | 문구 이해 | 한마디 |", "|---|---|---|---|---|"]
            for st in dicts(w.get("steps")):
                sid = t(st.get("screen_id"))
                quote = f"\"{mc(st.get('quote'))}\""
                if t(st.get("cause")):
                    quote += f" 원인: {mc(st.get('cause'))}"
                L.append(f"| {mc(m.screen_name(sid))} ({code(sid)}) | {mc(st.get('device'))} | "
                         f"{mc(st.get('design'))} | {mc(st.get('writing'))} | {quote} |")
                fids = strs(st.get("finding_ids"))
                weak = [f"{an} {st.get(k)}" for k, an in AXES if st.get(k) in ("보통", "막힘")]
                if fids and weak:
                    ft = ", ".join(f"{mt(x)} {mt(m.finding_by_id[x].get('title'))}" if x in m.finding_by_id else mt(x)
                                   for x in fids)
                    links.append(f"- {mt(p.get('name'))} · {mt(m.screen_name(sid))}: {', '.join(weak)} → {ft}")
        if links:
            L += ["", "### 반응에서 나온 지적"] + links

    if m.strengths:
        L += ["", "## 잘 된 점"]
        for st in m.strengths:
            tail = ", ".join(x for x in (mt(st.get("principle")), mt(st.get("screen_id"))) if x)
            L.append(f"- {mt(st.get('note'))}" + (f" ({tail})" if tail else ""))
    if m.checks:
        L += ["", "## 확인 필요"]
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


def build(run, fmt="both", cases_path=None):
    """RUN의 리포트를 만들고 쓴 파일 경로 목록을 돌려준다. cases_path는 사례 출처 링크용 cases.md."""
    rev_path = os.path.join(run, "review.json")
    if not os.path.isfile(rev_path):
        raise ValueError(f"review.json이 없어요 ({rev_path}). 샤딩이면 먼저 validate.py를 돌려 합쳐요")
    rev = load_json(rev_path)
    if not isinstance(rev, dict):
        raise ValueError("review.json 최상위는 객체여야 해요")
    cap_path = os.path.join(run, "capture.json")
    cap = load_json(cap_path) if os.path.isfile(cap_path) else {}
    m = Model(rev, cap, load_case_index(cases_path))
    written = []
    if fmt in ("html", "both"):
        doc, n_img, missing = build_html(m, run)
        p = os.path.join(run, "report.html")
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
    a = ap.parse_args()
    try:
        build(a.run, a.format)
    except (ValueError, OSError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
