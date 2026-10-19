# -*- coding: utf-8 -*-
"""
ben-ux-feedback 코어 스크립트 테스트 (표준 라이브러리 unittest).

실행 (저장소 루트에서):
  python3 -m unittest discover -s tests -v
"""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skill", "ben-ux-feedback")
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)

import build_compare  # noqa: E402
import build_report  # noqa: E402
import detect_input  # noqa: E402
import image_capture  # noqa: E402
import validate  # noqa: E402

GUIDELINE = os.path.join(SKILL, "references", "guideline.md")
CASES = os.path.join(SKILL, "references", "cases.md")
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def write(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as fh:
        fh.write(data)


def good_review():
    return {
        "run": {"goal": "테스트", "product_value": "지출을 빠르게 기록한다",
                "input_type": "image", "writing_judge": "ben-ux-writing",
                "brief": {"product": "가계부 앱", "objective": "매일 기록하게 하기", "source": "user"}},
        "screens": [{"id": "home", "name": "홈", "shot": "shots/home.png",
                     "screen_goal": "지출을 기록한다", "verdict": "저장 버튼이 가려져요."}],
        "findings": [{
            "id": "F01", "screen_id": "home", "severity": "심각", "lens": "화면",
            "title": "저장 버튼이 가려져요", "observation": "하단 버튼이 키보드 밑에 있어요.",
            "why": "저장 방법이 안 보여 입력을 잃어요.", "principle": "Clear Action",
            "fix": "버튼을 키보드 위에 고정해요.", "tobe": "키보드 위에 '저장하기'를 고정해요.",
            "done_when": "키보드를 연 상태에서도 '저장하기'가 화면에 보여요.",
            "evidence": {"shot": "shots/home.png", "where": "화면 하단", "type": "shot"},
            "pin": {"x": 0.5, "y": 0.9},
        }],
        "strengths": [],
        "checks_needed": [],
        "summary": {"headline": "저장 버튼 문제가 가장 커요.", "top": ["F01"]},
    }


class RunCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.run_dir = os.path.join(self.tmp, "run")
        write(os.path.join(self.run_dir, "shots", "home.png"), PNG)
        write(os.path.join(self.run_dir, "capture.json"), json.dumps({
            "input_type": "image",
            "screens": [{"id": "home", "name": "홈", "shot": "shots/home.png"}],
            "edges": []}))
        self.principles = validate.load_principles(GUIDELINE)
        self.cases = validate.load_cases(CASES)

    def run_check(self, rev, cap="auto"):
        if cap == "auto":
            with open(os.path.join(self.run_dir, "capture.json"), encoding="utf-8") as fh:
                cap = json.load(fh)
        return validate.check(rev, cap, self.run_dir, self.principles, self.cases)

    def assertHasError(self, errors, needle):
        self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")


class DetectInputTest(RunCase):
    def test_figma_url_converts_node_id_and_prefers_branch(self):
        r = detect_input.detect("https://www.figma.com/design/ABC123/name?node-id=6129-63060")
        self.assertEqual((r["type"], r["file_key"], r["node_id"]), ("figma", "ABC123", "6129:63060"))
        b = detect_input.detect("https://www.figma.com/design/ABC123/branch/BR9/name")
        self.assertEqual(b["file_key"], "BR9")

    def test_live_url_and_localhost(self):
        self.assertEqual(detect_input.detect("http://localhost:3000/x")["localhost"], True)
        r = detect_input.detect("example.com/app")
        self.assertEqual((r["type"], r["url"], r["localhost"]), ("live", "https://example.com/app", False))

    def test_image_file_and_folder_natural_order(self):
        for n in ("10.png", "2.png", "1.png", "note.txt"):
            write(os.path.join(self.tmp, "imgs", n), PNG)
        folder = detect_input.detect(os.path.join(self.tmp, "imgs"))
        self.assertEqual((folder["type"], folder["kind"]), ("image", "folder"))
        self.assertEqual(folder["files"], ["1.png", "2.png", "10.png"])
        f = detect_input.detect(os.path.join(self.tmp, "imgs", "2.png"))
        self.assertEqual((f["type"], f["kind"], f["count"]), ("image", "file", 1))

    def test_unknown_inputs(self):
        self.assertEqual(detect_input.detect("")["type"], "unknown")
        self.assertEqual(detect_input.detect(os.path.join(self.tmp, "nope.png"))["type"], "unknown")
        os.makedirs(os.path.join(self.tmp, "empty"))
        self.assertEqual(detect_input.detect(os.path.join(self.tmp, "empty"))["type"], "unknown")
        write(os.path.join(self.tmp, "a.txt"), "x")
        self.assertEqual(detect_input.detect(os.path.join(self.tmp, "a.txt"))["type"], "unknown")


class ImageCaptureTest(RunCase):
    def test_folder_copies_and_writes_capture(self):
        for n in ("02 입력.png", "01 홈.PNG"):
            write(os.path.join(self.tmp, "in", n), PNG)
        out = os.path.join(self.tmp, "out")
        cap = image_capture.capture(os.path.join(self.tmp, "in"), out)
        self.assertEqual(cap["input_type"], "image")
        self.assertEqual([s["name"] for s in cap["screens"]], ["01 홈", "02 입력"])
        for s in cap["screens"]:
            self.assertTrue(os.path.isfile(os.path.join(out, s["shot"])))
        saved = json.load(open(os.path.join(out, "capture.json"), encoding="utf-8"))
        self.assertEqual(saved["source"]["count"], 2)
        self.assertNotIn(self.tmp, json.dumps(saved, ensure_ascii=False))

    def test_main_prints_shot_paths_for_next_turn(self):
        write(os.path.join(self.tmp, "in", "01-Home.png"), PNG)
        out = os.path.join(self.tmp, "out")
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["image_capture.py", os.path.join(self.tmp, "in"), "--run", out]), \
                contextlib.redirect_stdout(buf):
            image_capture.main()
        self.assertIn("shots/01-home.png", buf.getvalue())

    def test_duplicate_slugs_get_unique_ids(self):
        write(os.path.join(self.tmp, "in", "a.png"), PNG)
        write(os.path.join(self.tmp, "in", "a.jpg"), PNG)
        cap = image_capture.capture(os.path.join(self.tmp, "in"), os.path.join(self.tmp, "out"))
        ids = [s["id"] for s in cap["screens"]]
        self.assertEqual(len(set(ids)), 2)

    def test_no_images_raises(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        with self.assertRaises(ValueError):
            image_capture.capture(os.path.join(self.tmp, "empty"), os.path.join(self.tmp, "out"))
        with self.assertRaises(ValueError):
            image_capture.capture(os.path.join(self.tmp, "missing.png"), os.path.join(self.tmp, "out"))


class ValidateTest(RunCase):
    def test_principles_and_cases_are_read_from_reference_files(self):
        for name in ("clear action", "one thing", "less policy", "no more loading"):
            self.assertIn(name, self.principles)
        self.assertNotIn("p0", self.principles)
        self.assertIn("C001", self.cases)

    def test_valid_review_passes(self):
        errors, warns = self.run_check(good_review())
        self.assertEqual(errors, [])

    def test_severe_without_tobe_fails(self):
        rev = good_review()
        del rev["findings"][0]["tobe"]
        self.assertHasError(self.run_check(rev)[0], "tobe")

    def test_severe_absence_claim_without_scan_trail_warns(self):
        rev = good_review()
        f = rev["findings"][0]
        f.update({"title": "광고 고지가 없어요", "observation": "검색창 아래에 고지가 없어요."})
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertTrue(any("훑은 흔적" in w for w in warns), warns)

    def test_absence_claim_with_scan_trail_or_lower_severity_does_not_warn(self):
        rev = good_review()
        f = rev["findings"][0]
        f.update({"title": "광고 고지가 없어요",
                  "observation": "화면 전체를 훑어도 비슷한 고지는 없고, 가장 가까운 것은 하단 약관 링크뿐이에요."})
        self.assertFalse(any("훑은 흔적" in w for w in self.run_check(rev)[1]))
        f.update({"observation": "검색창 아래에 고지가 없어요.", "confirm_needed": "화면 밖에 비슷한 고지가 멀리 있는지 확인해요."})
        self.assertFalse(any("훑은 흔적" in w for w in self.run_check(rev)[1]))
        f.update({"observation": "검색창 아래에 고지가 없어요.", "confirm_needed": None, "severity": "중간"})
        self.assertFalse(any("훑은 흔적" in w for w in self.run_check(rev)[1]))

    def test_unknown_principle_fails_and_null_is_allowed(self):
        rev = good_review()
        rev["findings"][0]["principle"] = "Tap & Scroll"
        self.assertHasError(self.run_check(rev)[0], "원칙 이름")
        rev["findings"][0]["principle"] = None
        self.assertEqual(self.run_check(rev)[0], [])

    def test_unknown_case_fails(self):
        rev = good_review()
        rev["findings"][0]["case"] = "C999"
        self.assertHasError(self.run_check(rev)[0], "사례 번호")
        rev["findings"][0]["case"] = "C177"
        self.assertEqual(self.run_check(rev)[0], [])

    def test_writing_lens_requires_asis_and_tobe(self):
        rev = good_review()
        f = rev["findings"][0]
        f.update({"lens": "문구", "severity": "중간"})
        errors, _ = self.run_check(rev)
        self.assertHasError(errors, "asis")
        f["asis"] = "선택"
        del f["tobe"]
        self.assertHasError(self.run_check(rev)[0], "tobe")

    def test_old_priority_scale_is_rejected(self):
        rev = good_review()
        rev["findings"][0]["severity"] = "P0"
        self.assertHasError(self.run_check(rev)[0], "severity")

    def test_missing_shot_fails(self):
        rev = good_review()
        rev["findings"][0]["evidence"]["shot"] = "shots/none.png"
        self.assertHasError(self.run_check(rev)[0], "evidence.shot")
        rev = good_review()
        rev["screens"][0]["shot"] = "../outside.png"
        self.assertHasError(self.run_check(rev)[0], "shot")

    def test_null_screen_id_only_for_flow_lens(self):
        rev = good_review()
        rev["findings"][0]["screen_id"] = None
        self.assertHasError(self.run_check(rev)[0], "lens=흐름")
        rev["findings"][0]["lens"] = "흐름"
        self.assertEqual(self.run_check(rev)[0], [])

    def test_uncovered_capture_screen_fails(self):
        write(os.path.join(self.run_dir, "shots", "add.png"), PNG)
        cap = {"input_type": "image", "screens": [
            {"id": "home", "name": "홈", "shot": "shots/home.png"},
            {"id": "add", "name": "추가", "shot": "shots/add.png"}]}
        self.assertHasError(self.run_check(good_review(), cap)[0], "전수 검토")

    def test_summary_top_must_reference_findings(self):
        rev = good_review()
        rev["summary"]["top"] = ["F99"]
        self.assertHasError(self.run_check(rev)[0], "summary.top")

    def test_exclusion_warns_but_does_not_fail(self):
        rev = good_review()
        rev["run"]["exclusions"] = ["curly-braces", "팀 약관 문구 제외"]
        rev["findings"][0]["observation"] = "안내에 {name} 토큰이 그대로 보여요."
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertTrue(any("curly-braces" in w for w in warns))
        self.assertTrue(any("자동 검사 대상이 아니" in w for w in warns))

    def test_fallback_writing_finding_requires_confirm_needed(self):
        rev = good_review()
        rev["run"]["writing_judge"] = "fallback"
        rev["findings"][0].update({"lens": "문구", "severity": "중간", "asis": "선택"})
        self.assertHasError(self.run_check(rev)[0], "fallback")
        rev["findings"][0]["confirm_needed"] = "ben-ux-writing 기준 미적용"
        self.assertEqual(self.run_check(rev)[0], [])

    def test_null_principle_with_case_is_error(self):
        rev = good_review()
        rev["findings"][0].update({"principle": None, "case": "C177"})
        self.assertHasError(self.run_check(rev)[0], "case도 비워요")

    def test_summary_top_over_five_is_error(self):
        rev = good_review()
        rev["summary"]["top"] = ["F01"] * 6
        self.assertHasError(self.run_check(rev)[0], "최대 5개")

    def test_done_when_warns_for_severe_and_checks_type(self):
        rev = good_review()
        del rev["findings"][0]["done_when"]
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertTrue(any("done_when" in w for w in warns))
        rev["findings"][0]["done_when"] = "키보드가 올라와도 '저장하기'가 보여요."
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertFalse(any("done_when" in w for w in warns))
        rev["findings"][0]["severity"] = "중간"
        del rev["findings"][0]["done_when"]
        self.assertFalse(any("done_when" in w for w in self.run_check(rev)[1]))
        rev["findings"][0]["done_when"] = ["목록"]
        self.assertHasError(self.run_check(rev)[0], "done_when은 문자열")

    def test_empty_screens_is_error(self):
        rev = good_review()
        rev["screens"] = []
        rev["findings"] = []
        rev["summary"]["top"] = []
        self.assertHasError(self.run_check(rev)[0], "screens가 비어")

    def test_non_string_ids_do_not_crash(self):
        rev = good_review()
        rev["findings"][0]["screen_id"] = ["home"]
        errors, _ = self.run_check(rev)
        self.assertHasError(errors, "screens에 없는 screen_id")
        cap = {"input_type": "image", "screens": [
            {"id": ["home"], "shot": "shots/home.png"}, {"id": "home", "shot": "shots/home.png"}]}
        self.assertEqual(self.run_check(good_review(), cap)[0], [])

    def test_amount_exclusion_ignores_word_won_in_other_words(self):
        rev = good_review()
        rev["run"]["exclusions"] = ["dummy-amount-mismatch"]
        rev["findings"][0]["why"] = "원칙과 다르게 버튼이 가려져 원인을 몰라요."
        self.assertEqual(self.run_check(rev)[1], [])
        rev["findings"][0]["why"] = "버튼의 금액이 화면마다 달라요."
        self.assertTrue(any("dummy-amount-mismatch" in w for w in self.run_check(rev)[1]))

    def test_pin_is_optional_but_warned(self):
        rev = good_review()
        self.assertFalse(any("pin" in w for w in self.run_check(rev)[1]))
        del rev["findings"][0]["pin"]
        self.assertTrue(any("pin이 없어" in w for w in self.run_check(rev)[1]))
        rev["findings"][0]["pin"] = {"x": 1.5, "y": 0.2}
        warns = self.run_check(rev)[1]
        self.assertTrue(any("pin은" in w for w in warns))
        self.assertEqual(self.run_check(rev)[0], [])   # 경고일 뿐 오류는 아니에요
        rev["findings"][0]["pin"] = {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0}
        self.assertTrue(any("pin은" in w for w in self.run_check(rev)[1]))
        rev["findings"][0]["pin"] = {"x": 0.1, "y": 0.2, "w": 0.5}   # w, h는 함께
        self.assertTrue(any("pin은" in w for w in self.run_check(rev)[1]))
        rev["findings"][0]["pin"] = {"x": 0.8, "y": 0.8, "w": 0.5, "h": 0.5}
        self.assertTrue(any("이미지 밖" in w for w in self.run_check(rev)[1]))

    def test_pin_box_clamps_and_rejects_bad_values(self):
        pb = build_report.pin_box
        self.assertEqual(pb({"pin": {"x": 0.8, "y": 0.8, "w": 0.5, "h": 0.5}}), (0.8, 0.8, 0.2, 0.2))
        self.assertEqual(pb({"pin": {"x": 0.3, "y": 0.4}}), (0.3, 0.4, None, None))
        self.assertEqual(pb({"pin": {"x": 0.3, "y": 0.4, "w": 0.5}}), (0.3, 0.4, None, None))   # 한쪽만 있으면 점
        self.assertEqual(pb({"pin": {"x": 1.0, "y": 0.4, "w": 0.5, "h": 0.5}})[2:], (None, None))   # 남는 폭이 0이면 점
        for bad in ({"x": "a", "y": 0.1}, {"x": True, "y": 0.1}, {"x": float("nan"), "y": 0.1}, "x", None):
            self.assertIsNone(pb({"pin": bad}), repr(bad))
        self.assertEqual(build_report.pin_point((0.2, 0.2, 0.4, 0.2)), (0.4, 0.3))
        self.assertEqual(build_report.pin_point((0.2, 0.2, None, None)), (0.2, 0.2))

    def test_asis_must_appear_in_aux_text_when_available(self):
        rev = good_review()
        rev["findings"][0].update({"lens": "문구", "severity": "중간", "asis": "변동비를 선택해 주세요 지금"})
        cap = {"input_type": "image", "screens": [
            {"id": "home", "shot": "shots/home.png", "aux_text": ["변동비를 선택해 주세요 지금"]}]}
        self.assertFalse(any("asis 인용" in w for w in self.run_check(rev, cap)[1]))
        cap["screens"][0]["aux_text"] = ["전혀 다른 문구가 여기 적혀 있어요"]
        self.assertTrue(any("asis 인용" in w for w in self.run_check(rev, cap)[1]))
        del cap["screens"][0]["aux_text"]
        self.assertFalse(any("asis 인용" in w for w in self.run_check(rev, cap)[1]))

    def test_shot_must_be_an_image_file(self):
        rev = good_review()
        rev["screens"][0]["shot"] = "capture.json"
        rev["findings"][0]["evidence"]["shot"] = "capture.json"
        errors, _ = self.run_check(rev)
        self.assertHasError(errors, "이미지 확장자")
        write(os.path.join(self.run_dir, "shots", "icon.svg"), "<svg/>")
        self.assertTrue(validate.shot_ok(self.run_dir, "shots/icon.svg"))

    def test_shot_must_be_under_shots_dir_like_the_builder(self):
        write(os.path.join(self.run_dir, "img", "a.png"), PNG)
        write(os.path.join(self.run_dir, "root.png"), PNG)
        self.assertTrue(validate.shot_ok(self.run_dir, "shots/home.png"))
        for bad in ("img/a.png", "root.png", "shots/../root.png", "../run/root.png", "shots", "shots/\0x.png"):
            self.assertFalse(validate.shot_ok(self.run_dir, bad), repr(bad))
            # 검증기가 막는 경로는 빌더도 받지 않고, 검증기가 받는 경로는 빌더도 받아요
            self.assertIsNone(build_report.safe_shot(self.run_dir, bad), repr(bad))
        self.assertIsNotNone(build_report.safe_shot(self.run_dir, "shots/home.png"))
        rev = good_review()
        rev["screens"][0]["shot"] = "img/a.png"
        rev["findings"][0]["evidence"]["shot"] = "img/a.png"
        errors, _ = self.run_check(rev)
        self.assertHasError(errors, "RUN/shots/")
        self.assertEqual(sum("RUN/shots/" in e for e in errors), 2)

    def test_stale_review_json_is_replaced_by_parts(self):
        write(os.path.join(self.run_dir, "review.json"), json.dumps({"stale": True}))
        write(os.path.join(self.run_dir, "review-part-1.json"), json.dumps(good_review(), ensure_ascii=False))
        merged = validate.merge_parts(self.run_dir)
        self.assertEqual(merged["screens"][0]["id"], "home")
        self.assertNotIn("stale", merged)
        res = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "validate.py"), "--run", self.run_dir],
                             capture_output=True, text=True, encoding="utf-8",
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.assertIn("PASS", res.stdout, res.stdout + res.stderr)
        saved = json.load(open(os.path.join(self.run_dir, "review.json"), encoding="utf-8"))
        self.assertNotIn("stale", saved)

    def test_merge_parts_rejects_non_list_sections(self):
        bad = good_review()
        bad["findings"] = {"F01": "x"}
        write(os.path.join(self.run_dir, "review-part-1.json"), json.dumps(bad, ensure_ascii=False))
        with self.assertRaises(ValueError):
            validate.merge_parts(self.run_dir)

    def test_shards_are_merged_and_duplicate_ids_fail(self):
        p1, p2 = good_review(), good_review()
        write(os.path.join(self.run_dir, "shots", "add.png"), PNG)
        p2["screens"] = [{"id": "add", "name": "추가", "shot": "shots/add.png",
                          "screen_goal": "금액을 입력한다", "verdict": "문제없어요."}]
        p2["findings"] = []
        p2["summary"] = {"headline": "합침", "top": ["F01"]}
        write(os.path.join(self.run_dir, "review-part-1.json"), json.dumps(p1, ensure_ascii=False))
        write(os.path.join(self.run_dir, "review-part-2.json"), json.dumps(p2, ensure_ascii=False))
        merged = validate.merge_parts(self.run_dir)
        self.assertEqual([s["id"] for s in merged["screens"]], ["home", "add"])
        self.assertEqual(merged["summary"]["headline"], "합침")
        cap = {"input_type": "image", "screens": [
            {"id": "home", "shot": "shots/home.png"}, {"id": "add", "shot": "shots/add.png"}]}
        self.assertEqual(self.run_check(merged, cap)[0], [])
        merged["findings"].append(copy.deepcopy(merged["findings"][0]))
        self.assertHasError(self.run_check(merged, cap)[0], "id 중복")


