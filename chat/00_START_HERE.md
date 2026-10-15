<!-- 생성 파일이에요. 직접 고치지 말고 scripts/chat_templates.py를 고친 뒤 python3 scripts/build.py를 실행해요. -->
# 여기서 시작해요

이 폴더는 ChatGPT, Gemini, Claude 웹 같은 채팅형 LLM에서 ben-ux-feedback을 쓰는 방법이에요. 스크립트나 도구 없이 파일 올리기와 대화만으로 써요. 서비스마다 메뉴 이름은 조금씩 달라요.

## 파일 설명

| 파일 | 하는 일 | 어디에 쓰나 |
|---|---|---|
| `PROJECT_INSTRUCTIONS.md` | 짧은 지침 | 프로젝트 지침(Instructions)에 붙여 넣어요 |
| `KNOWLEDGE.md` | 가이드라인, 판정 절차, 문구 기준, 가상 UT 페르소나, 마크다운 출력 형식 | 프로젝트 파일(Knowledge)로 올려요 |
| `KNOWLEDGE_APPENDIX.md` | 원칙별 상세 규칙과 사례 | 올릴 수 있으면 같이 올려요. 길어서 못 올리면 빼도 돼요 |
| `REQUEST_EXAMPLES.md` | 요청 문장 예시 | 복사해서 대화에 붙여 써요 |

## 설정 3단계

1. 프로젝트를 만들어요. Claude의 Projects, ChatGPT의 프로젝트나 GPT, Gemini의 Gem 같은 기능이에요.
2. `PROJECT_INSTRUCTIONS.md`의 내용을 통째로 복사해서 프로젝트 지침에 붙여 넣어요.
3. `KNOWLEDGE.md`를 프로젝트 파일로 올려요. 가능하면 `KNOWLEDGE_APPENDIX.md`도 올려요.

프로젝트 기능이 없으면 새 대화의 첫 메시지에 지침을 붙여 넣고 `KNOWLEDGE.md`를 첨부해요. 첨부가 안 되면 내용을 이어서 붙여 넣어요.

## 쓰는 법

1. 검토할 화면 이미지를 올려요. 여러 장이면 한 번에 올려요.
2. `REQUEST_EXAMPLES.md`에서 비슷한 문장을 골라 붙여 넣고, 대괄호 안을 내 상황에 맞게 바꿔요.
3. 답을 받으면 심각한 지적부터 확인해요. 고친 뒤에는 화면을 다시 올려서 확인을 부탁해요.

## 알아 둘 것

- 올린 이미지에 보이는 것만 근거로 삼아요. Figma 링크나 서비스 주소는 열어 볼 수 없으니 스크린샷을 올려요.
- 검증 스크립트와 HTML 리포트는 만들 수 없어요. 리포트가 필요하면 Claude Code나 Codex에서 쓰는 방법을 README에서 봐요.
- 가상 UT는 화면을 보고 추론한 가상 반응이에요. 실제 사용자 조사가 아니에요.
- 문구 판정은 ben-ux-writing이 없는 상태라서 가이드라인의 기본 점검만 해요. 답변에 그렇게 적혀 나와요.
- 피드백은 보조 판단이에요. 최종 결정은 사람이 해요.
