# 변경 기록

## 0.2.0

같은 품질을 더 빨리 내도록 진행 순서를 바꿨어요. 단일·흐름 모드의 판정 기준과 읽는 파일은 그대로이고, 새 비교 모드도 같은 지적 규율과 검사 규칙을 받아요.

- 0단계 맥락 받기: 판정 전에 브리프(제품, 목표, 문제, 원인, 해결 방법, 유저·회사 기대효과)를 한 번만 물어요. 이미 답한 항목은 묻지 않고, 건너뛰면 추론해 진행해요. 결과에는 `run.brief`(비교 모드 `brief`)로 남고 리포트에 검토 전제로 보여요. 판정에 쓰는 법은 `procedure.md` 1-1이에요. 이제 `run.brief`가 없으면 검증기가 경고하므로, 0.1.0 형식의 `review.json`은 `--strict`에서 실패해요.
- 0단계 범위 확인: Figma 노드를 받으면 부모와 형제 화면을 먼저 한 번에 조회하고 모드를 정해요. 자동으로 넓히는 범위는 같은 목적의 시안까지만이에요(`SKILL.md`, `input.md`).
- 비교 모드: `compare.json` 계약(`output-contract.md`), 비교 판정 절차(`procedure.md` 11번), 검사와 리포트를 함께 하는 `build_compare.py`(검사 규칙은 `validate.py`를 재사용해요), 1위 시안 가상 UT, 가상 예시 `examples/sample-compare/`.
- 필수 기준 파일을 모드별로 한 번의 호출에 몰아 읽어요.
- 리포트를 만들었으면 채팅 답은 총평, 먼저 고칠 것, 경로만 짧게 써요.
- 테스트: 비교 모드 검사와 빌드(이스케이프, 외부 요청 없음, 순위, 기준 칸, 전수 커버리지, 심각 tobe, 원칙·사례, 경고 규칙, 가상 UT, 한글 id 앵커).

## 0.1.0

첫 공개 버전이에요.

- 스킬 `ben-ux-feedback`: 화면 이미지, Figma, 라이브 서비스를 디자인 가이드라인으로 검토해서 지적, 근거, 수정안을 돌려줘요.
  - 가이드라인(`guideline.md`), 원칙별 부록(`appendix.md`), 근거 사례 178개(`cases.md`)
  - 판정 절차, 심각·중간·낮음 3단계, 심각 지적은 수정 후 모습과 확인 기준 필수
  - 문구 판정은 ben-ux-writing과 함께 쓰고, 없으면 기본 점검
  - 가상 UT: 청년·중년·노년 가상 사용자 3명의 화면별 반응(디바이스, 시안 이해, 문구 이해)을 지적에 연결
  - 출력 계약 `review.json`과 마크다운 형식, 검증기 `validate.py`
  - 입력 스크립트: 입력 판별, 이미지 캡처, Figma 캡처(`FIGMA_TOKEN` 환경 변수만 읽어요)
  - 리포트: `build_report.py`가 단일 파일 `report.html`(외부 요청 없음)과 `report.md`를 만들어요
  - 예시 run: 가상 가계부 앱 3화면(`examples/sample-run/`)
- 배포: Claude Code용 `.claude/skills/`, Codex용 `.agents/skills/`, 채팅형 LLM용 `chat/`
- 도구: `scripts/build.py`(정본에서 생성물 만들기, `--check`), `scripts/install.py`(기본은 계획만 출력, 백업 후 교체)
- 문서: README, NOTICE, AGENTS, `docs/DESIGN_DECISIONS.md`
- 라이선스: MIT

### 알려진 한계
- 모델이 화면 요소를 놓쳐 "없어요"라고 잘못 지적할 수 있어요. 판정 절차와 검증기 경고로 줄였지만 막지는 못해요. 심각 지적은 사람이 화면에서 확인해요.
