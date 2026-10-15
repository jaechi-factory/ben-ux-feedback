# 변경 기록

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