def good_ut():
    return {
        "mode": "virtual",
        "personas": [{"id": "p-senior-dlo-ulo", "age_group": "노년", "device_level": "하", "ux_level": "하",
                      "name": "박순자",
                      "traits": "68세, 은행 앱만 써요. 작은 글씨는 돋보기로 봐요.", "goal": "오늘 쓴 돈을 적는다"}],
        "walks": [{"persona_id": "p-senior-dlo-ulo", "outcome": "이탈", "stopped_at": "home",
                   "stop_reason": "저장 버튼을 못 찾아서 포기했어요",
                   "steps": [{"screen_id": "home", "device": "막힘", "design": "보통", "writing": "쉬움",
                              "quote": "저장은 어디서 하는 거예요?",
                              "cause": "저장 버튼이 키보드에 가려졌어요", "finding_ids": ["F01"]}]}],
    }


class UtValidateTest(RunCase):
    def review_with_ut(self):
        rev = good_review()
        rev["ut"] = good_ut()
        rev["findings"][0]["from_ut"] = ["p-senior-dlo-ulo"]
        return rev

    def test_valid_ut_passes(self):
        errors, warns = self.run_check(self.review_with_ut())
        self.assertEqual(errors, [])
        self.assertEqual([w for w in warns if "ut" in w or "from_ut" in w], [])

    def test_persona_composition_warns_when_not_three_distinct_ages(self):
        rev = self.review_with_ut()  # 노년 1명
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertTrue(any("페르소나 구성" in w and "무시해도 되는 경고" in w for w in warns), warns)

        ut = rev["ut"]
        for pid, age in (("p-youth", "청년"), ("p-mid", "중년")):
            p = copy.deepcopy(ut["personas"][0])
            p.update({"id": pid, "age_group": age})
            ut["personas"].append(p)
            w = copy.deepcopy(ut["walks"][0])
            w["persona_id"] = pid
            ut["walks"].append(w)
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertFalse(any("페르소나 구성" in w for w in warns), warns)

        ut["personas"][2]["age_group"] = "청년"  # 청년 2명, 중년 없음
        self.assertTrue(any("페르소나 구성" in w for w in self.run_check(rev)[1]))

    def test_bad_age_group_fails(self):
        for bad in ("60~70대", "노인", "청소년"):
            rev = self.review_with_ut()
            rev["ut"]["personas"][0]["age_group"] = bad
            self.assertHasError(self.run_check(rev)[0], "age_group은 청년|중년|노년")

    def test_bad_level_values_fail(self):
        for key in ("device_level", "ux_level"):
            for bad in ("최하", "높음", "1"):
                rev = self.review_with_ut()
                rev["ut"]["personas"][0][key] = bad
                self.assertHasError(self.run_check(rev)[0], f"{key}는 상|중|하")

    def test_missing_persona_attributes_fail(self):
        for key in ("age_group", "device_level", "ux_level"):
            rev = self.review_with_ut()
            del rev["ut"]["personas"][0][key]
            self.assertHasError(self.run_check(rev)[0], f"{key} 비어 있음")

    def test_old_persona_fields_are_rejected(self):
        for key, val in (("age_band", "60~70대"), ("tech", "하")):
            rev = self.review_with_ut()
            rev["ut"]["personas"][0][key] = val
            self.assertHasError(self.run_check(rev)[0], f"옛 필드 {key}")

    def test_bad_axis_value_fails(self):
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["steps"][0]["writing"] = "어려움"
        self.assertHasError(self.run_check(rev)[0], "writing는 쉬움|보통|막힘")

    def test_blocked_step_without_finding_fails(self):
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["steps"][0]["finding_ids"] = []
        self.assertHasError(self.run_check(rev)[0], "막힘 반응은 finding_ids")

    def test_unknown_finding_link_fails(self):
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["steps"][0]["finding_ids"] = ["F99"]
        self.assertHasError(self.run_check(rev)[0], "findings에 없는 finding id")

    def test_abandon_requires_stop_fields(self):
        rev = self.review_with_ut()
        del rev["ut"]["walks"][0]["stop_reason"]
        self.assertHasError(self.run_check(rev)[0], "stop_reason")
        rev = self.review_with_ut()
        del rev["ut"]["walks"][0]["stopped_at"]
        self.assertHasError(self.run_check(rev)[0], "stopped_at")
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["stopped_at"] = "nowhere"
        self.assertHasError(self.run_check(rev)[0], "screens에 없는 화면 id")

    def test_score_fields_and_numbers_are_forbidden(self):
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["satisfaction_score"] = 4
        errors, _ = self.run_check(rev)
        self.assertHasError(errors, "수치 필드")
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["steps"][0]["memo"] = 3
        self.assertHasError(self.run_check(rev)[0], "숫자 값")

    def test_persona_walk_must_be_one_to_one(self):
        rev = self.review_with_ut()
        rev["ut"]["walks"].append(copy.deepcopy(rev["ut"]["walks"][0]))
        self.assertHasError(self.run_check(rev)[0], "둘 이상")
        rev = self.review_with_ut()
        rev["ut"]["walks"] = []
        self.assertHasError(self.run_check(rev)[0], "짝이 되는 walk가 없어요")
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["persona_id"] = "p-ghost"
        self.assertHasError(self.run_check(rev)[0], "persona_id")

    def test_step_screen_and_quote_must_be_valid(self):
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["steps"][0]["screen_id"] = "ghost"
        self.assertHasError(self.run_check(rev)[0], "screens에 없는 screen_id")
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["steps"][0]["quote"] = " "
        self.assertHasError(self.run_check(rev)[0], "quote")

    def test_from_ut_must_name_existing_persona(self):
        rev = self.review_with_ut()
        rev["findings"][0]["from_ut"] = ["p-ghost"]
        self.assertHasError(self.run_check(rev)[0], "from_ut")
        rev = good_review()
        rev["findings"][0]["from_ut"] = ["p-senior-dlo-ulo"]
        self.assertHasError(self.run_check(rev)[0], "from_ut")

    def test_mode_must_be_virtual_and_completed_walk_has_no_stop_fields(self):
        rev = self.review_with_ut()
        rev["ut"]["mode"] = "real"
        self.assertHasError(self.run_check(rev)[0], "ut.mode")
        rev = self.review_with_ut()
        rev["ut"]["walks"][0]["outcome"] = "완주"
        self.assertHasError(self.run_check(rev)[0], "완주인데")


    def with_second_screen(self, rev):
        """capture.json과 review에 '월간' 화면을 더해요(easy_screens 검사용)."""
        write(os.path.join(self.run_dir, "shots", "monthly.png"), PNG)
        write(os.path.join(self.run_dir, "capture.json"), json.dumps({
            "input_type": "image",
            "screens": [{"id": "home", "name": "홈", "shot": "shots/home.png"},
                        {"id": "monthly", "name": "월간", "shot": "shots/monthly.png"}],
            "edges": []}))
        rev["screens"].append({"id": "monthly", "name": "월간", "shot": "shots/monthly.png",
                               "screen_goal": "한 달 흐름을 본다", "verdict": "문제없어요."})
        return rev

    def test_easy_screens_replace_all_easy_steps(self):
        rev = self.with_second_screen(self.review_with_ut())
        w = rev["ut"]["walks"][0]
        w.update({"outcome": "완주", "easy_screens": ["monthly"]})
        del w["stopped_at"], w["stop_reason"]
        errors, _ = self.run_check(rev)
        self.assertEqual(errors, [])

        w["steps"].append({"screen_id": "monthly", "device": "쉬움", "design": "쉬움", "writing": "쉬움",
                           "quote": "괜찮네요", "finding_ids": []})
        self.assertHasError(self.run_check(rev)[0], "steps에도 있어요")
        w["steps"].pop()

        w["easy_screens"] = ["ghost"]
        self.assertHasError(self.run_check(rev)[0], "easy_screens에 screens에 없는 화면 id")

        w["easy_screens"] = "monthly"
        self.assertHasError(self.run_check(rev)[0], "easy_screens는 화면 id 목록")

        w.update({"outcome": "이탈", "stopped_at": "home", "stop_reason": "포기했어요", "easy_screens": ["home"]})
        self.assertHasError(self.run_check(rev)[0], "easy_screens에 올 수 없어요")

        # 모든 화면이 쉬움인 완주 walk만 steps를 비울 수 있어요
        w.update({"outcome": "완주", "steps": [], "easy_screens": ["home", "monthly"]})
        del w["stopped_at"], w["stop_reason"]
        self.assertEqual(self.run_check(rev)[0], [])
        w["easy_screens"] = []
        self.assertHasError(self.run_check(rev)[0], "steps는 비어 있지 않은 목록")
        w.update({"outcome": "이탈", "stopped_at": "home", "stop_reason": "포기했어요", "easy_screens": ["monthly"]})
        self.assertHasError(self.run_check(rev)[0], "steps는 비어 있지 않은 목록")


