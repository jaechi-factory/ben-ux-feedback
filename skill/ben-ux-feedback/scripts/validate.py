#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ben-ux-feedback 4단계: 검증
review.json을 output-contract.md 계약과 capture.json, guideline.md, cases.md에 대조한다.
오류(계약의 필수 규칙 위반)는 exit 1, 경고(판단이 필요한 규율)는 출력만 한다(--strict면 경고도 실패).
수준 구분은 references/output-contract.md의 "검증 수준" 절과 같다.

사용: python3 validate.py --run ./run [--strict] [--guideline PATH] [--cases PATH]
review-part-*.json이 있으면 항상 다시 합쳐서 review.json을 덮어쓴다(옛 합본을 검증하지 않기 위해서다).
"""
import argparse
import glob
import json
import os
import re
import sys

SEVERITY = ("심각", "중간", "낮음")
LENS = ("화면", "흐름", "문구", "접근성")
INPUT_TYPES = ("image", "figma", "live")
WRITING_JUDGES = ("ben-ux-writing", "fallback")
EVIDENCE_TYPES = ("shot", "console", "dom")
KNOWN_EXCLUSIONS = ("curly-braces", "dummy-amount-mismatch")
# 리뷰 전에 받는 맥락(브리프). SKILL.md 0단계의 질문 순서와 같다.
BRIEF_FIELDS = (("product", "어떤 제품인가요"), ("objective", "달성하려는 목표"), ("problem", "해결하려는 문제"),
                ("cause", "이 문제를 겪는 이유"),
                ("solution", "해결 방법"), ("user_value", "유저 기대효과"), ("business_value", "회사 기대효과"))
BRIEF_SOURCES = ("user", "inferred", "mixed")
SHOT_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")

UT_MODE = "virtual"
UT_AXES = ("device", "design", "writing")
UT_AXIS_VALUES = ("쉬움", "보통", "막힘")
UT_OUTCOMES = ("완주", "이탈")
UT_AGE_GROUPS = ("청년", "중년", "노년")
UT_LEVELS = ("상", "중", "하")
UT_OLD_PERSONA_KEYS = ("age_band", "tech")
UT_SCORE_KEY = re.compile(
    r"(score|rating|nps|sus|csat|satisfaction|rate|duration|seconds|minutes|time|점수|만족|완주율|시간|소요)", re.I)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GUIDELINE = os.path.join(HERE, "..", "references", "guideline.md")
DEFAULT_CASES = os.path.join(HERE, "..", "references", "cases.md")

ABSTRACT_FIX = re.compile(r"(명확히\s*(보여|표시|드러)|강조해|정리해|개선해)")
# 부재 주장("없어요", "안 보여요")과, 화면을 훑고 비슷한 요소의 위치를 적은 흔적
ABSENCE_CLAIM = re.compile(r"(없어요|없습니다|안\s*보여요|안\s*보입니다|보이지\s*않아요|빠져\s*있어요|빠져\s*있습니다|빠져요)")
SCAN_TRACE = re.compile(r"(훑|비슷한|가장\s*가까운|가까운|대신|멀리|다른\s*(위치|곳))")


def norm(name):
    return re.sub(r"\s+", " ", str(name)).strip().casefold()


def load_principles(path):
    """guideline.md에서 원칙 이름(과 별칭)을 읽어 정규화한 집합을 돌려준다."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    names = set()
    # 4절 QA 표의 첫 칸
    for line in text.splitlines():
        if line.startswith("|"):
            cell = line.strip("|").split("|")[0].strip()
            if cell and cell != "원칙" and not set(cell) <= set("-: "):
                names.add(norm(cell))
    # 3절 원칙 목록: "- **Name** (Alias): ..." 에서 영문으로 시작하는 이름과 별칭.
    # 3절 안에서만 읽어요(첫머리 "작업 유형별 최소 읽기"의 굵은 항목이 원칙으로 섞이지 않게).
    sec3 = re.search(r"^## 3\..*?(?=^## 4\.)", text, re.M | re.S)
    for m in re.finditer(r"^- \*\*([A-Za-z][^*]*)\*\*(?: \(([^)]*)\))?", sec3.group(0) if sec3 else text, re.M):
        names.add(norm(m.group(1)))
        alias = (m.group(2) or "").strip()
        if re.match(r"[A-Za-z]", alias):
            names.add(norm(alias))
    if len(names) < 10:
        raise ValueError(f"guideline.md에서 원칙 이름을 충분히 읽지 못했어요 ({len(names)}개). 파일 형식을 확인하세요")
    return names


