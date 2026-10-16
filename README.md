# ben-ux-feedback

화면 이미지를 올리면 디자인 가이드라인 기준으로 시안·UX 피드백을 정리해 주는 오픈소스(MIT) 스킬이에요.

## 무엇을 해 주나

- **시안·UX 피드백**: 이미 만들어진 화면이나 플로우를 가이드라인으로 검토해요. 지적마다 근거와 바로 쓸 수 있는 수정안이 붙고, 심각·중간·낮음 3단계로 나눠요. 심각 지적에는 수정 후 모습과 고쳤는지 확인하는 기준이 꼭 들어가요.
- **가상 UT**: 청년·중년·노년 가상 사용자 3명이 화면을 걸어 보고 막히는 곳을 말해 줘요. 화면을 보고 추론한 가상 반응이고 실제 사용자 조사는 아니에요.
- **리포트**: 결과를 HTML(이미지가 안에 들어간 파일 하나)과 마크다운으로 만들어요. 먼저 고칠 것이 맨 위에 나와요.

Claude Code에서 가장 편하게 쓰고, Codex와 채팅형 LLM(ChatGPT, Gemini 등)에서도 써요.

## 빠른 시작

### Claude Code

1. 저장소를 받아서 그 폴더에서 Claude Code를 열어요.
   ```bash
   git clone https://github.com/jaechi-factory/ben-ux-feedback.git
   cd ben-ux-feedback
   claude
   ```
   이 저장소에는 프로젝트 범위 스킬(`.claude/skills/ben-ux-feedback/`)이 들어 있어서 바로 `/ben-ux-feedback`을 쓸 수 있어요.
2. 다른 프로젝트에서도 쓰고 싶으면 설치해요. 먼저 계획만 보고, 괜찮으면 `--apply`를 붙여요.
   ```bash
   python3 scripts/install.py --target claude
   python3 scripts/install.py --target claude --apply
   ```
   `~/.claude/skills/ben-ux-feedback/`에 복사돼요.
3. 화면을 알려 주고 불러요.
   ```
   /ben-ux-feedback ./screens 폴더의 화면을 검토해 줘. 목표는 가입 전환율이야.
   ```

### Codex

1. 저장소를 받아서 그 폴더에서 Codex를 열어요. 프로젝트 범위 스킬(`.agents/skills/ben-ux-feedback/`)과 `AGENTS.md`가 들어 있어요.
2. 다른 프로젝트에서도 쓰려면 설치해요.
   ```bash
   python3 scripts/install.py --target codex
   python3 scripts/install.py --target codex --apply
   ```
   `~/.agents/skills/ben-ux-feedback/`에 복사돼요. 프로젝트 안에 넣으려면 `--scope project --project <폴더>`를 붙여요.
3. `ben-ux-feedback` 스킬로 화면을 검토해 달라고 요청해요.

### 채팅형 LLM (ChatGPT, Gemini, Claude 웹 등)

1. `chat/00_START_HERE.md`를 열어요.
2. 프로젝트를 만들고 `chat/PROJECT_INSTRUCTIONS.md`를 지침에 붙여 넣어요.
3. `chat/KNOWLEDGE.md`(가능하면 `chat/KNOWLEDGE_APPENDIX.md`도)를 파일로 올리고, 화면 이미지와 함께 `chat/REQUEST_EXAMPLES.md`의 요청 문장을 써요.

채팅형에서는 스크립트를 돌릴 수 없어서 HTML 리포트는 못 만들고 마크다운으로 답해요.

설치 스크립트는 이미 있는 폴더를 덮어쓰지 않아요. 바꾸려면 `--replace-with-backup`을 붙이면 기존 폴더를 `.ben-ux-feedback-backups/`로 옮긴 뒤 교체해요. 홈 폴더나 루트 같은 위험한 경로와 심볼릭 링크는 거절해요.

## 리뷰 전에 받는 맥락

화면만 보면 "잘 만들었나"까지만 알 수 있어요. 무엇을 풀려고 만든 화면인지 알면 "이 화면이 그 문제를 푸나"까지 판정해요. 그래서 요청에 맥락이 없으면 판정 전에 한 번만 "안 써도 리뷰할 수 있지만, 자세히 쓸수록 더 정확한 피드백이 나와요."라는 안내와 함께 아래 양식을 보여 줘요. 이미 답한 항목은 묻지 않고, "그냥 해줘"라고 하면 화면에서 추론해 바로 진행해요.

```markdown
## 어떤 제품인가요?
## 달성하고자 하는 목표가 무엇인가요?
## 해결하고자 하는 문제는 무엇인가요?
## 왜 이 문제를 겪고 있을까요?
## 어떻게 해결하고자 하나요?
## 이 개선을 통해서 유저가 얻는 기대효과는 무엇인가요?
## 이 개선을 통해서 회사가 얻는 기대효과는 무엇인가요?
## 디자인 결과물 링크나 이미지
```

양식은 도구 호출 없이 바로 보여 주고 턴을 끝내요. 기준 문서와 화면은 답을 받은 뒤 한 턴에 열어요. 양식 아래에는 가상 UT(가상 사용자 3명 반응)를 뺄 수 있다는 한 줄이 붙어요. 빼면 결과가 더 빨리 나와요.

맥락은 만든 사람의 전제로만 써요. 지적 근거는 언제나 화면이에요.

## 입력

