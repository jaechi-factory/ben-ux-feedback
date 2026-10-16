#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 비교 모드: 시안 비교 리포트 빌드
RUN/compare.json을 검사한 뒤 단일 HTML(이미지 내장, 외부 요청 없음)을 만든다.
같은 목적의 시안 여러 개 중 무엇이 가장 좋은지, 각각 무엇이 아쉬운지를 한 장에 보여준다.
compare.json은 바꾸지 않는다. 표준 라이브러리만 쓴다.

사용: python3 build_compare.py --run ./run [--check] [--strict] [--out 경로.html]
  --check   검사만 하고 HTML은 쓰지 않는다(오류가 있으면 exit 1)
  --strict  경고도 실패로 본다
검사 규칙(원칙 이름, 사례 번호, 추상 수정안, 부재 주장, 제외 규칙, 가상 UT)은 validate.py의 규칙을 그대로 쓴다.
결과: RUN/compare.html (또는 --out 경로)
"""
import argparse
import base64
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate  # noqa: E402  같은 폴더의 검증기 규칙을 재사용한다

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}
SEVERITY = {"심각": "s1", "중간": "s2", "낮음": "s3"}
LEVELS = ("good", "mid", "bad")
SIZE_WARN_MB = 20
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GUIDELINE = os.path.join(HERE, "..", "references", "guideline.md")
DEFAULT_CASES = os.path.join(HERE, "..", "references", "cases.md")


# ── 검사 ──
# 지적 규율(원칙 이름, 사례 번호, 추상 수정안, 부재 주장, 제외 규칙, UT 수치 금지)은 validate.py와 같은 규칙을 그대로 쓴다.

def blank(v):
    return not isinstance(v, str) or not v.strip()


def safe_shot(run, rel):
    """shot은 RUN/shots 안의 이미지 파일만 허용한다(build_report.py와 같은 규칙)."""
    if blank(rel):
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


def as_list(cmp, key, errors, required=False):
    v = cmp.get(key)
    if v is None:
        if required:
            errors.append(f"{key}가 없어요")
        return []
    if not isinstance(v, list):
        errors.append(f"{key}는 목록이어야 해요")
        return []
    return v


def opt_str(obj, keys, where, errors):
    for k in keys:
        if k in obj and obj[k] is not None and not isinstance(obj[k], str):
            errors.append(f"{where}.{k}는 문자열이어야 해요")


def check_issue(c, where, text_keys, ctx, errors, warns, owner):
    """시안별 아쉬운 점(cons)과 공통 문제(common) 하나를 단일 모드 지적과 같은 규율로 검사한다."""
    if not isinstance(c, dict):
        errors.append(f"{where}가 객체가 아니에요")
        return
    sev_v = c.get("severity")
    if sev_v not in SEVERITY:
        errors.append(f"{where}.severity는 심각, 중간, 낮음 중 하나여야 해요")
    for key in text_keys + ("fix", "where"):
        if blank(c.get(key)):
            errors.append(f"{where}.{key}가 비었어요" + (" (화면 안 위치)" if key == "where" else ""))
    opt_str(c, ("id", "tobe", "done_when", "confirm_needed", "applies", "principle", "case"), where, errors)
    if sev_v == "심각":
        if blank(c.get("tobe")):
            errors.append(f"{where}: 심각 지적에는 tobe(수정 후 모습)가 필요해요")
        if blank(c.get("done_when")):
            warns.append(f"{where}: 심각 지적에는 done_when(고쳤는지 확인하는 기준)을 권해요")
    pr, cs = c.get("principle"), c.get("case")
    if isinstance(pr, str) and ctx["principles"] is not None and validate.norm(pr) not in ctx["principles"]:
        errors.append(f"{where}: guideline.md에 없는 원칙 이름 {pr!r}")
    if blank(pr) and not blank(cs):
        errors.append(f"{where}: principle이 비었는데 case가 있어요")
    if isinstance(cs, str) and ctx["cases"] is not None and cs not in ctx["cases"]:
        errors.append(f"{where}: cases.md에 없는 사례 번호 {cs!r}")
    body = " ".join(str(c.get(k) or "") for k in text_keys)
    if sev_v == "심각" and validate.ABSENCE_CLAIM.search(body):
        trail = f"{c.get('where') or ''} {c.get('confirm_needed') or ''} {body}"
        if not validate.SCAN_TRACE.search(trail):
            warns.append(f"{where}: 없다는 주장인데 화면을 훑은 흔적이 없어요. 비슷한 요소의 위치나 "
                         "가장 가까운 요소를 where나 confirm_needed에 적으세요")
    if isinstance(c.get("fix"), str) and validate.ABSTRACT_FIX.search(c["fix"]) and blank(c.get("tobe")):
        warns.append(f"{where}: fix가 추상적이에요. 무엇을 어디에 어떻게 바꾸는지 tobe로 구체화하세요")
    active = ctx["exclusions"]
    if "curly-braces" in active and re.search(r"\{[^{}]*\}", body):
        warns.append(f"{where}: curly-braces 제외 규칙이 켜져 있는데 중괄호를 언급해요")
    if ("dummy-amount-mismatch" in active and re.search(r"(금액|가격|\d[\d,]*\s*원)", body)
            and re.search(r"(불일치|다르|달라|서로 다른)", body)):
        warns.append(f"{where}: dummy-amount-mismatch 제외 규칙이 켜져 있는데 금액 불일치를 지적한 것 같아요. "
                     "한 화면 안의 숫자 불일치라면 그대로 둬도 돼요")
    if not blank(c.get("id")):
        if c["id"] in ctx["issue_ids"]:
            errors.append(f"{where}.id '{c['id']}'가 겹쳐요")
        ctx["issue_ids"][c["id"]] = owner


def check_ut(ut, ids, issue_ids, first_id, errors, warns):
    """1위 시안을 걸어 본 가상 사용자 반응. 단일 모드 ut와 같은 축과 금지 규칙을 쓴다."""
    if not isinstance(ut, dict):
        errors.append("ut는 객체여야 해요")
        return
    if ut.get("mode") != validate.UT_MODE:
        errors.append("ut.mode는 virtual이어야 해요")
    if ut.get("variant") not in ids:
        errors.append(f"ut.variant가 variants의 id가 아니에요: {ut.get('variant')!r}")
    elif first_id is not None and ut["variant"] != first_id:
        warns.append(f"ut.variant '{ut['variant']}'가 1위 시안이 아니에요. 비교 모드 가상 UT는 1위 시안을 걸어 봐요")
    allowed = {k for k, owner in issue_ids.items() if owner in ("common", ut.get("variant"))}
    validate.scan_ut_scores(ut, "ut", errors)
    personas = ut.get("personas")
    if not isinstance(personas, list) or not personas:
        errors.append("ut.personas는 1명 이상의 목록이어야 해요")
        return
    ages = []
    for i, p in enumerate(personas):
        where = f"ut.personas[{i}]"
        if not isinstance(p, dict):
            errors.append(f"{where}가 객체가 아니에요")
            continue
        for key in ("name", "traits", "goal", "quote"):
            if blank(p.get(key)):
                errors.append(f"{where}.{key}가 비었어요")
        if p.get("age_group") not in validate.UT_AGE_GROUPS:
            errors.append(f"{where}.age_group은 청년, 중년, 노년 중 하나여야 해요")
        ages.append(p.get("age_group"))
        for key in ("device_level", "ux_level"):
            if p.get(key) not in validate.UT_LEVELS:
                errors.append(f"{where}.{key}는 상, 중, 하 중 하나여야 해요")
        if p.get("outcome") not in validate.UT_OUTCOMES:
            errors.append(f"{where}.outcome은 완주 또는 이탈이어야 해요")
        vals = [p.get(a) for a in validate.UT_AXES]
        for a, v in zip(validate.UT_AXES, vals):
            if v not in validate.UT_AXIS_VALUES:
                errors.append(f"{where}.{a}는 쉬움, 보통, 막힘 중 하나여야 해요")
        links = p.get("issue_ids", [])
        if not isinstance(links, list) or not all(isinstance(x, str) for x in links):
            errors.append(f"{where}.issue_ids는 지적 id 목록이어야 해요")
            links = []
        for x in links:
            if x not in allowed:
                errors.append(f"{where}.issue_ids의 '{x}'가 ut.variant 시안의 cons나 common의 id에 없어요")
        if "막힘" in vals:
            if blank(p.get("cause")):
                errors.append(f"{where}: 막힘이 있으면 cause가 필요해요")
            if not links:
                errors.append(f"{where}: 막힘 반응은 issue_ids로 지적에 이어요")
        elif "보통" in vals and not links:
            warns.append(f"{where}: 보통 반응에 연결된 지적이 없어요")
    if len(personas) != 3 or len(set(ages)) != len(ages):
        warns.append("가상 UT 페르소나가 3명이 아니거나 연령대가 겹쳐요(사용자가 정했다면 무시해도 돼요)")


def check(cmp, run, cap=None, principles=None, cases=None):
    """compare.json을 검사해 (오류 목록, 경고 목록)을 돌려준다. 오류가 비면 리포트를 만들 수 있다."""
    errors, warns = [], []
    if not isinstance(cmp, dict):
        return ["compare.json 최상위는 객체여야 해요"], warns
    for key in ("headline", "lead"):
        if blank(cmp.get(key)):
            errors.append(f"{key}가 비었어요")
    opt_str(cmp, ("title", "kicker", "criteria_lead"), "compare", errors)
    exclusions = cmp.get("exclusions", [])
    if not isinstance(exclusions, list) or not all(isinstance(x, str) for x in exclusions):
        errors.append("exclusions는 문자열 목록이어야 해요")
        exclusions = []
    for x in exclusions:
        if x not in validate.KNOWN_EXCLUSIONS:
            warns.append(f"exclusions '{x[:30]}'는 자동 검사 대상이 아니에요. 직접 지켰는지 확인하세요")
    ctx = {"principles": principles, "cases": cases, "exclusions": set(exclusions), "issue_ids": {}}
    validate.check_brief(cmp.get("brief"), "brief", errors, warns)

    variants = cmp.get("variants")
    if not isinstance(variants, list) or len(variants) < 2:
        return errors + ["variants는 시안 2개 이상의 목록이어야 해요"], warns
    ids, ranks = [], []
    for i, v in enumerate(variants):
        where = f"variants[{i}]"
        if not isinstance(v, dict):
            errors.append(f"{where}가 객체가 아니에요")
            continue
        for key in ("id", "name", "shot", "one_line", "why", "summary"):
            if blank(v.get(key)):
                errors.append(f"{where}.{key}가 비었어요")
        opt_str(v, ("short", "source", "alt", "goods_label"), where, errors)
        if isinstance(v.get("id"), str):
            ids.append(v["id"])
        rank = v.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool):
            errors.append(f"{where}.rank는 정수여야 해요")
        else:
            ranks.append(rank)
        if not blank(v.get("shot")) and not safe_shot(run, v["shot"]):
            errors.append(f"{where}.shot이 RUN/shots/ 아래 이미지 파일이 아니에요: {v['shot']}")
        goods = v.get("goods", [])
        if not isinstance(goods, list) or any(blank(g) for g in goods):
            errors.append(f"{where}.goods는 문장 목록이어야 해요")
            goods = []
        cons = v.get("cons", [])
        if not isinstance(cons, list):
            errors.append(f"{where}.cons는 목록이어야 해요")
            cons = []
        for j, c in enumerate(cons):
            check_issue(c, f"{where}.cons[{j}]", ("text",), ctx, errors, warns, v.get("id"))
        if not goods and not cons:
            errors.append(f"{where}에 잘한 점(goods)도 아쉬운 점(cons)도 없어요")
    if len(set(ids)) != len(ids):
        errors.append("variants.id가 겹쳐요")
    if ranks and sorted(ranks) != list(range(1, len(variants) + 1)):
        errors.append(f"rank는 1부터 {len(variants)}까지 한 번씩 써야 해요: {sorted(ranks)}")

    criteria = as_list(cmp, "criteria", errors, required=True)
    if not criteria and isinstance(cmp.get("criteria"), list):
        errors.append("criteria는 비교 기준 1개 이상이어야 해요")
    for i, cr in enumerate(criteria):
        where = f"criteria[{i}]"
        if not isinstance(cr, dict) or blank(cr.get("label")):
            errors.append(f"{where}.label이 비었어요")
            continue
        cells = cr.get("cells")
        if not isinstance(cells, dict):
            errors.append(f"{where}.cells는 시안 id를 키로 한 객체여야 해요")
            continue
        for vid in ids:
            cell = cells.get(vid)
            if not isinstance(cell, dict):
                errors.append(f"{where}.cells에 시안 '{vid}'가 없어요")
                continue
            if cell.get("level") not in LEVELS:
                errors.append(f"{where}.cells.{vid}.level은 good, mid, bad 중 하나여야 해요")
            if blank(cell.get("word")):
                errors.append(f"{where}.cells.{vid}.word가 비었어요")
            opt_str(cell, ("note",), f"{where}.cells.{vid}", errors)
        extra = sorted(set(cells) - set(ids))
        if extra:
            errors.append(f"{where}.cells에 없는 시안 id가 있어요: {extra}")

    for i, c in enumerate(as_list(cmp, "common", errors)):
        check_issue(c, f"common[{i}]", ("title", "body"), ctx, errors, warns, "common")

    recipe = cmp.get("recipe")
    if recipe is not None:
        if not isinstance(recipe, dict):
            errors.append("recipe는 객체여야 해요")
        else:
            opt_str(recipe, ("lead", "note"), "recipe", errors)
            for i, st in enumerate(as_list(recipe, "steps", errors)):
                if not isinstance(st, dict) or blank(st.get("title")):
                    errors.append(f"recipe.steps[{i}].title이 비었어요")
                else:
                    opt_str(st, ("detail",), f"recipe.steps[{i}]", errors)
            for i, sp in enumerate(as_list(recipe, "spec", errors)):
                if not isinstance(sp, dict) or blank(sp.get("label")) or blank(sp.get("value")):
                    errors.append(f"recipe.spec[{i}]에는 label과 value가 필요해요")

    for i, c in enumerate(as_list(cmp, "checks", errors)):
        if not isinstance(c, dict) or blank(c.get("what")) or blank(c.get("how")):
            errors.append(f"checks[{i}]에는 what과 how가 필요해요")
    footer = as_list(cmp, "footer", errors)
    if any(not isinstance(x, str) for x in footer):
        errors.append("footer는 문장 목록이어야 해요")

    if cmp.get("ut") is not None:
        first = [v.get("id") for v in variants if isinstance(v, dict) and v.get("rank") == 1]
        check_ut(cmp["ut"], ids, ctx["issue_ids"], first[0] if len(first) == 1 else None, errors, warns)
    else:
        warns.append("ut가 없어요. 가상 UT를 돌리지 않았으면 리포트 끝에 생략했다고 자동으로 적어요")

    # 전수 커버리지: capture.json의 화면과 시안이 서로 빠짐없이 맞아야 한다
    if cap is not None:
        if not isinstance(cap, dict) or not isinstance(cap.get("screens"), list):
            warns.append("capture.json 형식이 달라 전수 커버리지를 검사하지 못했어요")
        else:
            cap_ids = {sc.get("id") for sc in cap["screens"] if isinstance(sc, dict) and isinstance(sc.get("id"), str)}
            missing = sorted(cap_ids - set(ids))
            if missing:
                errors.append(f"capture.json 화면이 비교에서 빠졌어요: {missing}")
            unknown = sorted(set(ids) - cap_ids)
            if unknown:
                errors.append(f"capture.json에 없는 시안 id예요: {unknown}")
    return errors, warns


# ── 렌더 ──

def esc(v):
    return html.escape(v if isinstance(v, str) else "", quote=True)


def rich(v):
    """이스케이프한 뒤 **굵게**와 {자리표시}만 표시한다. 그 밖의 마크업은 쓰지 않는다."""
    s = esc(v)
    s = re.sub(r"\*\*([^*\n]+?)\*\*", r"<strong>\1</strong>", s)
    # 자리표시는 이스케이프된 꺾쇠(&lt; &gt;)를 넘지 않아서 굵게 태그와 엇갈리지 않는다
    s = re.sub(r"\{([^{}<>&\n]{1,40})\}", r"<code>{\1}</code>", s)
    return s.replace("\n", "<br>")


def issue_meta(c):
    """지적의 화면 위치, 수정 후 모습, 확인 기준, 근거 원칙, 확인 필요를 렌더한다(있는 것만)."""
    parts = []
    if not blank(c.get("tobe")):
        parts.append(f'<p class="tobe"><span class="k">수정 후</span>{rich(c["tobe"])}</p>')
    if not blank(c.get("done_when")):
        parts.append(f'<p class="meta"><span class="k">확인 기준</span>{rich(c["done_when"])}</p>')
    basis = []
    if not blank(c.get("where")):
        basis.append(f"화면: {esc(c['where'])}")
    if not blank(c.get("principle")):
        basis.append(f"원칙: {esc(c['principle'])}" + (f" {esc(c['case'])}" if not blank(c.get("case")) else ""))
    if basis:
        parts.append(f'<p class="meta">{" · ".join(basis)}</p>')
    if not blank(c.get("confirm_needed")):
        parts.append(f'<p class="meta"><span class="k">확인 필요</span>{rich(c["confirm_needed"])}</p>')
    return "".join(parts)


def data_uri(path):
    mime = MIME[os.path.splitext(path)[1].lower()]
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode("ascii")


def sev(level):
    return f'<span class="sev {SEVERITY[level]}">{esc(level)}</span>'


def rank_badge(rank):
    cls = "rank first" if rank == 1 else "rank"
    return f'<span class="{cls}">{rank}</span>'


CSS = """
:root{
--grey-50:#F9FAFB;--grey-100:#F2F4F6;--grey-200:#E5E8EB;--grey-400:#B0B8C1;--grey-500:#8B95A1;--grey-600:#6B7684;--grey-700:#4E5968;--grey-800:#333D4B;--grey-900:#191F28;
--blue-50:#E8F3FF;--blue-500:#3182F6;--blue-700:#1B64DA;
--red-50:#FFEEEE;--red-500:#F04452;--red-600:#E42939;
--yellow-50:#FFF9E7;--yellow-500:#FFC342;
--green-500:#03B26C;
--font-sans:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
--t1:30px;--t2:26px;--t3:22px;--t4:20px;--t5:17px;--t6:15px;--t7:13px;--lh-title:1.5;--lh-body:1.65;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#FFFFFF;color:var(--grey-800);font-family:var(--font-sans);font-size:var(--t5);line-height:var(--lh-body);word-break:keep-all;overflow-wrap:anywhere;-webkit-font-smoothing:antialiased}
main{max-width:880px;margin:0 auto;padding:64px 24px 96px}
h1,h2,h3{color:var(--grey-900);line-height:var(--lh-title);margin:0}
h1{font-size:var(--t1);font-weight:700}h2{font-size:var(--t3);font-weight:700}h3{font-size:var(--t4);font-weight:700}
p{margin:0}ul,ol{margin:0;padding:0;list-style:none}
section{margin-top:72px}
.kicker{font-size:var(--t7);font-weight:500;color:var(--blue-700);margin-bottom:12px}
.lead{margin-top:16px;color:var(--grey-700)}.lead strong{color:var(--grey-900)}
.sec-lead{margin-top:8px;color:var(--grey-600);font-size:var(--t6)}
code{font-family:inherit;background:var(--grey-100);border-radius:4px;padding:0 4px;color:var(--grey-800)}
.verdict{margin-top:32px;background:var(--grey-50);border-radius:16px;padding:24px}
.verdict li{display:grid;grid-template-columns:32px minmax(0,1fr);gap:12px;align-items:start;padding:12px 0}
.verdict li+li{border-top:1px solid var(--grey-200)}
.verdict strong{color:var(--grey-900)}
.verdict .why{display:block;font-size:var(--t6);color:var(--grey-700)}
.rank{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:14px;font-size:var(--t7);font-weight:700;background:var(--grey-200);color:var(--grey-700);flex:none}
.rank.first{background:var(--blue-500);color:#FFFFFF}
.thumbs{margin-top:24px;display:grid;grid-template-columns:repeat(var(--tc),minmax(0,200px));gap:16px}
.thumb{margin:0;min-width:0}
.thumb a{display:block;color:inherit;text-decoration:none;border-radius:12px}
.thumb a:focus-visible{outline:2px solid var(--blue-500);outline-offset:4px}
.thumb .cap{margin-bottom:12px;min-height:48px;display:flex;gap:8px;align-items:flex-start}
.thumb .name{font-size:var(--t6);font-weight:700;color:var(--grey-900);line-height:var(--lh-title)}
.thumb .one{display:block;font-size:var(--t7);color:var(--grey-600);font-weight:400}
.frame{border:1px solid var(--grey-200);border-radius:12px;overflow:hidden;background:#FFFFFF}
.best .frame{border:2px solid var(--blue-500)}
.frame img{display:block;width:100%;height:auto}
.matrix{margin-top:24px;border-top:1px solid var(--grey-200)}
.mrow{display:grid;grid-template-columns:minmax(0,1.3fr) repeat(var(--n),minmax(0,1fr));gap:8px;padding:16px 0;border-bottom:1px solid var(--grey-200);align-items:start}
.mrow.head{padding:12px 0;font-size:var(--t7);font-weight:700;color:var(--grey-600)}
.mlabel{font-size:var(--t6);font-weight:500;color:var(--grey-900)}
.cell{font-size:var(--t7);line-height:1.5;color:var(--grey-700)}
.cell b{display:inline-flex;align-items:center;gap:4px;font-weight:700;color:var(--grey-900)}
.cell b::before{content:"";width:10px;height:10px;border-radius:5px;flex:none}
.good b::before{background:var(--green-500)}.mid b::before{background:var(--grey-400)}.bad b::before{background:var(--red-500)}
.cell .vname{display:none}
.problems{margin-top:24px;display:grid;gap:16px}
.problem{border:1px solid var(--grey-200);border-radius:16px;padding:20px 24px}
.ptitle{display:flex;gap:8px;align-items:baseline}
.ptitle h3{font-size:var(--t5)}
.sev{flex:none;display:inline-flex;align-items:center;gap:6px;font-size:var(--t7);font-weight:700;padding:2px 10px;border-radius:999px}
.sev::before{content:"";width:8px;height:8px;border-radius:4px}
.sev.s1{background:var(--red-50);color:var(--red-600)}.sev.s1::before{background:var(--red-500)}
.sev.s2{background:var(--yellow-50);color:var(--grey-800)}.sev.s2::before{background:var(--yellow-500)}
.sev.s3{background:var(--grey-100);color:var(--grey-700)}.sev.s3::before{background:var(--grey-400)}
.problem p{margin-top:8px;font-size:var(--t6);color:var(--grey-700)}
.fix{margin-top:12px;background:var(--blue-50);border-radius:12px;padding:12px 16px;font-size:var(--t6);color:var(--grey-800)}
.fix::before{content:"이렇게 고쳐요";display:block;font-size:var(--t7);font-weight:700;color:var(--blue-700);margin-bottom:4px}
.where{margin-top:8px;font-size:var(--t7);color:var(--grey-600)}
.tobe{margin-top:8px;font-size:var(--t6);color:var(--grey-900)}
.meta{margin-top:6px;font-size:var(--t7);color:var(--grey-600)}
.k{display:inline-block;margin-right:8px;font-weight:700;color:var(--grey-700)}
.ut{margin-top:24px;display:grid;gap:16px}
.ut li{border:1px solid var(--grey-200);border-radius:16px;padding:20px 24px}
.ut .who{font-weight:700;color:var(--grey-900)}
.ut .trait{margin-top:4px;font-size:var(--t7);color:var(--grey-600)}
.ut .axes{margin-top:12px;display:flex;flex-wrap:wrap;gap:8px}
.ut .ax{font-size:var(--t7);padding:2px 10px;border-radius:999px;background:var(--grey-100);color:var(--grey-800)}
.ut .ax.block{background:var(--red-50);color:var(--red-600);font-weight:700}
.ut .quote{margin-top:12px;font-size:var(--t6);color:var(--grey-900)}
.ut .cause{margin-top:4px;font-size:var(--t7);color:var(--grey-600)}
.variant{margin-top:40px;padding-top:40px;border-top:1px solid var(--grey-200);display:grid;grid-template-columns:240px minmax(0,1fr);gap:32px;align-items:start}
.variant:first-of-type{border-top:0;padding-top:0}
.variant .frame{position:sticky;top:24px}
.vhead{display:flex;gap:12px;align-items:center}
.vsub{margin-top:4px;font-size:var(--t7);color:var(--grey-500)}
.vsum{margin-top:12px;color:var(--grey-800)}
.label{margin-top:24px;font-size:var(--t7);font-weight:700;color:var(--grey-600)}
.goods{margin-top:8px;display:grid;gap:8px}
.goods li{font-size:var(--t6);color:var(--grey-800);padding-left:16px;position:relative}
.goods li::before{content:"";position:absolute;left:0;top:10px;width:6px;height:6px;border-radius:3px;background:var(--green-500)}
.cons{margin-top:8px;display:grid;gap:12px}
.cons li{background:var(--grey-50);border-radius:12px;padding:16px}
.cons .ctext{display:flex;gap:8px;align-items:baseline;font-size:var(--t6);color:var(--grey-900);font-weight:500}
.cons .cfix{margin-top:6px;font-size:var(--t6);color:var(--grey-700)}
.cons .cfix::before{content:"→ ";color:var(--blue-500);font-weight:700}
.steps{margin-top:24px}
.steps li{position:relative;padding:0 0 24px 40px}
.steps li::before{content:"";position:absolute;left:11px;top:28px;bottom:0;width:2px;background:var(--grey-200)}
.steps li:last-child::before{display:none}
.steps .dot{position:absolute;left:0;top:0;width:24px;height:24px;border-radius:12px;background:var(--blue-500);color:#FFFFFF;font-size:var(--t7);font-weight:700;display:flex;align-items:center;justify-content:center}
.steps strong{color:var(--grey-900)}
.steps .sd{display:block;font-size:var(--t6);color:var(--grey-700)}
.spec{margin:8px 0 0;border:1px solid var(--grey-200);border-radius:16px;overflow:hidden}
.spec div{display:grid;grid-template-columns:120px minmax(0,1fr);gap:16px;padding:14px 20px;font-size:var(--t6)}
.spec div+div{border-top:1px solid var(--grey-200)}
.spec dt{color:var(--grey-600)}.spec dd{margin:0;color:var(--grey-900);font-weight:500}
.brief{margin-top:24px}
.brief summary{cursor:pointer;font-size:var(--t6);font-weight:700;color:var(--grey-700);padding:8px 0}
.brief summary:focus-visible{outline:2px solid var(--blue-500);outline-offset:4px;border-radius:4px}
.checks{margin-top:24px;display:grid;gap:12px}
.checks li{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;padding-bottom:12px;border-bottom:1px solid var(--grey-200);font-size:var(--t6)}
.checks .q{color:var(--grey-900);font-weight:500}.checks .h{color:var(--grey-600)}
footer{margin-top:72px;padding-top:24px;border-top:1px solid var(--grey-200);font-size:var(--t7);color:var(--grey-500)}
footer p+p{margin-top:4px}
@media (max-width:720px){
main{padding:40px 20px 72px}
h1{font-size:var(--t2)}
.thumbs{grid-template-columns:repeat(2,minmax(0,1fr))}
.thumb .cap{min-height:80px}
.variant{grid-template-columns:minmax(0,1fr);gap:20px}
.variant .frame{position:static;max-width:260px}
.mrow.head{display:none}
.mrow{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px}
.mlabel{grid-column:1/-1}
.cell .vname{display:block;color:var(--grey-500)}
.checks li{grid-template-columns:minmax(0,1fr);gap:4px}
.spec div{grid-template-columns:minmax(0,1fr);gap:2px}
}
"""


def build_html(cmp, run):
    vs = sorted(cmp["variants"], key=lambda v: v["rank"])
    n = len(vs)
    imgs = {v["id"]: data_uri(safe_shot(run, v["shot"])) for v in vs}
    anchor = {v["id"]: f"v-{i}" for i, v in enumerate(vs, 1)}  # id에 한글이 있어도 겹치지 않게 순번으로
    out = []
    w = out.append
    title = cmp.get("title") or cmp["headline"]
    w('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width, initial-scale=1">'
      f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
      f'<title>{esc(title)}</title><style>{CSS}</style></head><body>'
      f'<main style="--n:{n};--tc:{min(n, 4)}"><header>')
    if not blank(cmp.get("kicker")):
        w(f'<p class="kicker">{esc(cmp["kicker"])}</p>')
    w(f'<h1>{esc(cmp["headline"])}</h1><p class="lead">{rich(cmp["lead"])}</p>')
    w('<ol class="verdict" aria-label="추천 순위">')
    for v in vs:
        w(f'<li>{rank_badge(v["rank"])}<span><strong>{esc(v["name"])}</strong>'
          f'<span class="why">{rich(v["why"])}</span></span></li>')
    w('</ol>')
    brief = cmp.get("brief") if isinstance(cmp.get("brief"), dict) else {}
    rows = [(label, brief.get(k)) for k, label in validate.BRIEF_FIELDS if not blank(brief.get(k))]
    if rows:
        src = "작성자가 준 맥락이에요." if brief.get("source") == "user" else "일부나 전부를 화면에서 추론했어요."
        w(f'<details class="brief"><summary>검토 전제 보기</summary><p class="where">{src}</p><dl class="spec">')
        w("".join(f'<div><dt>{esc(k)}</dt><dd>{rich(v)}</dd></div>' for k, v in rows))
        w('</dl></details>')
    w('</header>')

    w('<section aria-labelledby="s-glance"><h2 id="s-glance">한눈에 보기</h2>'
      '<p class="sec-lead">추천 순서로 놓았어요. 누르면 그 시안의 상세로 가요.</p><div class="thumbs">')
    for v in vs:
        best = " best" if v["rank"] == 1 else ""
        alt = v.get("alt") or f'{v["name"]} 화면'
        w(f'<div class="thumb{best}"><a href="#{anchor[v["id"]]}"><span class="cap">{rank_badge(v["rank"])}'
          f'<span class="name">{esc(v["name"])}<span class="one">{esc(v["one_line"])}</span></span></span>'
          f'<span class="frame" style="display:block"><img src="{imgs[v["id"]]}" alt="{esc(alt)}"></span></a></div>')
    w('</div></section>')

    w('<section aria-labelledby="s-matrix"><h2 id="s-matrix">기준별로 비교하면</h2>')
    if not blank(cmp.get("criteria_lead")):
        w(f'<p class="sec-lead">{rich(cmp["criteria_lead"])}</p>')
    w('<div class="matrix" role="table" aria-label="기준별 시안 비교"><div class="mrow head" role="row">'
      '<span role="columnheader">기준</span>')
    for v in vs:
        w(f'<span role="columnheader">{v["rank"]} {esc(v.get("short") or v["name"])}</span>')
    w('</div>')
    for cr in cmp["criteria"]:
        w(f'<div class="mrow" role="row"><span class="mlabel" role="rowheader">{esc(cr["label"])}</span>')
        for v in vs:
            c = cr["cells"][v["id"]]
            note = f' {esc(c["note"])}' if not blank(c.get("note")) else ""
            w(f'<span class="cell {c["level"]}" role="cell"><span class="vname">{esc(v.get("short") or v["name"])}</span>'
              f'<b>{esc(c["word"])}</b>{note}</span>')
        w('</div>')
    w('</div></section>')

    common = cmp.get("common") or []
    if common:
        w('<section aria-labelledby="s-common"><h2 id="s-common">어느 시안을 고르든 고쳐야 할 것</h2>'
          '<p class="sec-lead">시안을 고르는 것과 별개로, 이대로 내면 문제가 되는 것들이에요.</p><div class="problems">')
        for c in sorted(common, key=lambda c: list(SEVERITY).index(c["severity"])):
            w(f'<article class="problem"><div class="ptitle">{sev(c["severity"])}<h3>{esc(c["title"])}</h3></div>'
              f'<p>{rich(c["body"])}</p><div class="fix">{rich(c["fix"])}</div>{issue_meta(c)}')
            if not blank(c.get("applies")):
                w(f'<p class="where">해당: {esc(c["applies"])}</p>')
            w('</article>')
        w('</div></section>')

    w('<section aria-labelledby="s-detail"><h2 id="s-detail">시안별로 아쉬운 점</h2>'
      '<p class="sec-lead">추천 순서예요. 위의 공통 문제는 여기서 다시 쓰지 않았어요.</p>')
    for v in vs:
        best = " best" if v["rank"] == 1 else ""
        alt = v.get("alt") or f'{v["name"]} 화면 전체'
        w(f'<article class="variant{best}" id="{anchor[v["id"]]}"><div class="frame">'
          f'<img src="{imgs[v["id"]]}" alt="{esc(alt)}"></div><div>'
          f'<div class="vhead">{rank_badge(v["rank"])}<h3>{esc(v["name"])}</h3></div>')
        if not blank(v.get("source")):
            w(f'<p class="vsub">{esc(v["source"])}</p>')
        w(f'<p class="vsum">{rich(v["summary"])}</p>')
        if v.get("goods"):
            w(f'<p class="label">{esc(v.get("goods_label") or "잘한 점")}</p><ul class="goods">')
            w("".join(f"<li>{rich(g)}</li>" for g in v["goods"]))
            w('</ul>')
        if v.get("cons"):
            w('<p class="label">아쉬운 점</p><ul class="cons">')
            for c in sorted(v["cons"], key=lambda c: list(SEVERITY).index(c["severity"])):
                w(f'<li><span class="ctext">{sev(c["severity"])}<span>{rich(c["text"])}</span></span>'
                  f'<p class="cfix">{rich(c["fix"])}</p>{issue_meta(c)}</li>')
            w('</ul>')
        w('</div></article>')
    w('</section>')

    recipe = cmp.get("recipe")
    if isinstance(recipe, dict) and (recipe.get("steps") or recipe.get("spec")):
        w('<section aria-labelledby="s-mix"><h2 id="s-mix">추천 조합: 이렇게 합치면 돼요</h2>')
        if not blank(recipe.get("lead")):
            w(f'<p class="sec-lead">{rich(recipe["lead"])}</p>')
        if recipe.get("steps"):
            w('<ol class="steps">')
            for i, s in enumerate(recipe["steps"], 1):
                detail = f'<span class="sd">{rich(s["detail"])}</span>' if not blank(s.get("detail")) else ""
                w(f'<li><span class="dot">{i}</span><strong>{esc(s["title"])}</strong>{detail}</li>')
            w('</ol>')
        if recipe.get("spec"):
            w('<p class="label">고친 뒤 문구 예시</p><dl class="spec">')
            w("".join(f'<div><dt>{esc(s["label"])}</dt><dd>{rich(s["value"])}</dd></div>' for s in recipe["spec"]))
            w('</dl>')
        if not blank(recipe.get("note")):
            w(f'<p class="where">{rich(recipe["note"])}</p>')
        w('</section>')

    ut = cmp.get("ut")
    if isinstance(ut, dict):
        target = next(v for v in vs if v["id"] == ut["variant"])
        w(f'<section aria-labelledby="s-ut"><h2 id="s-ut">가상 사용자 반응: {esc(target["name"])}</h2>'
          '<p class="sec-lead">실제 사용자 조사가 아니라 화면을 보고 추론한 가상 반응이에요.</p><ul class="ut">')
        labels = {"device": "디바이스", "design": "시안 이해", "writing": "문구 이해"}
        for p in ut["personas"]:
            axes = "".join(f'<span class="ax{" block" if p[a] == "막힘" else ""}">{labels[a]} {esc(p[a])}</span>'
                           for a in validate.UT_AXES)
            cause = f'<p class="cause">막힌 이유: {rich(p["cause"])}</p>' if not blank(p.get("cause")) else ""
            w(f'<li><p class="who">{esc(p["name"])} · {esc(p["age_group"])} · 디바이스 {esc(p["device_level"])} · '
              f'UX 이해 {esc(p["ux_level"])} · {esc(p["outcome"])}</p><p class="trait">{esc(p["traits"])} 목표: {esc(p["goal"])}</p>'
              f'<div class="axes">{axes}</div><p class="quote">“{esc(p["quote"])}”</p>{cause}</li>')
        w('</ul></section>')

    checks = cmp.get("checks") or []
    if checks:
        w('<section aria-labelledby="s-check"><h2 id="s-check">화면만으로는 알 수 없는 것</h2><ul class="checks">')
        w("".join(f'<li><span class="q">{rich(c["what"])}</span><span class="h">{rich(c["how"])}</span></li>'
                  for c in checks))
        w('</ul></section>')

    notes = [x for x in cmp.get("footer", []) if not blank(x)] if isinstance(cmp.get("footer"), list) else []
    if not isinstance(ut, dict):
        notes.append("이번 비교에서는 가상 사용자 반응을 돌리지 않았어요.")
    if notes:
        w('<footer>' + "".join(f"<p>{rich(x)}</p>" for x in notes) + '</footer>')
    w('</main></body></html>')
    return "".join(out)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise ValueError(f"{os.path.basename(path)} JSON 파싱 실패: {e.lineno}행, {e.msg}")


def build(run, out=None, check_only=False, strict=False, guideline=None, cases_path=None):
    """검사를 통과하면 HTML 경로를, check_only면 None을 돌려준다. 실패하면 ValueError.
    strict면 경고도 실패로 본다(validate.py --strict와 같다)."""
    path = os.path.join(run, "compare.json")
    if not os.path.isfile(path):
        raise ValueError(f"compare.json이 없어요 ({path})")
    cmp = load_json(path)
    cap_path = os.path.join(run, "capture.json")
    cap = load_json(cap_path) if os.path.isfile(cap_path) else None
    principles = validate.load_principles(guideline or DEFAULT_GUIDELINE)
    cases = validate.load_cases(cases_path or DEFAULT_CASES)
    errors, warns = check(cmp, run, cap, principles, cases)
    if cap is None:
        warns.append("capture.json이 없어 전수 커버리지를 검사하지 못했어요")
    for x in warns:
        print(f"경고: {x}")
    if errors:
        raise ValueError(f"compare.json 검사 실패(오류 {len(errors)} · 경고 {len(warns)}):\n- " + "\n- ".join(errors))
    if strict and warns:
        raise ValueError(f"--strict: 경고 {len(warns)}건이 있어 실패로 봐요")
    if check_only:
        print(f"PASS: 시안 {len(cmp['variants'])}개, 기준 {len(cmp['criteria'])}개, 경고 {len(warns)}")
        return None
    out = out or os.path.join(run, "compare.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_html(cmp, run))
    size = os.path.getsize(out)
    print(f"WROTE {out} ({size // 1024}KB, 시안 {len(cmp['variants'])}개)")
    if size > SIZE_WARN_MB * 1024 * 1024:
        print(f"경고: 리포트가 {size // (1024 * 1024)}MB예요. 캡처를 작게 다시 떠 보세요")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="./run")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    try:
        build(a.run, a.out, a.check, a.strict)
    except (ValueError, OSError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