class ReportTest(RunCase):
    def put_review(self, rev):
        write(os.path.join(self.run_dir, "review.json"), json.dumps(rev, ensure_ascii=False))

    def ut_review(self):
        rev = good_review()
        rev["ut"] = good_ut()
        rev["findings"][0]["from_ut"] = ["p-senior-dlo-ulo"]
        return rev

    def read(self, name):
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as fh:
            return fh.read()

    def test_easy_screens_render_compactly(self):
        rev = self.ut_review()
        write(os.path.join(self.run_dir, "shots", "monthly.png"), PNG)
        rev["screens"].append({"id": "monthly", "name": "월간", "shot": "shots/monthly.png",
                               "screen_goal": "한 달 흐름을 본다", "verdict": "문제없어요."})
        rev["ut"]["walks"][0]["easy_screens"] = ["monthly"]
        self.put_review(rev)
        build_report.build(self.run_dir)
        html = self.read("report.html")
        self.assertIn("세 가지 모두 쉬움", html)
        self.assertNotIn("걷지 않았어요", html)
        self.assertIn("나머지는 세 가지 모두 쉬움: 월간", self.read("report.md"))

    def test_all_easy_walk_renders_without_steps(self):
        rev = self.ut_review()
        w = rev["ut"]["walks"][0]
        w.update({"outcome": "완주", "steps": [], "easy_screens": ["home"]})
        del w["stopped_at"], w["stop_reason"]
        self.put_review(rev)
        build_report.build(self.run_dir)
        html = self.read("report.html")
        self.assertIn("세 가지 모두 쉬움", html)
        self.assertIn("<b>완주</b>", html)
        md = self.read("report.md")
        self.assertNotIn("| 화면 | 디바이스 |", md)
        self.assertIn("나머지는 세 가지 모두 쉬움: 홈", md)

    def test_strings_are_html_escaped(self):
        rev = self.ut_review()
        payload = "<script>alert(1)</script>"
        rev["summary"]["headline"] = '"><img src=x onerror=alert(1)>'
        rev["findings"][0]["title"] = payload
        rev["findings"][0]["why"] = payload
        rev["screens"][0]["name"] = payload
        rev["ut"]["personas"][0]["name"] = payload
        rev["ut"]["walks"][0]["steps"][0]["quote"] = payload
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        self.assertNotIn(payload, doc)
        self.assertNotIn("<img src=x", doc)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", doc)

    def test_shot_path_escape_is_rejected(self):
        write(os.path.join(self.run_dir, "shots", "ok.png"), PNG)
        self.assertIsNotNone(build_report.safe_shot(self.run_dir, "shots/ok.png"))
        secret = b"\x89PNG\r\n\x1a\nSECRET-OUTSIDE"
        write(os.path.join(self.tmp, "secret.png"), secret)
        write(os.path.join(self.run_dir, "root.png"), secret)
        for bad in ("../secret.png", "shots/../../secret.png", os.path.join(self.tmp, "secret.png"),
                    "root.png", "capture.json", "shots", "", None, 3, "shots/\0x.png"):
            self.assertIsNone(build_report.safe_shot(self.run_dir, bad), repr(bad))
        try:
            os.symlink(os.path.join(self.tmp, "secret.png"), os.path.join(self.run_dir, "shots", "link.png"))
        except (OSError, NotImplementedError):
            pass
        else:
            self.assertIsNone(build_report.safe_shot(self.run_dir, "shots/link.png"))
        rev = good_review()
        rev["screens"][0]["shot"] = "../secret.png"
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        import base64
        self.assertNotIn(base64.b64encode(secret).decode(), doc)
        self.assertNotIn("data:image", doc)

    def test_builder_warns_when_a_screen_image_is_missing(self):
        write(os.path.join(self.run_dir, "img", "a.png"), PNG)
        rev = good_review()
        rev["screens"][0]["shot"] = "img/a.png"
        self.put_review(rev)
        doc, n_img, missing = build_report.build_html(build_report.Model(rev, {}), self.run_dir)
        self.assertEqual((n_img, missing), (0, ["홈"]))
        self.assertIn("이미지를 불러오지 못했어요", doc)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            build_report.build(self.run_dir, "html")
        self.assertIn("경고: 이미지를 넣지 못한 화면 1개: 홈", buf.getvalue())
        rev["screens"][0]["shot"] = "shots/home.png"
        self.put_review(rev)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            build_report.build(self.run_dir, "html")
        self.assertNotIn("이미지를 넣지 못한", buf.getvalue())

    def test_html_has_csp_aria_table_roles_and_four_multiple_padding(self):
        self.put_review(self.ut_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        self.assertIn('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                      'img-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">', doc)
        self.assertLess(doc.index("Content-Security-Policy"), doc.index("<style>"))
        table = doc.split('<table class="ut-table')[1].split("</table>")[0]
        for needle in ('role="table"', '<thead role="rowgroup">', '<tbody role="rowgroup">', '<tr role="row">',
                       'role="columnheader"', 'role="rowheader"', '<td role="cell"'):
            self.assertIn(needle, table)
        self.assertIsNone(re.search(r"padding:2px", doc))
        for px in re.findall(r"padding:(\d+)px", doc):
            self.assertEqual(int(px) % 4, 0, px)

    def test_image_is_embedded_with_alt_and_no_external_requests(self):
        write(os.path.join(self.run_dir, "shots", "home.png"), PNG)
        self.put_review(self.ut_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        self.assertIn("data:image/png;base64,", doc)
        self.assertRegex(doc, r'<img src="data:image/png;base64,[A-Za-z0-9+/=]+" alt="홈 화면 시안" id="img-home">')
        # 이미지는 한 번만 들어가고, 지적 카드의 위치 그림은 그 이미지에서 canvas로 그려요
        self.assertEqual(doc.count("data:image/png;base64,"), 1)
        self.assertIsNone(re.search(r'(src|href|action)\s*=\s*"(https?:)?//', doc))
        self.assertNotIn("@import", doc)
        self.assertNotIn("url(http", doc)

    def test_both_formats_and_md_content(self):
        self.put_review(self.ut_review())
        written = build_report.build(self.run_dir)
        self.assertEqual([os.path.basename(p) for p in written], ["report.html", "report.md"])
        md = self.read("report.md")
        self.assertIn("## 총평", md)
        self.assertIn("### [심각] F01 저장 버튼이 가려져요", md)
        self.assertIn("## 가상 UT", md)
        self.assertIn("| 홈 (`home`) | 막힘 | 보통 | 쉬움 |", md)
        self.assertIn("### 반응에서 나온 지적", md)
        self.assertIn("박순자", md)

    def test_md_neutralizes_tags_and_table_pipes(self):
        rev = self.ut_review()
        rev["findings"][0]["observation"] = "<b>굵게</b> 보여요"
        rev["ut"]["walks"][0]["steps"][0]["quote"] = "가|나 <i>말</i>"
        self.put_review(rev)
        build_report.build(self.run_dir, "md")
        md = self.read("report.md")
        self.assertNotIn("<b>", md)
        self.assertNotIn("<i>", md)
        self.assertIn("가\\|나", md)

    def test_md_neutralizes_markdown_images_links_and_autolinks(self):
        rev = self.ut_review()
        rev["findings"][0]["observation"] = "![x](https://evil.example/p.png) [링크](http://evil.example) *굵게* _기울임_ `코드`"
        rev["findings"][0]["title"] = "자동 링크 https://evil.example/a 와 HTTP://EVIL.example"
        rev["ut"]["walks"][0]["steps"][0]["quote"] = "![y](https://evil.example/q.png)"
        self.put_review(rev)
        build_report.build(self.run_dir, "md")
        md = self.read("report.md")
        self.assertNotIn("![", md)
        self.assertNotIn("](", md)
        self.assertNotRegex(md, r"(?i)https?://")
        self.assertIn("\\!\\[x\\]\\(https:​//evil.example/p.png\\)", md)
        self.assertIn("\\[링크\\]\\(http:​//evil.example\\)", md)
        self.assertIn("\\*굵게\\* \\_기울임\\_ \\`코드\\`", md)
        self.assertIn("\\!\\[y\\]", md)
        # 글은 그대로 읽혀요: 이스케이프를 걷어 내면 원문이 남아요
        plain = re.sub(r"\\([\\\[\]()!*_`])", r"\1", md.replace("​", ""))
        self.assertIn("https://evil.example/a", plain)

    def test_md_top_matches_html_top_rule(self):
        rev = good_review()
        base = rev["findings"][0]
        rev["findings"] = []
        for i, sev in enumerate(("낮음", "중간", "낮음", "심각", "중간"), 1):
            f = copy.deepcopy(base)
            f.update({"id": f"F0{i}", "severity": sev, "title": f"지적 {i}"})
            rev["findings"].append(f)
        rev["summary"]["top"] = ["F01", "F02", "F03", "F04", "F05"]
        self.put_review(rev)
        build_report.build(self.run_dir, "md")
        line = [x for x in self.read("report.md").splitlines() if x.startswith("먼저 고칠 것:")][0]
        self.assertEqual(line, "먼저 고칠 것: F04 지적 4, F02 지적 2, F05 지적 5")
        m = build_report.Model(rev, {})
        self.assertEqual([f["id"] for f in build_report.top_findings(m)], ["F04", "F02", "F05"])

    def test_format_option_writes_only_requested_file(self):
        self.put_review(good_review())
        build_report.build(self.run_dir, "md")
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "report.md")))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "report.html")))

    def test_ut_sections_are_omitted_without_ut(self):
        self.put_review(good_review())
        build_report.build(self.run_dir)
        doc, md = self.read("report.html"), self.read("report.md")
        for needle in ('id="ut"', "가상 사용자 반응", "실제 조사 아님", "ut-table"):
            if needle == "ut-table":
                needle = '<table class="ut-table'
            self.assertNotIn(needle, doc)
        self.assertNotIn("가상 UT", md)

    def test_ut_sections_show_virtual_label_axes_and_links(self):
        self.put_review(self.ut_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        self.assertIn('id="ut"', doc)
        self.assertIn("가상 사용자 반응 · 실제 조사 아님", doc)
        self.assertIn("박순자", doc)
        self.assertIn('<table class="ut-table', doc)
        for word in ("디바이스", "시안", "라이팅", "막힘", "보통", "쉬움"):
            self.assertIn(word, doc)
        self.assertIn('href="#f-F01"', doc)
        self.assertIn('id="f-F01"', doc)
        self.assertIn('id="ut-p-p-senior-dlo-ulo"', doc)

    def test_classify_buttons_are_per_finding_and_native(self):
        self.put_review(good_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        card = doc.split('id="f-F01"')[1].split("</article>")[0]
        for label in ("고쳤어요", "문제 아님", "되돌리기"):
            self.assertRegex(card, r'<button type="button"[^>]*data-act="[a-z]+"[^>]*>' + label + "</button>")
        self.assertNotIn("data-chip", doc)
        self.assertNotIn("문제를 해결했어요", doc)
        self.assertIn('id="n-resolve"', doc)
        self.assertIn('class="progress"', doc)
        self.assertIn("localStorage", doc)
        self.assertIn("prefers-reduced-motion", doc)

    def test_pin_crop_quote_dedupe_and_collapsed_premise(self):
        rev = self.ut_review()
        rev["checks_needed"] = [{"what": "정책", "how": "문서를 봐요"}]
        rev["findings"][0]["pin"] = {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}
        f2 = copy.deepcopy(rev["findings"][0])
        f2.update({"id": "F02", "severity": "중간", "title": "버튼 이름이 모호해요", "pin": {"x": 0.5, "y": 0.5},
                   "from_ut": []})
        rev["findings"].append(f2)
        rev["ut"]["walks"][0]["steps"][0]["finding_ids"] = ["F01", "F02"]
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        c1 = doc.split('id="f-F01"')[1].split("</article>")[0]
        c2 = doc.split('id="f-F02"')[1].split("</article>")[0]
        # 위치 그림: 상자는 data-w/h, 점은 번호 핀. 둘 다 canvas로 그려요
        self.assertIn('class="crop" data-img="img-home" data-x="0.1000" data-y="0.8000" data-w="0.8000" data-h="0.1000"', c1)
        self.assertIn("<canvas", c1)
        # 썸네일 핀 번호와 카드 번호가 같고, pin 있는 지적만 이어서 센다
        self.assertIn('<span class="num" aria-hidden="true">1</span>', c1)
        self.assertIn('<span class="num" aria-hidden="true">2</span>', c2)
        self.assertEqual(doc.count('class="pin" aria-hidden="true" style='), 2)
        self.assertIn('data-x="0.5000" data-y="0.5000"', c2)
        self.assertNotIn("data-w", c2)
        self.assertIn('class="pin"', c2)
        # 같은 한마디는 첫 번째로 이어진 지적(F01)에만, F02에는 이름만
        self.assertIn("저장은 어디서 하는 거예요?", c1)
        self.assertNotIn("저장은 어디서 하는 거예요?", c2)
        self.assertIn("여기서도 막힌 사람", c2)
        self.assertEqual(doc.count("저장은 어디서 하는 거예요?"), 2)   # F01 카드 + 가상 UT 표
        # 원칙 칩 옆 검토 질문, 같은 원칙끼리 연결
        self.assertIn("완료에 필요한 행동이 한눈에 보이는가?", c1)
        self.assertIn('같은 원칙에 걸린 지적: <a href="#f-F02">F02</a>', c1)
        # 검토 전제는 접혀 있고, 입력·판정 방식은 맨 아래 한 줄
        self.assertIn('<details class="meta-wrap"><summary>검토 전제 보기</summary>', doc)
        self.assertLess(doc.index('class="foot-meta"'), doc.index("<script>"))
        self.assertNotIn("<dt>입력 방식</dt>", doc)
        self.assertNotIn("<dt>검토 목표</dt>", doc)   # 브리프 목표가 있으면 run.goal 줄은 빼요
        self.assertIn("답해 주시면 더 정확해져요", doc)
        self.assertNotIn("<h5>근거</h5>", doc)

    def test_missing_review_json_is_a_clean_error(self):
        with self.assertRaises(ValueError):
            build_report.build(self.run_dir)

    def test_malformed_values_do_not_crash(self):
        rev = self.ut_review()
        rev["findings"][0]["pin"] = {"x": "a", "y": True}
        rev["findings"][0]["from_ut"] = "p-senior-dlo-ulo"
        rev["summary"]["top"] = 5
        rev["run"]["exclusions"] = "x"
        rev["ut"]["walks"][0]["steps"][0]["finding_ids"] = 7
        self.put_review(rev)
        build_report.build(self.run_dir)

    def test_checklist_markdown_skips_cleared_screens(self):
        rev = self.ut_review()
        rev["findings"][0]["done_when"] = "키보드가 올라와도 '저장하기'가 보여요."
        rev["findings"].append({
            "id": "F02", "screen_id": None, "severity": "중간", "lens": "흐름",
            "title": "수정하는 길이 없어요", "observation": "목록에 단서가 없어요.", "why": "잘못 적어도 못 고쳐요.",
            "principle": None, "fix": "수정 화면을 추가해요.",
            "evidence": {"shot": "shots/home.png", "where": "목록", "type": "shot"}})
        m = build_report.Model(rev, {})
        items = build_report.checklist_items(m)
        self.assertEqual([it["fid"] for it in items], ["F01", "F02"])
        md = build_report.render_checklist(items)
        self.assertIn("## 남은 지적 2개", md)
        self.assertIn("- [ ] [심각] F01 저장 버튼이 가려져요 (홈)", md)
        self.assertIn("  - 확인 기준: 키보드가 올라와도 '저장하기'가 보여요.", md)
        self.assertIn("- [ ] [중간] F02 수정하는 길이 없어요 (여러 화면에 걸친 흐름)", md)
        cleared = build_report.render_checklist(items, skip_fids={"F01"})
        self.assertNotIn("F01", cleared)
        self.assertIn("F02", cleared)
        self.assertEqual(build_report.render_checklist(items, skip_fids={"F01"}).count("- [ ]"), 1)
        self.put_review(rev)
        build_report.build(self.run_dir, "md")
        report = self.read("report.md")
        self.assertIn("- 고쳤는지 확인하는 기준: 키보드가 올라와도", report)
        self.assertIn("- [ ] [심각] F01", report)

    def test_checklist_text_is_neutralized_and_embedded_safely(self):
        rev = self.ut_review()
        rev["findings"][0]["title"] = "<b>굵게</b></script><script>alert(1)</script>"
        self.put_review(rev)
        build_report.build(self.run_dir, "both")
        doc, md = self.read("report.html"), self.read("report.md")
        self.assertIn('id="cl-data"', doc)
        self.assertNotIn("</script><script>alert(1)", doc)
        self.assertNotIn("<b>굵게</b>", md)
        data = re.search(r'<script type="application/json" id="cl-data">(.*?)</script>', doc, re.S).group(1)
        items = json.loads(data)
        self.assertEqual(items[0]["fid"], "F01")
        self.assertEqual(items[0]["sid"], "home")
        self.assertRegex(doc, r'<button type="button"[^>]*data-copy="checklist"[^>]*>남은 지적을 체크리스트로 복사</button>')
        self.assertIn('id="cl-fallback"', doc)

    def test_copy_button_next_to_tobe_is_native_and_named(self):
        self.put_review(good_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        self.assertRegex(doc, r'<p id="tobe-F01">키보드 위에')
        self.assertRegex(doc, r'<button type="button" class="btn small" data-copy="tobe-F01" aria-label="F01 수정 후 문구 복사">복사</button>')
        self.assertIn("navigator.clipboard", doc)
        self.assertIn("selectNodeContents", doc)

    def test_first_screen_shows_headline_then_top_three_severe_first(self):
        rev = good_review()
        base = rev["findings"][0]
        rev["findings"] = []
        for i, sev in enumerate(("낮음", "중간", "낮음", "심각"), 1):
            f = copy.deepcopy(base)
            f.update({"id": f"F0{i}", "severity": sev, "title": f"지적 {i}"})
            rev["findings"].append(f)
        rev["summary"]["top"] = ["F01", "F02", "F03", "F04"]
        m = build_report.Model(rev, {})
        self.assertEqual([f["id"] for f in build_report.top_findings(m)], ["F04", "F02", "F01"])
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        head = doc.split('class="top-fix"')[1].split("</section>")[0]
        self.assertEqual(head.count("<li>"), 3)
        self.assertLess(head.index('href="#f-F04"'), head.index('href="#f-F02"'))
        self.assertNotIn('href="#f-F03"', head)
        self.assertLess(doc.index("<h1>"), doc.index('class="top-fix"'))
        self.assertLess(doc.index('class="top-fix"'), doc.index('class="stats"'))

    def test_card_order_and_done_when(self):
        rev = good_review()
        rev["findings"][0]["done_when"] = "키보드가 올라와도 '저장하기'가 보여요."
        rev["findings"][0]["case"] = "C177"
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        card = doc.split('id="f-F01"')[1]
        order = [card.index(x) for x in ('class="crop"', "무엇이 문제인가", "사용자에게 생기는 일", "Clear Action",
                                         "이렇게 고쳐요", "고쳤는지 확인하는 기준", 'class="card-actions"')]
        self.assertEqual(order, sorted(order))
        self.assertIn("화면 위치", card)
        self.assertIn('href="https://toss.im/simplicity/sessions/when-ux-ignores-blind-users"', card)
        self.assertIn("사례 C177", card)
        rev["findings"][0].pop("case")
        del rev["findings"][0]["done_when"]
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        self.assertNotIn("사례 C", doc)
        self.assertNotIn("고쳤는지 확인하는 기준", doc)

    def test_case_index_reads_title_and_url(self):
        idx = build_report.load_case_index()
        title, url = idx["C177"]
        self.assertIn("'선택' 버튼", title)
        self.assertTrue(url.startswith("https://"))
        self.assertEqual(build_report.load_case_index(os.path.join(self.tmp, "none.md")), {})

    def test_avatars_are_inline_distinct_and_self_contained(self):
        icons = {a: build_report.avatar(a) for a in ("청년", "중년", "노년")}
        self.assertEqual(len(set(icons.values())), 3)
        for age, svg in icons.items():
            self.assertTrue(svg.startswith("<svg "))
            self.assertIn('width="36" height="36" viewBox="0 0 36 36"', svg)
            self.assertIn(f"<title>{age} 사용자</title>", svg)
            self.assertIn(f'aria-label="{age} 사용자"', svg)
            for banned in ("href", "xlink", "<image", "<use", "url(", "http", "data:", "@import", "<script", "<style"):
                self.assertNotIn(banned, svg)
            self.assertEqual(svg.count("<svg"), svg.count("</svg>"))
        self.assertIn("<circle", icons["노년"])
        self.assertIn("hair-white", icons["노년"])
        self.assertNotIn("hair-white", icons["청년"])
        self.assertIn("<rect", icons["중년"][icons["중년"].index("</title>"):])
        self.assertIn('aria-label="사용자"', build_report.avatar("모름"))
        # 단독일 때만 title과 label, 글이 옆에 있으면 aria-hidden
        alone, beside = build_report.avatar("청년"), build_report.avatar("청년", True)
        self.assertIn("<title>", alone)
        self.assertNotIn("aria-hidden", alone)
        for gone in ("<title>", "aria-label", 'role="img"'):
            self.assertNotIn(gone, beside)
        self.assertIn('aria-hidden="true"', beside)

    def test_avatar_markup_has_no_emoji_or_off_palette_color(self):
        doc = ""
        self.put_review(self.ut_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        for svg in re.findall(r"<svg .*?</svg>", doc, re.S):
            self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3,8}|rgb|fill=|stroke=", svg), svg[:80])
            self.assertTrue(all(ord(ch) < 0x2E80 or 0xAC00 <= ord(ch) <= 0xD7A3 for ch in svg))

    def test_persona_icons_in_cards_table_and_bubbles_with_virtual_label(self):
        self.put_review(self.ut_review())
        build_report.build(self.run_dir, "html")
        doc = self.read("report.html")
        # 글이 옆에 있는 아이콘은 스크린리더에서 숨겨 같은 말이 두 번 읽히지 않게 한다
        hidden = 'class="avatar" width="36" height="36" viewBox="0 0 36 36" aria-hidden="true" focusable="false">'
        persona = doc.split('id="ut-p-p-senior-dlo-ulo"')[1].split("</li>")[0]
        self.assertIn(hidden, persona)
        self.assertNotIn("aria-label", persona.split("<h3>")[0])
        table = doc.split('<table class="ut-table')[1].split("</table>")[0]
        self.assertIn(hidden, table)
        self.assertNotIn("노년 사용자", table)
        self.assertIn("노년 · 디바이스 하 · UX 이해도 하", table)
        card = doc.split('id="f-F01"')[1].split("</article>")[0]
        self.assertIn('class="bubble"', card)
        self.assertIn(hidden, card)
        self.assertNotIn("노년 사용자", card)
        self.assertIn("박순자", card)
        self.assertIn("노년 · 디바이스 하 · UX 이해도 하", card)
        self.assertIn("저장은 어디서 하는 거예요?", card)
        self.assertIn("가상 사용자 반응 · 실제 조사 아님", card)
        self.assertIn('href="#ut-p-p-senior-dlo-ulo"', card)

    def test_card_has_no_reactions_without_linked_personas(self):
        rev = self.ut_review()
        rev["findings"][0].pop("from_ut")
        rev["ut"]["walks"][0]["steps"][0]["finding_ids"] = []
        rev["ut"]["walks"][0]["steps"][0]["device"] = "쉬움"
        self.put_review(rev)
        build_report.build(self.run_dir, "html")
        card = self.read("report.html").split('id="f-F01"')[1].split("</article>")[0]
        self.assertNotIn('class="bubble"', card)
        self.assertNotIn("실제 조사 아님", card)

    def test_sample_run_validates_and_builds(self):
        src = os.path.join(SKILL, "examples", "sample-run")
        dst = os.path.join(self.tmp, "sample")
        shutil.copytree(src, dst)
        with open(os.path.join(dst, "review.json"), encoding="utf-8") as fh:
            rev = json.load(fh)
        with open(os.path.join(dst, "capture.json"), encoding="utf-8") as fh:
            cap = json.load(fh)
        errors, _warns = validate.check(rev, cap, dst, self.principles, self.cases)
        self.assertEqual(errors, [])
        build_report.build(dst)
        with open(os.path.join(dst, "report.html"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("data:image/svg+xml;base64,", doc)
        self.assertIn("빠진 흐름·분기", doc)
        self.assertIn("실제 조사 아님", doc)

    def test_sample_run_matches_example_doc_and_walk_is_consistent(self):
        ex = os.path.join(SKILL, "examples")
        with open(os.path.join(ex, "sample-run", "review.json"), encoding="utf-8") as fh:
            rev = json.load(fh)
        with open(os.path.join(ex, "ut-example.md"), encoding="utf-8") as fh:
            doc = fh.read()
        for f in rev["findings"]:
            if f["id"] == "F03":
                self.assertIn(f"F03 {f['title']}", doc)
        walk = [w for w in rev["ut"]["walks"] if w["persona_id"] == "p-mid-dlo-umid"][0]
        self.assertEqual(walk["outcome"], "완주")
        last = walk["steps"][-1]
        self.assertNotIn("못 누르겠어요", last["quote"])
        self.assertNotIn("못 누르겠어요", doc)
        self.assertNotIn("막힘", [last["device"], last["design"], last["writing"]])

    def test_contract_levels_match_validator(self):
        with open(os.path.join(SKILL, "references", "output-contract.md"), encoding="utf-8") as fh:
            contract = fh.read()
        # 검증기에서 경고인 ut 규칙은 계약에 "(경고)"로 적혀 있어요
        self.assertIn("보통 반응도 이어요(경고)", contract)
        self.assertIn("`stopped_at` 화면이에요(경고)", contract)
        self.assertIn("페르소나 `id`가 비었거나 겹침", contract)
        self.assertIn("`RUN/shots/`", contract)
        self.assertIn("심각을 앞으로 올려 최대 3개", contract)
        self.assertIn("연령대가 겹침", contract)
        self.assertIn("화면을 훑은 흔적", contract)
        rev = good_review()
        rev["ut"] = good_ut()
        rev["findings"][0]["from_ut"] = ["p-senior-dlo-ulo"]
        dup = copy.deepcopy(rev["ut"]["personas"][0])
        rev["ut"]["personas"].append(dup)
        self.assertHasError(self.run_check(rev)[0], "persona id 중복")


class ImageRerunTest(RunCase):
    def test_rerun_removes_stale_shots(self):
        write(os.path.join(self.tmp, "in1", "a.png"), PNG)
        write(os.path.join(self.tmp, "in1", "b.png"), PNG)
        out = os.path.join(self.tmp, "out")
        image_capture.capture(os.path.join(self.tmp, "in1"), out)
        write(os.path.join(self.tmp, "in2", "c.png"), PNG)
        write(os.path.join(out, "shots", "notes.txt"), "keep")
        image_capture.capture(os.path.join(self.tmp, "in2"), out)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "shots"))), ["c.png", "notes.txt"])


class FigmaKeyTest(unittest.TestCase):
    def test_file_key_is_url_quoted(self):
        import figma_capture
        seen = []

        def fake_req(path, tries=3):
            seen.append(path)
            return {"nodes": {}, "document": {"children": []}}

        class A:
            file_key = "AB/../x?y"
            node_id = "1:2"
            section_name = None
        with mock.patch.object(figma_capture, "req", fake_req):
            try:
                figma_capture.find_target(A)
            except SystemExit:
                pass
        self.assertTrue(seen)
        for p in seen:
            self.assertNotIn("AB/../x", p)
            self.assertIn("AB%2F..%2Fx%3Fy", p)


class BriefTest(RunCase):
    def test_missing_brief_warns_and_malformed_brief_fails(self):
        rev = good_review()
        del rev["run"]["brief"]
        errors, warns = self.run_check(rev)
        self.assertEqual(errors, [])
        self.assertTrue(any("run.brief가 없어요" in w for w in warns), warns)
        for bad, needle in (({"product": "앱"}, "source"), ({"source": "user"}, "채운 항목"),
                            ({"product": 3, "source": "user"}, "문자열"), ({"wish": "x", "source": "user"}, "모르는 키"),
                            ("앱", "객체")):
            rev["run"]["brief"] = bad
            self.assertHasError(self.run_check(rev)[0], needle)

    def test_brief_order_matches_skill_questions(self):
        keys = [k for k, _ in validate.BRIEF_FIELDS]
        self.assertEqual(keys, ["product", "objective", "problem", "cause", "solution", "user_value", "business_value"])
        skill = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
        qs = ["## 어떤 제품인가요?", "## 달성하고자 하는 목표가 무엇인가요?", "## 해결하고자 하는 문제는 무엇인가요?",
              "## 왜 이 문제를 겪고 있을까요?", "## 어떻게 해결하고자 하나요?",
              "## 이 개선을 통해서 유저가 얻는 기대효과는 무엇인가요?",
              "## 이 개선을 통해서 회사가 얻는 기대효과는 무엇인가요?", "## 디자인 결과물 링크나 이미지"]
        pos = [skill.index(q) for q in qs]
        self.assertEqual(pos, sorted(pos))
        line = "안 써도 리뷰할 수 있지만, 자세히 쓸수록 더 정확한 피드백이 나와요."
        self.assertLess(skill.index(line), pos[0])  # 안내 한 줄은 양식 바로 위에 그대로 나와요

    def test_report_shows_brief_as_premise(self):
        rev = good_review()
        rev["run"]["brief"] = {"product": "<b>가계부</b> 앱", "problem": "기록을 안 해요", "source": "mixed"}
        write(os.path.join(self.run_dir, "review.json"), json.dumps(rev, ensure_ascii=False))
        with contextlib.redirect_stdout(io.StringIO()):
            build_report.build(self.run_dir)
        with open(os.path.join(self.run_dir, "report.html"), encoding="utf-8") as fh:
            doc = fh.read()
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("해결하려는 문제", doc)
        self.assertIn("&lt;b&gt;가계부&lt;/b&gt;", doc)
        self.assertIn("화면에서 추론했어요", doc)
        self.assertIn("해결하려는 문제: 기록을 안 해요", md)


class CompareTest(unittest.TestCase):
    SAMPLE = os.path.join(SKILL, "examples", "sample-compare")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = os.path.join(self._tmp.name, "run")
        shutil.copytree(self.SAMPLE, self.run_dir)
        with open(os.path.join(self.run_dir, "compare.json"), encoding="utf-8") as fh:
            self.cmp = json.load(fh)
        with open(os.path.join(self.run_dir, "capture.json"), encoding="utf-8") as fh:
            self.cap = json.load(fh)
        self.principles = validate.load_principles(GUIDELINE)
        self.cases = validate.load_cases(CASES)

    def result(self, cmp=None, cap="auto"):
        return build_compare.check(self.cmp if cmp is None else cmp, self.run_dir,
                                   self.cap if cap == "auto" else cap, self.principles, self.cases)

    def errors(self, cmp=None, cap="auto"):
        return self.result(cmp, cap)[0]

    def warns(self, cmp=None, cap="auto"):
        return self.result(cmp, cap)[1]

    def assertHas(self, items, needle):
        self.assertTrue(any(needle in e for e in items), f"{needle!r} not in {items}")

    def write_cmp(self, cmp):
        with open(os.path.join(self.run_dir, "compare.json"), "w", encoding="utf-8") as fh:
            json.dump(cmp, fh, ensure_ascii=False)

    def test_sample_passes_strict_and_builds_self_contained_html(self):
        self.assertEqual(self.result(), ([], []))
        with contextlib.redirect_stdout(io.StringIO()):
            out = build_compare.build(self.run_dir, strict=True)
        with open(out, encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("Content-Security-Policy", doc)
        self.assertNotRegex(doc, r'(src|href)="https?:')
        self.assertEqual(doc.count("data:image/svg+xml;base64,"), 4)  # 썸네일과 상세에 시안마다 두 번
        self.assertLess(doc.index("B안 지난달 기준 추천"), doc.index("A안 항목별 입력"))  # 순위 순서
        for heading in ("한눈에 보기", "기준별로 비교하면", "어느 시안을 고르든 고쳐야 할 것",
                        "시안별로 아쉬운 점", "가상 사용자 반응", "추천 조합", "화면만으로는 알 수 없는 것"):
            self.assertIn(heading, doc)
        self.assertIn("가상 반응", doc)
        self.assertNotIn("가상 사용자 반응을 돌리지 않았어요", doc)

    def test_check_only_writes_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(build_compare.build(self.run_dir, check_only=True))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "compare.html")))

    def test_text_is_escaped_and_only_bold_and_placeholders_render(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["lead"] = "<script>alert(1)</script> **굵게** {자리_표시} **a {b** c}"
        doc = build_compare.build_html(cmp, self.run_dir)
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)
        self.assertIn("<strong>굵게</strong>", doc)
        self.assertIn("<code>{자리_표시}</code>", doc)
        self.assertNotIn("<code>{b</strong>", doc)  # 태그가 엇갈려 중첩되지 않아요

    def test_rank_must_be_unique_and_complete(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"][1]["rank"] = 1
        self.assertHas(self.errors(cmp), "rank는 1부터")

    def test_every_variant_needs_a_cell_per_criterion(self):
        cmp = copy.deepcopy(self.cmp)
        del cmp["criteria"][0]["cells"]["plan-a"]
        self.assertHas(self.errors(cmp), "시안 'plan-a'가 없어요")
        cmp = copy.deepcopy(self.cmp)
        cmp["criteria"][0]["cells"]["plan-a"]["level"] = "great"
        self.assertHas(self.errors(cmp), "level은 good, mid, bad")

    def test_issues_need_severity_fix_and_where(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"][0]["cons"][0]["fix"] = ""
        cmp["variants"][0]["cons"][0]["where"] = ""
        cmp["common"][0]["severity"] = "P1"
        errs = self.errors(cmp)
        self.assertHas(errs, "cons[0].fix가 비었어요")
        self.assertHas(errs, "cons[0].where가 비었어요")
        self.assertHas(errs, "common[0].severity")

    def test_severe_issue_follows_single_mode_discipline(self):
        cmp = copy.deepcopy(self.cmp)
        con = cmp["variants"][1]["cons"][0]
        con.update({"severity": "심각", "text": "저장 버튼이 없어요", "fix": "명확히 보여주세요"})
        con.pop("tobe", None)
        con.pop("done_when", None)
        errs, warns = self.result(cmp)
        self.assertHas(errs, "tobe(수정 후 모습)")
        self.assertHas(warns, "done_when")
        self.assertHas(warns, "훑은 흔적")
        self.assertHas(warns, "fix가 추상적")

    def test_principle_and_case_are_checked_against_references(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"][0]["cons"][0]["principle"] = "Make It Pop"
        self.assertHas(self.errors(cmp), "없는 원칙 이름")
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"][0]["cons"][0]["case"] = "C999"
        self.assertHas(self.errors(cmp), "없는 사례 번호")
        cmp = copy.deepcopy(self.cmp)
        cmp["common"][0]["case"] = "C127"
        self.assertHas(self.errors(cmp), "principle이 비었는데 case")

    def test_exclusion_rules_warn(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["exclusions"] = ["dummy-amount-mismatch"]
        cmp["variants"][1]["cons"][1]["text"] = "두 화면의 금액이 서로 달라요"
        self.assertHas(self.warns(cmp), "dummy-amount-mismatch")

    def test_ut_structure_and_links(self):
        cmp = copy.deepcopy(self.cmp)
        p = cmp["ut"]["personas"][0]
        p.update({"writing": "막힘", "issue_ids": []})
        p.pop("cause", None)
        errs = self.errors(cmp)
        self.assertHas(errs, "cause가 필요해요")
        self.assertHas(errs, "issue_ids로 지적에 이어요")
        cmp = copy.deepcopy(self.cmp)
        cmp["ut"]["personas"][1]["issue_ids"] = ["NOPE"]
        cmp["ut"]["personas"][2]["score"] = 3
        errs = self.errors(cmp)
        self.assertHas(errs, "'NOPE'")
        self.assertHas(errs, "수치 필드")

    def test_ut_must_walk_first_variant_and_link_its_own_issues(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["ut"]["variant"] = "plan-a"
        for p in cmp["ut"]["personas"]:
            p["issue_ids"] = ["C1"] if p["issue_ids"] else []
        self.assertHas(self.warns(cmp), "1위 시안이 아니에요")
        cmp = copy.deepcopy(self.cmp)
        cmp["ut"]["personas"][2]["issue_ids"] = ["A1"]  # 2위 시안의 지적
        self.assertHas(self.errors(cmp), "ut.variant 시안의 cons나 common")

    def test_brief_renders_folded_premise_and_is_checked(self):
        doc = build_compare.build_html(self.cmp, self.run_dir)
        self.assertIn("검토 전제 보기", doc)
        self.assertIn("작성자가 준 맥락이에요", doc)
        cmp = copy.deepcopy(self.cmp)
        del cmp["brief"]
        self.assertHas(self.warns(cmp), "brief가 없어요")
        cmp["brief"] = {"source": "user"}
        self.assertHas(self.errors(cmp), "채운 항목")

    def test_bold_can_wrap_placeholder(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["lead"] = "**{선택_금액}으로 정하기**"
        doc = build_compare.build_html(cmp, self.run_dir)
        self.assertIn("<strong><code>{선택_금액}</code>으로 정하기</strong>", doc)

    def test_missing_ut_warns_and_footer_discloses_it(self):
        cmp = copy.deepcopy(self.cmp)
        del cmp["ut"]
        self.assertHas(self.warns(cmp), "ut가 없어요")
        doc = build_compare.build_html(cmp, self.run_dir)
        self.assertIn("가상 사용자 반응을 돌리지 않았어요", doc)

    def test_strict_fails_on_warnings(self):
        cmp = copy.deepcopy(self.cmp)
        del cmp["ut"]
        self.write_cmp(cmp)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            build_compare.build(self.run_dir, strict=True)

    def test_capture_coverage_both_ways(self):
        cap = copy.deepcopy(self.cap)
        cap["screens"].append({"id": "plan-c", "name": "C안", "shot": "shots/plan-a.svg"})
        self.assertHas(self.errors(cap=cap), "비교에서 빠졌어요")
        cap = copy.deepcopy(self.cap)
        cap["screens"] = cap["screens"][:1]
        self.assertHas(self.errors(cap=cap), "capture.json에 없는 시안 id")
        self.assertHas(self.warns(cap=[]), "전수 커버리지를 검사하지 못했어요")

    def test_korean_ids_get_unique_anchors(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"][0]["id"], cmp["variants"][1]["id"] = "개선안", "기존안"
        for cr in cmp["criteria"]:
            cr["cells"] = {"개선안": cr["cells"]["plan-b"], "기존안": cr["cells"]["plan-a"]}
        cmp["ut"]["variant"] = "개선안"
        doc = build_compare.build_html(cmp, self.run_dir)
        ids = re.findall(r'id="(v-[^"]+)"', doc)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 2)

    def test_malformed_optional_parts_are_errors_not_crashes(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["recipe"]["steps"] = "단계"
        cmp["recipe"]["spec"] = 5
        cmp["variants"][0]["alt"] = ["x"]
        errs = self.errors(cmp)
        self.assertHas(errs, "steps는 목록")
        self.assertHas(errs, "spec는 목록")
        self.assertHas(errs, "variants[0].alt는 문자열")

    def test_shot_outside_shots_dir_fails(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"][0]["shot"] = "capture.json"
        self.assertHas(self.errors(cmp), "shot이 RUN/shots/ 아래")

    def test_needs_two_variants_and_build_refuses_invalid(self):
        cmp = copy.deepcopy(self.cmp)
        cmp["variants"] = cmp["variants"][:1]
        self.assertHas(self.errors(cmp), "2개 이상")
        self.write_cmp(cmp)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            build_compare.build(self.run_dir)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "compare.html")))


class HygieneTest(unittest.TestCase):
    def test_scripts_and_docs_have_no_personal_traces(self):
        banned = ("/Users/", "resolve_token", ".claude.json", "자비스", "bridge", "P0", "—")
        for base, _dirs, files in os.walk(SKILL):
            for n in files:
                if not n.endswith((".py", ".md")) or n in ("guideline.md", "appendix.md", "cases.md"):
                    continue
                text = open(os.path.join(base, n), encoding="utf-8").read()
                for b in banned:
                    self.assertNotIn(b, text, f"{n} contains {b!r}")


class GuidelinePrincipleParseTest(unittest.TestCase):
    def test_bold_reading_guide_items_are_not_principles(self):
        import validate
        names = validate.load_principles(os.path.join(SKILL, "references", "guideline.md"))
        self.assertNotIn("qa 리뷰할 때", names)
        self.assertIn("one thing", names)


if __name__ == "__main__":
    unittest.main()