| 입력 | 방법 |
|---|---|
| 화면 이미지(기본) | 파일이나 폴더를 알려 줘요 |
| Figma 링크 | 환경 변수 `FIGMA_TOKEN`(읽기 전용 개인 액세스 토큰)이 있거나 환경에 Figma 도구가 있을 때만 해요. 없으면 이미지로 내보내 달라고 요청해요. 토큰은 환경 변수에서만 읽고 출력하거나 기록하지 않아요 |
| 라이브 서비스 주소 | 환경에 브라우저 도구가 있을 때만 해요. 없으면 스크린샷을 요청해요 |

세 방식 모두 읽기 전용이에요. Figma나 서비스에 아무것도 쓰지 않고 로그인, 결제, 삭제 같은 동작도 하지 않아요.

## 결과물

실행 폴더(`runs/<이름>/`)에 `review.json`(정본), `report.html`, `report.md`가 생겨요. `runs/`는 git에 올라가지 않아요.

예시 run이 `skill/ben-ux-feedback/examples/sample-run/`에 있어요(가상 가계부 앱 3화면). 리포트는 이 명령으로 다시 만들어요.

```bash
python3 skill/ben-ux-feedback/scripts/build_report.py --run skill/ben-ux-feedback/examples/sample-run
```

`examples/sample-run/report.html`이 생기면 브라우저로 열어요. 내 결과는 검증을 먼저 하고 만들어요.

```bash
python3 skill/ben-ux-feedback/scripts/validate.py --run runs/<이름> && python3 skill/ben-ux-feedback/scripts/build_report.py --run runs/<이름>
```

### 시안 비교

같은 화면의 시안 여러 개를 비교하면 `compare.json`(정본)과 `compare.html`이 생겨요. 결론과 순위, 시안 썸네일, 기준별 비교, 공통으로 고칠 것, 시안별 잘한 점과 아쉬운 점, 추천 조합이 한 장에 들어가요. HTML은 고정 틀이라 내용만 쓰면 돼요. 예시는 `skill/ben-ux-feedback/examples/sample-compare/`(가상 가계부 앱 예산 설정 2안)예요.

```bash
python3 skill/ben-ux-feedback/scripts/build_compare.py --run skill/ben-ux-feedback/examples/sample-compare
```

## 문구 판정

화면 속 문구는 [ben-ux-writing](https://github.com/jaechi-factory/ben-ux-writing)을 함께 설치하는 것을 권해요. 설치돼 있으면 그 스킬의 기준으로 판정해요. 없으면 가이드라인의 기본 점검만 하고, 문구 지적에 "ben-ux-writing 기준 미적용"이라고 밝혀요.

## 디자인 작업에도 같은 가이드라인 쓰기

화면을 새로 기획하거나 시안을 만들 때도 `skill/ben-ux-feedback/references/guideline.md`를 기준으로 쓸 수 있어요. 시작 전 질문 5개에 먼저 답하고, 해당 원칙의 부록만 펼치고, 끝나기 전에 해당 원칙만 표로 자가 점검해요. 리뷰할 때와 만들 때 기준이 같아야 피드백이 설계로 돌아와요. 이 스킬은 새 디자인을 만들어 주지는 않고 지킬 기준만 줘요.

## 가이드라인의 출처와 고지

가이드라인은 토스(비바리퍼블리카)의 공개 자료를 학습해 만든 독립 가이드예요. 토스와 제휴하거나 보증받은 관계가 아니에요. 자세한 내용은 [NOTICE.md](NOTICE.md)에 있어요. 가상 UT는 실제 사용자 조사가 아니고, 피드백은 보조 판단이라 최종 결정은 사람이 해요.

**알려진 한계:** 모델이 화면을 잘못 읽어 실제로 있는 요소를 "없어요"라고 지적할 때가 있어요. 공개 전 실험에서 한 모델이 화면 상단의 광고 고지를 두 번 연속 놓쳤어요. 심각 지적, 특히 "없어요·안 보여요" 지적은 화면에서 직접 확인한 뒤 반영해 주세요.

## 관리 방법

고치는 곳은 `skill/ben-ux-feedback/`(정본) 하나뿐이에요. `.claude/skills/`, `.agents/skills/`, `chat/`, `build-manifest.json`은 생성물이라 직접 고치지 않아요.

```bash
python3 scripts/build.py           # 정본에서 생성물을 다시 만들어요
python3 scripts/build.py --check   # 생성물이 정본과 같은지만 검사해요
python3 -m unittest discover -s tests -v
```

채팅용 고정 문구는 `scripts/chat_templates.py`에서 고쳐요. 자세한 결정 배경은 [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md), 변경 기록은 [CHANGELOG.md](CHANGELOG.md)에 있어요.

## 라이선스

[MIT](LICENSE). Copyright (c) 2026 jaechi.

## English summary

ben-ux-feedback is an MIT-licensed skill that reviews screen designs against a design guideline and returns severity-ranked findings (severe, medium, low), each with evidence and a ready-to-use fix. It can also run a virtual usability walkthrough with three simulated users (young, middle-aged, senior), which is inference from static screens and not real user research, and it builds HTML and Markdown reports, including a side-by-side comparison report for multiple design variants. It works with Claude Code (project and user scope), Codex, and chat-based LLMs through the files in `chat/`. The guideline was written independently from Toss's public materials and is not affiliated with or endorsed by Toss; see NOTICE.md. The skill is read-only, and the final decision stays with people. Feedback is written in Korean.