def load_cases(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    cases = set(re.findall(r"^###\s+(C\d{3})\b", text, re.M))
    if not cases:
        raise ValueError("cases.md에서 C### 번호를 읽지 못했어요")
    return cases


def shot_ok(run, shot):
    """shot 경로가 RUN/shots 아래 실존 이미지 파일인지 확인한다(리포트 빌더와 같은 규칙).
    경로 이탈, shots 밖 파일, 이미지가 아닌 확장자는 차단한다."""
    if not isinstance(shot, str) or not shot.strip():
        return False
    try:
        sp = os.path.realpath(os.path.join(run, shot))
        base = os.path.realpath(os.path.join(run, "shots"))
        if os.path.splitext(sp)[1].lower() not in SHOT_EXT:
            return False
        return sp.startswith(base + os.sep) and os.path.isfile(sp)
    except (ValueError, OSError):
        return False


def asis_anchored(asis, aux_lines):
    """asis 인용이 화면 추출 텍스트(aux_text)에 실재하는지. 판정 불가면 True."""
    if not isinstance(aux_lines, list):
        return True
    hay = re.sub(r"\s+", "", " ".join(str(x) for x in aux_lines))
    if not hay:
        return True
    frags = [re.sub(r"\s+", "", f) for f in re.split(r"…|\.\.\.|/|\n", str(asis))]
    frags = [f for f in frags if len(f) >= 8]
    if not frags:
        return True
    return max(frags, key=len) in hay


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise ValueError(f"{os.path.basename(path)} JSON 파싱 실패: {e.lineno}행, {e.msg}")


def merge_parts(run):
    """review-part-*.json을 합친 dict를 돌려준다. 파트가 없으면 None."""
    parts = sorted(glob.glob(os.path.join(run, "review-part-*.json")))
    if not parts:
        return None
    rev = {"run": {}, "screens": [], "findings": [], "strengths": [], "checks_needed": [], "summary": {}}
    seen = set()
    for pp in parts:
        part = read_json(pp)
        if not isinstance(part, dict):
            raise ValueError(f"{os.path.basename(pp)} 최상위는 객체여야 해요")
        for key in ("screens", "findings", "strengths", "checks_needed"):
            if part.get(key) is not None and not isinstance(part[key], list):
                raise ValueError(f"{os.path.basename(pp)}: {key}는 목록이어야 해요")
        if not rev["run"] and isinstance(part.get("run"), dict):
            rev["run"] = part["run"]
        for s in part.get("screens") or []:
            sid = s.get("id") if isinstance(s, dict) else None
            if isinstance(sid, str) and sid in seen:
                continue
            if isinstance(sid, str):
                seen.add(sid)
            rev["screens"].append(s)
        for key in ("findings", "strengths", "checks_needed"):
            rev[key].extend(part.get(key) or [])
        summ = part.get("summary")
        if isinstance(summ, dict) and not blank(summ.get("headline")):
            rev["summary"] = summ
        if "ut" in part and "ut" not in rev:
            rev["ut"] = part["ut"]
    return rev


def blank(v):
    return not (isinstance(v, str) and v.strip())


def ut_persona_ids(ut):
    """ut.personas에서 문자열 id만 모은다. 형식이 틀리면 빈 집합."""
    if not isinstance(ut, dict) or not isinstance(ut.get("personas"), list):
        return set()
    return {p["id"] for p in ut["personas"] if isinstance(p, dict) and not blank(p.get("id"))}


def check_brief(brief, where, errors, warns):
    """리뷰 맥락(브리프)을 검사한다. 없으면 경고만 한다(맥락 없이도 리뷰는 할 수 있다)."""
    if brief is None:
        warns.append(f"{where}가 없어요. 리뷰 맥락을 받지 못했으면 화면에서 추론하고 brief.source를 inferred로 적으세요")
        return
    if not isinstance(brief, dict):
        errors.append(f"{where}는 객체여야 해요")
        return
    known = {k for k, _ in BRIEF_FIELDS} | {"source"}
    for k, v in brief.items():
        if k not in known:
            errors.append(f"{where}에 모르는 키가 있어요: {k!r}")
        elif k != "source" and v is not None and not isinstance(v, str):
            errors.append(f"{where}.{k}는 문자열이어야 해요")
    if brief.get("source") not in BRIEF_SOURCES:
        errors.append(f"{where}.source는 user, inferred, mixed 중 하나여야 해요")
    if all(blank(brief.get(k)) for k, _ in BRIEF_FIELDS):
        errors.append(f"{where}에 채운 항목이 하나도 없어요")


def scan_ut_scores(node, path, errors):
    """ut 안에 숫자 값이나 점수류 키가 있으면 오류. 정적 워크스루의 수치는 지어낸 값이라 금지다."""
    if isinstance(node, dict):
        for k, v in node.items():
            if UT_SCORE_KEY.search(str(k)):
                errors.append(f"{path}.{k}: 점수, 시간, 완주율 같은 수치 필드는 쓰지 않아요")
            scan_ut_scores(v, f"{path}.{k}", errors)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            scan_ut_scores(v, f"{path}[{i}]", errors)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        errors.append(f"{path}: 숫자 값은 쓰지 않아요 (가상 UT에는 수치가 없어요)")


def check_ut(ut, screens, fids, errors, warns):
    """ut(dict)를 검사하고 (persona_id, finding_id) 연결 집합을 돌려준다."""
    linked = set()
    scan_ut_scores(ut, "ut", errors)
    if ut.get("mode") != UT_MODE:
        errors.append(f"ut.mode는 'virtual' ({ut.get('mode')!r}). 실제 조사가 아니라 가상 반응이라는 표시예요")

    # personas
    pids = set()
    personas = ut.get("personas")
    if not isinstance(personas, list) or not personas:
        errors.append("ut.personas는 비어 있지 않은 목록이어야 해요")
        personas = []
    for i, p in enumerate(personas):
        if not isinstance(p, dict):
            errors.append(f"ut.personas[{i}]가 객체가 아니에요")
            continue
        pid = p.get("id")
        tag = f"ut.personas[{pid if isinstance(pid, str) else i}]"
        if blank(pid):
            errors.append(f"{tag}: id 비어 있음")
            continue
        if pid in pids:
            errors.append(f"{tag}: persona id 중복")
        pids.add(pid)
        for k in UT_OLD_PERSONA_KEYS:
            if k in p:
                errors.append(f"{tag}: 옛 필드 {k}는 쓰지 않아요 (age_group, device_level, ux_level로 바꿔요)")
        for k in ("age_group", "device_level", "ux_level", "name", "traits", "goal"):
            if blank(p.get(k)):
                errors.append(f"{tag}: {k} 비어 있음")
        if not blank(p.get("age_group")) and p["age_group"] not in UT_AGE_GROUPS:
            errors.append(f"{tag}: age_group은 청년|중년|노년 ({p['age_group']!r})")
        for k in ("device_level", "ux_level"):
            if not blank(p.get(k)) and p[k] not in UT_LEVELS:
                errors.append(f"{tag}: {k}는 상|중|하 ({p[k]!r})")

    # 기본 구성: 서로 다른 연령대 3명. 사용자가 따로 정했으면 무시해도 되는 경고예요
    ages = [p["age_group"] for p in personas
            if isinstance(p, dict) and p.get("age_group") in UT_AGE_GROUPS]
    if personas and (len(personas) != 3 or len(set(ages)) != len(ages)):
        warns.append(f"페르소나 구성: 기본은 서로 다른 연령대 3명인데 {len(personas)}명, 연령대 {sorted(set(ages))}이에요. "
                     "사용자가 인원이나 연령대를 정했다면 무시해도 되는 경고예요")

    # walks (personas와 1:1)
    walks = ut.get("walks")
    if not isinstance(walks, list):
        errors.append("ut.walks는 목록이어야 해요")
        return linked
    walked = {}
    for i, w in enumerate(walks):
        if not isinstance(w, dict):
            errors.append(f"ut.walks[{i}]가 객체가 아니에요")
            continue
        pid = w.get("persona_id")
        tag = f"ut.walks[{pid if isinstance(pid, str) else i}]"
        if not isinstance(pid, str) or pid not in pids:
            errors.append(f"{tag}: ut.personas에 없는 persona_id {pid!r}")
            continue
        if pid in walked:
            errors.append(f"{tag}: 같은 페르소나의 walk가 둘 이상이에요")
            continue
        walked[pid] = w

        outcome = w.get("outcome")
        if outcome not in UT_OUTCOMES:
            errors.append(f"{tag}: outcome은 완주|이탈 ({outcome!r})")
        stopped_at, stop_reason = w.get("stopped_at"), w.get("stop_reason")
        if outcome == "이탈":
            if blank(stopped_at):
                errors.append(f"{tag}: 이탈이면 stopped_at(멈춘 화면 id) 필수")
            elif stopped_at not in screens:
                errors.append(f"{tag}: stopped_at이 screens에 없는 화면 id {stopped_at!r}")
            if blank(stop_reason):
                errors.append(f"{tag}: 이탈이면 stop_reason(멈춘 이유) 필수")
        elif outcome == "완주" and (stopped_at is not None or stop_reason is not None):
            errors.append(f"{tag}: 완주인데 stopped_at 또는 stop_reason이 있어요")

        steps = w.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{tag}: steps는 비어 있지 않은 목록이어야 해요")
            continue
        for j, st in enumerate(steps):
            if not isinstance(st, dict):
                errors.append(f"{tag}.steps[{j}]가 객체가 아니에요")
                continue
            ssid = st.get("screen_id")
            stag = f"{tag}.steps[{ssid if isinstance(ssid, str) else j}]"
            if not isinstance(ssid, str) or ssid not in screens:
                errors.append(f"{stag}: screens에 없는 screen_id {ssid!r}")
            blocked = False
            medium = False
            for axis in UT_AXES:
                val = st.get(axis)
                if val not in UT_AXIS_VALUES:
                    errors.append(f"{stag}: {axis}는 쉬움|보통|막힘 ({val!r})")
                blocked = blocked or val == "막힘"
                medium = medium or val == "보통"
            if blank(st.get("quote")):
                errors.append(f"{stag}: quote 비어 있음 (그 사람 말투의 한 문장)")
            cause = st.get("cause")
            if cause is not None and not isinstance(cause, str):
                errors.append(f"{stag}: cause는 문자열이어야 해요")
            elif blocked and blank(cause):
                errors.append(f"{stag}: 막힘이 있으면 cause(무엇 때문인지 한 줄) 필수")
            fin = st.get("finding_ids")
            if not isinstance(fin, list) or not all(isinstance(x, str) for x in fin):
                errors.append(f"{stag}: finding_ids는 지적 id 목록이어야 해요 (없으면 빈 목록)")
                fin = []
            for x in fin:
                if x not in fids:
                    errors.append(f"{stag}: findings에 없는 finding id {x!r}")
                else:
                    linked.add((pid, x))
            if blocked and not fin:
                errors.append(f"{stag}: 막힘 반응은 finding_ids에 지적을 1개 이상 연결해야 해요")
            elif medium and not fin:
                warns.append(f"{stag}: 보통 반응인데 연결된 지적이 없어요. 고칠 점이 있으면 지적에 연결하세요")
        if outcome == "이탈" and not blank(stopped_at) and isinstance(steps[-1], dict) \
                and steps[-1].get("screen_id") != stopped_at:
            warns.append(f"{tag}: 마지막 step의 화면이 stopped_at({stopped_at})과 달라요")

    for pid in sorted(pids - set(walked)):
        errors.append(f"ut.personas[{pid}]: 짝이 되는 walk가 없어요 (페르소나와 walk는 1:1)")
    return linked


def check(rev, cap, run, principles, cases):
    """review(dict)를 검사해 (errors, warns)를 돌려준다. cap은 capture.json dict 또는 None."""
    errors, warns = [], []

    if not isinstance(rev, dict):
        return ["review 최상위는 객체여야 해요"], warns
    for key, want in (("screens", list), ("findings", list), ("strengths", list), ("checks_needed", list)):
        if not isinstance(rev.get(key), want):
            errors.append(f"{key}는 {want.__name__}여야 해요 (없거나 형식이 달라요)")
    if errors:
        return errors, warns

    # run
    r = rev.get("run")
    if not isinstance(r, dict):
        errors.append("run은 객체여야 해요")
        r = {}
    if blank(r.get("product_value")):
        errors.append("run.product_value 비어 있음 (제품 핵심 가치 한 줄)")
    if r.get("input_type") not in INPUT_TYPES:
        errors.append(f"run.input_type은 image|figma|live ({r.get('input_type')!r})")
    elif isinstance(cap, dict) and cap.get("input_type") and cap.get("input_type") != r.get("input_type"):
        warns.append(f"run.input_type({r.get('input_type')})이 capture.json({cap.get('input_type')})과 달라요")
    if r.get("writing_judge") not in WRITING_JUDGES:
        errors.append(f"run.writing_judge는 ben-ux-writing|fallback ({r.get('writing_judge')!r})")
    if "goal" in r and r["goal"] is not None and not isinstance(r["goal"], str):
        errors.append("run.goal은 문자열이어야 해요")
    check_brief(r.get("brief"), "run.brief", errors, warns)
    exclusions = r.get("exclusions")
    active = set()
    if exclusions is not None:
        if not isinstance(exclusions, list) or not all(isinstance(x, str) for x in exclusions):
            errors.append("run.exclusions는 문자열 목록이어야 해요")
        else:
            active = set(exclusions)
            for x in exclusions:
                if x not in KNOWN_EXCLUSIONS:
                    warns.append(f"run.exclusions '{x[:30]}'는 자동 검사 대상이 아니에요. 직접 지켰는지 확인하세요")

    cap_screens = {}
    if isinstance(cap, dict) and isinstance(cap.get("screens"), list):
        cap_screens = {s["id"]: s for s in cap["screens"]
                       if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]}

    # screens
    screens = {}
    if not rev["screens"]:
        errors.append("screens가 비어 있어요. 검토한 화면이 하나도 없으면 결과가 성립하지 않아요")
    for i, s in enumerate(rev["screens"]):
        if not isinstance(s, dict):
            errors.append(f"screens[{i}]가 객체가 아니에요")
            continue
        sid = s.get("id")
        tag = f"screens[{sid}]"
        if blank(sid):
            errors.append(f"screens[{i}]: id 비어 있음")
            continue
        if sid in screens:
            errors.append(f"{tag}: id 중복")
        screens[sid] = s
        for k in ("name", "screen_goal", "verdict"):
            if blank(s.get(k)):
                errors.append(f"{tag}: {k} 비어 있음")
        if not shot_ok(run, s.get("shot")):
            errors.append(f"{tag}: shot 파일이 없거나, RUN/shots/ 밖이거나, 이미지 확장자가 아니에요 ({s.get('shot')!r})")
        if cap_screens and sid not in cap_screens:
            errors.append(f"{tag}: capture.json에 없는 화면 id")

    # 커버리지
    if cap_screens:
        missing = [sid for sid, cs in cap_screens.items() if cs.get("shot") and sid not in screens]
        if missing:
            errors.append(f"capture 화면 {len(missing)}개가 screens에 없어요. 전수 검토가 계약이에요: {missing[:5]}")
        no_shot = [sid for sid, cs in cap_screens.items() if not cs.get("shot")]
        if no_shot:
            warns.append(f"capture에 shot이 없는 화면 {len(no_shot)}개는 검토 대상에서 빠졌어요: {no_shot[:5]}")
    else:
        warns.append("capture.json이 없거나 화면이 없어서 전수 커버리지를 검사하지 못했어요")

    # findings
    ut = rev.get("ut")
    ut_pids = ut_persona_ids(ut)
    fids = set()
    seen_combo = {}
    for i, f in enumerate(rev["findings"]):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}]가 객체가 아니에요")
            continue
        fid = f.get("id")
        tag = f"findings[{fid or i}] '{str(f.get('title') or '')[:24]}'"
        if blank(fid):
            errors.append(f"findings[{i}]: id 비어 있음")
        elif not isinstance(fid, str):
            errors.append(f"findings[{i}]: id는 문자열이어야 해요")
        elif fid in fids:
            errors.append(f"{tag}: finding id 중복")
        else:
            fids.add(fid)
        for k in ("title", "observation", "why", "fix"):
            if blank(f.get(k)):
                errors.append(f"{tag}: {k} 비어 있거나 문자열이 아니에요")
        sev, lens = f.get("severity"), f.get("lens")
        if sev not in SEVERITY:
            errors.append(f"{tag}: severity는 심각|중간|낮음 ({sev!r})")
        if lens not in LENS:
            errors.append(f"{tag}: lens는 화면|흐름|문구|접근성 ({lens!r})")
        if sev == "심각" and blank(f.get("tobe")):
            errors.append(f"{tag}: 심각 지적은 tobe(수정 후 모습) 필수")
        if lens == "문구":
            if blank(f.get("asis")):
                errors.append(f"{tag}: lens=문구는 asis(화면에 적힌 그대로) 필수")
            if blank(f.get("tobe")):
                errors.append(f"{tag}: lens=문구는 tobe(바꿀 문구) 필수")

        # screen_id
        sid = f.get("screen_id", "<missing>")
        if sid == "<missing>":
            errors.append(f"{tag}: screen_id 키가 없어요 (흐름 지적이 아니면 화면 id, 아니면 null)")
        elif sid is None:
            if lens != "흐름":
                errors.append(f"{tag}: screen_id가 null인 지적은 lens=흐름만 허용해요")
        elif not isinstance(sid, str) or sid not in screens:
            errors.append(f"{tag}: screens에 없는 screen_id {sid!r}")

        # principle, case
        if "principle" not in f:
            errors.append(f"{tag}: principle 키가 없어요 (원칙 이름 또는 null)")
        else:
            p = f.get("principle")
            if p is not None:
                if blank(p) or norm(p) not in principles:
                    errors.append(f"{tag}: guideline.md에 없는 원칙 이름 {p!r}. 연결이 약하면 null")
            elif f.get("case"):
                errors.append(f"{tag}: principle이 null이면 case도 비워요")
        c = f.get("case")
        if c is not None and (not isinstance(c, str) or c not in cases):
            errors.append(f"{tag}: cases.md에 없는 사례 번호 {c!r}")

        # evidence
        ev = f.get("evidence")
        if not isinstance(ev, dict):
            errors.append(f"{tag}: evidence는 {{shot, where, type}} 객체여야 해요")
        else:
            et = ev.get("type")
            if et not in EVIDENCE_TYPES:
                errors.append(f"{tag}: evidence.type은 shot|console|dom ({et!r})")
            if blank(ev.get("where")):
                errors.append(f"{tag}: evidence.where 비어 있음 (화면 안 위치)")
            eshot = ev.get("shot")
            if et == "shot" or (et in EVIDENCE_TYPES and eshot):
                if not shot_ok(run, eshot):
                    errors.append(f"{tag}: evidence.shot 파일이 없거나, RUN/shots/ 밖이거나, 이미지 확장자가 아니에요 ({eshot!r})")
                elif isinstance(sid, str) and sid in screens and os.path.normpath(str(eshot)) != os.path.normpath(str(screens[sid].get("shot"))):
                    warns.append(f"{tag}: evidence.shot이 screen_id의 화면 shot과 달라요")
            if et == "shot" and any(k in str(ev.get("where") or "").lower() for k in ("콘솔", "console", "devtools", "dom")):
                warns.append(f"{tag}: evidence.where가 콘솔/DOM을 말해요. 기술 근거면 type을 console|dom으로 밝히세요")

        # asis 인용이 추출 텍스트(aux_text)에 있는지(있을 때만)
        if isinstance(sid, str) and not blank(f.get("asis")):
            aux = (cap_screens.get(sid) or {}).get("aux_text")
            if not asis_anchored(f["asis"], aux):
                warns.append(f"{tag}: asis 인용이 capture.json의 화면 추출 텍스트에 없어요. 화면에 적힌 그대로인지 다시 확인하세요")

        # 문구 fallback
        if lens == "문구" and r.get("writing_judge") == "fallback" and blank(f.get("confirm_needed")):
            errors.append(f"{tag}: writing_judge가 fallback이면 confirm_needed에 ben-ux-writing 기준 미적용을 남겨요")
        if "confirm_needed" in f and f["confirm_needed"] is not None and not isinstance(f["confirm_needed"], str):
            errors.append(f"{tag}: confirm_needed는 문자열이어야 해요")

        # 고쳤는지 확인하는 기준
        dw = f.get("done_when")
        if dw is not None and not isinstance(dw, str):
            errors.append(f"{tag}: done_when은 문자열이어야 해요")
        elif sev == "심각" and blank(dw):
            warns.append(f"{tag}: 심각 지적에는 done_when(고쳤는지 확인하는 기준 한두 줄)을 권해요")

        # 부재 주장은 훑은 흔적이 있어야 한다(휴리스틱)
        if sev == "심각" and ABSENCE_CLAIM.search(f"{f.get('title') or ''} {f.get('observation') or ''}"):
            trail = f"{f.get('observation') or ''} {f.get('confirm_needed') or ''}"
            if not SCAN_TRACE.search(trail):
                warns.append(f"{tag}: 없다는 주장인데 화면을 훑은 흔적이 없어요. 화면 전체를 다시 보고 "
                             "비슷한 요소의 위치나 가장 가까운 요소를 observation이나 confirm_needed에 적으세요")

        # 가상 UT에서 나온 지적 표시
        fu = f.get("from_ut")
        if fu is not None:
            if not isinstance(fu, list) or not all(isinstance(x, str) for x in fu):
                errors.append(f"{tag}: from_ut는 페르소나 id 목록이어야 해요")
            else:
                for pid in fu:
                    if pid not in ut_pids:
                        errors.append(f"{tag}: from_ut의 persona '{pid}'가 ut.personas에 없어요")

        # 추상 수정안
        if isinstance(f.get("fix"), str) and ABSTRACT_FIX.search(f["fix"]) and blank(f.get("tobe")):
            warns.append(f"{tag}: fix가 추상적이에요. 무엇을 어디에 어떻게 바꾸는지 tobe로 구체화하세요")

        # 제외 규칙
        blob = " ".join(str(f.get(k) or "") for k in ("title", "observation", "why", "asis"))
        if "curly-braces" in active and re.search(r"\{[^{}]*\}", blob):
            warns.append(f"{tag}: curly-braces 제외 규칙이 켜져 있는데 중괄호를 언급해요")
        if "dummy-amount-mismatch" in active and re.search(r"(금액|가격|\d[\d,]*\s*원)", blob) and re.search(r"(불일치|다르|달라|서로 다른)", blob):
            warns.append(f"{tag}: dummy-amount-mismatch 제외 규칙이 켜져 있는데 금액 불일치를 지적한 것 같아요")

        key = (str(f.get("title") or "").strip(), sid if isinstance(sid, str) or sid is None else None)
        seen_combo[key] = seen_combo.get(key, 0) + 1

    for (ttl, sid), n in seen_combo.items():
        if n > 1 and ttl:
            warns.append(f"같은 제목의 중복 지적 {n}건: '{ttl[:30]}' (screen={sid})")

    # 이슈 없는 화면의 verdict는 문제를 서술하면 안 된다(역방향 검사)
    issue_sids = {f["screen_id"] for f in rev["findings"]
                  if isinstance(f, dict) and isinstance(f.get("screen_id"), str) and f["screen_id"]}
    ok_words = ("문제없", "문제 없", "이슈 없", "통과", "정석", "잘 지켜")
    for sid, s in screens.items():
        v = str(s.get("verdict") or "")
        if v and sid not in issue_sids and not any(w in v for w in ok_words):
            warns.append(f"screens[{sid}]: verdict가 문제를 말하는데 연결된 지적이 없어요. 지적을 만들거나 통과 문구로 바꾸세요")

    # strengths
    for i, st in enumerate(rev["strengths"]):
        if not isinstance(st, dict) or blank(st.get("note")):
            errors.append(f"strengths[{i}]: {{note, principle, screen_id}} 객체이고 note가 있어야 해요")
            continue
        p = st.get("principle")
        if p is not None and (blank(p) or norm(p) not in principles):
            errors.append(f"strengths[{i}]: guideline.md에 없는 원칙 이름 {p!r}")
        ssid = st.get("screen_id")
        if ssid is not None and (not isinstance(ssid, str) or ssid not in screens):
            errors.append(f"strengths[{i}]: screens에 없는 screen_id '{ssid}'")

    # checks_needed
    for i, ck in enumerate(rev["checks_needed"]):
        if not isinstance(ck, dict) or blank(ck.get("what")) or blank(ck.get("how")):
            errors.append(f"checks_needed[{i}]: {{what, how}} 객체이고 둘 다 있어야 해요")

    # summary
    summ = rev.get("summary")
    if not isinstance(summ, dict):
        errors.append("summary는 객체여야 해요")
    else:
        if blank(summ.get("headline")):
            errors.append("summary.headline 비어 있음")
        top = summ.get("top")
        if not isinstance(top, list):
            errors.append("summary.top은 finding id 목록이어야 해요")
        else:
            for t in top:
                if not isinstance(t, str) or t not in fids:
                    errors.append(f"summary.top에 없는 finding id '{t}'")
            if not top and fids:
                warns.append("summary.top 비어 있음. 먼저 고칠 지적을 적어요")
            if len(top) > 5:
                errors.append("summary.top은 최대 5개예요")

    # ut (가상 UT)
    if "ut" in rev:
        if not isinstance(ut, dict):
            errors.append("ut는 객체여야 해요")
        else:
            linked = check_ut(ut, screens, fids, errors, warns)
            for f in rev["findings"]:
                fu = f.get("from_ut") if isinstance(f, dict) else None
                if isinstance(fu, list) and isinstance(f.get("id"), str):
                    for pid in fu:
                        if isinstance(pid, str) and pid in ut_pids and (pid, f["id"]) not in linked:
                            warns.append(f"findings[{f['id']}]: from_ut의 '{pid}' walk에서 이 지적을 연결한 step이 없어요")

    return errors, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="./run")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--guideline", default=DEFAULT_GUIDELINE)
    ap.add_argument("--cases", default=DEFAULT_CASES)
    a = ap.parse_args()

    try:
        principles = load_principles(a.guideline)
        cases = load_cases(a.cases)
        cap_path = os.path.join(a.run, "capture.json")
        cap = read_json(cap_path) if os.path.exists(cap_path) else None
        rev_path = os.path.join(a.run, "review.json")
        rev = merge_parts(a.run)
        if rev is not None:
            # 파트가 있으면 항상 다시 합쳐 옛 합본이 남지 않게 한다
            existed = os.path.exists(rev_path)
            with open(rev_path, "w", encoding="utf-8") as fh:
                json.dump(rev, fh, ensure_ascii=False, indent=1)
            print(f"샤드 합침 -> review.json{' (기존 파일 덮어씀)' if existed else ''} "
                  f"(화면 {len(rev['screens'])} · 지적 {len(rev['findings'])})")
        elif os.path.exists(rev_path):
            rev = read_json(rev_path)
        else:
            sys.exit(f"review.json이 없어요 ({rev_path}). 샤딩이면 review-part-1.json 등이 필요해요")
    except (ValueError, OSError) as e:
        sys.exit(str(e))

    errors, warns = check(rev, cap, a.run, principles, cases)
    for w in warns:
        print(f"경고: {w}")
    for e in errors:
        print(f"오류: {e}")
    n_f = len(rev.get("findings", [])) if isinstance(rev, dict) and isinstance(rev.get("findings"), list) else 0
    print(f"검증: 오류 {len(errors)} · 경고 {len(warns)} · 지적 {n_f}")
    if errors or (a.strict and warns):
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
