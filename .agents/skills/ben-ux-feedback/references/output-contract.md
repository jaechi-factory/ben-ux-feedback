# 출력 계약

결과의 정본은 실행 폴더의 `review.json`이에요. 채팅만 되는 환경에서는 아래 마크다운 형식으로 같은 필드를 읽기 좋게 재배치해서 답해요. 모든 문구는 해요체예요. 검증은 `scripts/validate.py`가 해요. 어떤 규칙이 오류이고 어떤 규칙이 경고인지는 아래 "검증 수준" 절에 있어요.

실행 폴더 구조예요.

```
RUN/
  capture.json        입력 단계가 만든 화면 목록 (input.md)
  shots/              화면 이미지
  review.json         이 문서의 계약
  review-part-N.json  화면이 많을 때의 샤드 (선택)
```

모든 경로(`shot`, `evidence.shot`)는 `RUN` 기준 상대 경로이고 `RUN/shots/` 아래에 실제로 있는 이미지 파일이어야 해요(예: `shots/home.png`). `shots/` 밖의 파일은 검증기가 오류로 막고, 리포트 빌더도 넣지 않아요.

## review.json

최상위 키는 `run`, `screens`, `findings`, `strengths`, `checks_needed`, `summary`가 필수이고 `ut`는 선택이에요.

### run
| 필드 | 필수 | 설명 |
|---|---|---|
| `goal` | 선택 | 사용자가 준 목표나 제약 한 줄 |
| `product_value` | 필수 | 제품 핵심 가치 한 줄(가이드라인 4절 1번). 추론했으면 `checks_needed`에 적어요 |
| `input_type` | 필수 | `image` \| `figma` \| `live` |
| `writing_judge` | 필수 | `ben-ux-writing` \| `fallback` (`writing.md`) |
| `exclusions` | 선택 | 켠 제외 규칙 문자열 목록 (`input.md`) |
| `brief` | 선택(없으면 경고) | 리뷰 맥락. 아래 표 |

**run.brief**(SKILL.md 0단계 질문과 같은 순서예요)

| 필드 | 설명 |
|---|---|
| `product` | 어떤 제품인가요 |
| `objective` | 달성하고자 하는 목표 |
| `problem` | 해결하고자 하는 문제 |
| `cause` | 왜 이 문제를 겪는가 |
| `solution` | 어떻게 해결하고자 하나 |
| `user_value` | 유저가 얻는 기대효과 |
| `business_value` | 회사가 얻는 기대효과 |
| `source` | 필수. `user`(사용자가 씀) \| `inferred`(전부 추론) \| `mixed`(일부 추론) |

항목은 모두 문자열이고 빈 항목은 빼도 돼요. 하나도 채우지 않았으면 오류예요. 디자인 결과물 링크나 이미지는 `capture.json`이 맡아요. 리포트는 첫머리 검토 조건 옆에 이 내용을 "검토 전제"로 보여 줘요.

### screens[]
| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | 필수 | `capture.json`의 화면 id와 같아요 |
| `name` | 필수 | 화면 이름 |
| `shot` | 필수 | 화면 이미지 상대 경로 |
| `screen_goal` | 필수 | 화면 목표 한 줄 |
| `verdict` | 필수 | 한 줄 진단. 문제없으면 "문제없어요" 계열로 |

`capture.json`의 모든 화면이 여기에 있어야 해요. 빠진 화면이 "통과"로 위장되는 것을 막으려는 거예요. `screens`가 비어 있으면 결과가 성립하지 않아요(오류).

### findings[]
필드 순서는 아래와 같아요. 마크다운은 같은 필드를 읽기 좋게 재배치해요(아래 마크다운 절).

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | 필수 | `F01`처럼 겹치지 않는 id |
| `screen_id` | 필수(null 가능) | 근거 화면 id. `null`은 `lens=흐름`만 허용(빠진 분기의 진입 화면을 특정할 수 없을 때) |
| `severity` | 필수 | `심각` \| `중간` \| `낮음` |
| `lens` | 필수 | `화면` \| `흐름` \| `문구` \| `접근성` |
| `title` | 필수 | 한 줄 제목 |
| `observation` | 필수 | 화면에서 직접 본 것 |
| `why` | 필수 | 핵심 가치나 목표와 연결한 왜 문제인가. 사용자가 실패하는 방식과 제품 리스크까지 |
| `principle` | 필수(null 가능) | `guideline.md`에 있는 원칙 이름. 억지 연결이면 `null` |
| `case` | 선택 | 근거 사례 번호 `C###`. `cases.md`에 있는 번호만 |
| `fix` | 필수 | 바로 고칠 수 있는 수정안 요약 |
| `asis` | 문구는 필수 | 화면에 적힌 그대로 |
| `tobe` | 심각과 문구는 필수 | 수정 후 모습(문구, 순서, 구성) |
| `evidence` | 필수 | `{shot, where, type}` |
| `confirm_needed` | 선택 | 이 지적에서 화면만으로 확인하지 못한 부분 |
| `done_when` | 선택(심각은 권장) | 고쳤는지 확인하는 기준 한두 줄. 만든 사람이 화면에서 바로 확인할 수 있는 말로 적어요(예: "키보드가 올라와도 '저장하기'가 화면에 보여요") |
| `from_ut` | 선택 | 이 지적이 나오거나 근거가 보강된 가상 UT 페르소나 id 목록(`ut.personas[].id`) |

규칙은 다음과 같아요. 오류와 경고의 구분은 "검증 수준" 절에 있어요.

- `severity=심각`이면 `fix`와 `tobe` 모두 필수예요.
- `lens=문구`면 `asis`와 `tobe` 모두 필수예요.
- `evidence.type`은 `shot` \| `console` \| `dom`이에요. 기본은 `shot`이고, `shot`이면 `evidence.shot`이 필수이며 실제 파일이어야 해요. `console`이나 `dom`은 `where`에 근거 위치(메시지, 요소)를 적어요. 이 유형은 화면에 보이지 않는 보조 근거라는 표시예요.
- `evidence.where`는 화면 안 위치를 구체적으로 적어요(예: "하단 고정 버튼, 오른쪽 아래").
- 수량, 잘림, 크기는 직접 세어 확인한 것만 써요.
- `principle`이 `null`이면 `case`도 비워요.
- `run.writing_judge`가 `fallback`이면 문구 지적의 `confirm_needed`에 미적용 사실을 적어요(`writing.md`).

### strengths[]
지켜진 원칙과 화면 근거예요. 의례적인 칭찬은 쓰지 않아요.

```json
{"note": "무엇이 어떻게 잘 됐는지", "principle": "원칙 이름 또는 null", "screen_id": "화면 id 또는 null"}
```

### checks_needed[]
화면만으로 알 수 없어 미확인인 것과 확인 방법이에요.

```json
{"what": "알 수 없는 것", "how": "확인하는 방법"}
```

### summary
```json
{"headline": "핵심 문제를 짚는 한 문장", "top": ["F02", "F01"]}
```
`top`은 먼저 고칠 finding id를 우선순위 순서로 최대 5개 적어요. 리포트(HTML과 `report.md` 모두)의 "먼저 고칠 것"은 `top` 순서를 지키되 심각을 앞으로 올려 최대 3개만 보여요. `top`이 비면 전체 지적에서 심각도 순으로 골라요.

### ut (선택, 가상 UT)
연령대, 디바이스 적응도, UX 이해도가 다른 가상 사용자가 화면을 걸어 본 반응이에요. 실제 사용자 조사가 아니에요. 만드는 방법은 `personas.md`예요. 가상 UT를 끄면 이 키를 통째로 빼요.

```json
{
  "mode": "virtual",
  "personas": [
    {"id": "p-senior-dlo-ulo", "age_group": "노년", "device_level": "하", "ux_level": "하", "name": "박순자",
     "traits": "68세, 스마트폰은 은행 앱 정도만 써요. 가계부 앱은 처음이고 작은 글씨는 돋보기로 봐요.",
     "goal": "오늘 쓴 돈을 적는다"}
  ],
  "walks": [
    {"persona_id": "p-senior-dlo-ulo", "outcome": "이탈", "stopped_at": "add-expense",
     "stop_reason": "저장 버튼을 못 찾아서 입력을 포기했어요",
     "steps": [
       {"screen_id": "add-expense", "device": "막힘", "design": "보통", "writing": "막힘",
        "quote": "저장은 어디서 하는 거예요? 말도 너무 어려워요.",
        "cause": "저장 버튼이 키보드에 가려졌고 '변동비'라는 말을 몰라요",
        "finding_ids": ["F01", "F02"]}
     ]}
  ]
}
```

**personas[]**

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | 필수 | `p-{youth\|mid\|senior}-d{hi\|mid\|lo}-u{hi\|mid\|lo}` 형태를 권해요. 겹치지 않아야 해요 |
| `age_group` | 필수 | `청년` \| `중년` \| `노년` |
| `device_level` | 필수 | 디바이스 적응도 `상` \| `중` \| `하` |
| `ux_level` | 필수 | UX 이해도 `상` \| `중` \| `하` |
| `name` | 필수 | 이 런에서 지은 이름 |
| `traits` | 필수 | 능력, 이 제품 분야의 경험이나 불안, 몸과 마음 상태를 한두 문장으로 |
| `goal` | 필수 | 이 사람의 과업 한 줄 |

**walks[]** 는 페르소나와 1:1이에요. 페르소나마다 walk가 정확히 하나 있어요.

| 필드 | 필수 | 설명 |
|---|---|---|
| `persona_id` | 필수 | `personas[].id` |
| `outcome` | 필수 | `완주` \| `이탈` |
| `stopped_at` | 이탈이면 필수 | 멈춘 화면 id(`screens[].id`). 완주면 쓰지 않아요 |
| `stop_reason` | 이탈이면 필수 | 멈춘 이유. 완주면 쓰지 않아요 |
| `steps[]` | 필수 | 걸은 화면 순서대로 최소 1개 |

**steps[]**

| 필드 | 필수 | 설명 |
|---|---|---|
| `screen_id` | 필수 | `screens[].id` |
| `device` | 필수 | 디바이스 적응도. `쉬움` \| `보통` \| `막힘` |
| `design` | 필수 | 시안 이해도. `쉬움` \| `보통` \| `막힘` |
| `writing` | 필수 | 라이팅 이해도. `쉬움` \| `보통` \| `막힘` |
| `quote` | 필수 | 그 사람 말투의 한 문장 |
| `cause` | 막힘이면 필수 | 무엇 때문에 막혔는지 한 줄 |
| `finding_ids` | 필수 | 이 반응을 이은 `findings[].id` 목록. 막힘이 있으면 1개 이상, 없으면 빈 목록 |

규칙은 다음과 같아요.

- 세 축의 값은 `쉬움`, `보통`, `막힘` 세 가지뿐이에요. 점수, 시간, 완주율 같은 수치와 숫자 값은 `ut` 안에 어디에도 쓰지 않아요.
- 막힘 반응은 `finding_ids`로 지적에 이어요(오류). 보통 반응도 이어요(경고). 기존 지적이 없으면 새 지적을 만들고, 그 지적의 `from_ut`에 페르소나 id를 넣어요.
- 이탈한 walk의 마지막 step은 `stopped_at` 화면이에요(경고).
- `from_ut`의 id는 `ut.personas`에 있어야 해요.

## 검증 수준

`validate.py`는 규칙을 **오류**(exit 1)와 **경고**(출력만, `--strict`면 실패)로 나눠요. 이 문서의 "규칙"은 "(경고)"라고 적은 것을 빼면 아래 오류 항목과 같은 수준이에요. 경고 항목은 사람이 판단할 일이라 검증기가 보장하지 않아요. PASS가 곧 좋은 지적이라는 뜻은 아니에요.

| 수준 | 항목 |
|---|---|
| 오류 | 필수 필드와 형식(타입 포함), `severity`, `lens`, `run` 값, `screens`가 비어 있음, 없는 `screen_id`, shot 파일이 없거나 `RUN/shots/` 밖이거나 이미지 확장자(png, jpg, jpeg, webp, gif, svg)가 아님, 존재하지 않는 원칙 이름과 사례 번호, `principle`이 `null`인데 `case`가 있음, 심각의 `tobe`, 문구의 `asis`와 `tobe`, `fallback`인데 문구 지적에 `confirm_needed`가 없음, `summary.top`이 5개를 넘거나 없는 id를 가리킴, `capture.json` 화면이 `screens`에서 빠짐, 파트 사이 finding id 중복 |
| 오류(ut) | `mode`가 `virtual`이 아님, 페르소나 `id`가 비었거나 겹침, 페르소나의 `age_group`이 청년, 중년, 노년 밖, `device_level`이나 `ux_level`이 상, 중, 하 밖, 옛 필드 `age_band`나 `tech`가 있음, 페르소나와 walk가 1:1이 아님, 없는 `screen_id`, 세 축 값이 세 단계 밖, `quote` 비어 있음, 막힘인데 `cause`나 `finding_ids`가 없음, 없는 finding id, 이탈인데 `stopped_at`이나 `stop_reason`이 없음, 완주인데 둘이 있음, `from_ut`의 없는 페르소나, 숫자 값과 점수류 필드 |
| 오류 | 선택 필드 `done_when`이 문자열이 아님 |
| 경고 | 심각 지적에 `done_when`이 없음 |
| 경고 | 보통인데 연결된 지적이 없음, 마지막 step이 `stopped_at`과 다름, `from_ut`로 표시했는데 그 walk에서 연결한 step이 없음 |
| 경고 | 가상 UT 페르소나가 3명이 아니거나 연령대가 겹침(사용자가 인원이나 연령대를 정했다면 무시해도 돼요) |
| 경고 | 심각 지적의 제목이나 `observation`이 "없어요", "안 보여요", "빠져 있어요" 같은 부재 주장인데, `observation`이나 `confirm_needed`에 화면을 훑은 흔적(비슷한 요소의 위치, 가장 가까운 요소)이 없음 |
| 경고 | `evidence.shot`이 화면 shot과 다름, 근거 유형과 `where`가 어긋남, 추상적인 `fix`, 같은 제목의 중복 지적, 화면 `verdict`가 문제를 말하는데 연결된 지적이 없음, `summary.top`이 비어 있음, `capture.json`이 없어 전수 검사를 못 함, 제외 규칙 위반 의심, `asis` 인용이 `capture.json`의 `aux_text`에 없음, `run.input_type`이 `capture.json`과 다름 |

경고 항목은 휴리스틱이라 오탐과 누락이 있어요. 검증을 못 돌렸으면 이 표의 항목을 손으로 확인하고 못 돌렸다고 밝혀요.

## 샤딩

화면이 많으면 `review-part-1.json`, `review-part-2.json`…으로 나눠 써요. 각 파트는 위 구조의 일부(`screens`, `findings`, 필요하면 `strengths`, `checks_needed`)를 담아요. `validate.py`는 파트가 있으면 **항상** 다시 합쳐 `review.json`을 덮어써요. 파트를 고친 뒤 재검증해도 옛 합본이 남지 않게 하려는 거예요. 합본을 직접 고쳤다면 파트에도 같은 수정을 해요.

- `run`은 비어 있지 않은 첫 파트의 것을 써요. `summary`는 `headline`이 있는 마지막 파트의 것을 써요.
- `screens`는 id 기준으로 중복을 걸러요. `findings`, `strengths`, `checks_needed`는 이어 붙여요.
- finding `id`가 파트 사이에 겹치면 오류예요.

## 예시 (가상 제품)

가상의 가계부 앱 "모아가계부"의 지출 입력 화면 한 장을 검토한 결과예요.

```json
{
  "run": {
    "goal": "지출 입력 화면 첫 시안 검토",
    "product_value": "지출을 3초 안에 적고 한 달 흐름을 바로 본다",
    "input_type": "image",
    "writing_judge": "fallback"
  },
  "screens": [
    {
      "id": "add-expense",
      "name": "지출 입력",
      "shot": "shots/add-expense.png",
      "screen_goal": "방금 쓴 돈을 금액과 분류로 기록한다",
      "verdict": "금액 입력은 정석인데 분류가 전문 용어라 3초 안에 못 골라요."
    }
  ],
  "findings": [
    {
      "id": "F01",
      "screen_id": "add-expense",
      "severity": "심각",
      "lens": "화면",
      "title": "저장 버튼이 키보드에 가려져요",
      "observation": "금액 입력칸에 포커스가 있는 상태에서 하단 '저장' 버튼이 화면 밖에 있어요. 보이는 버튼은 '취소' 하나뿐이에요.",
      "why": "저장 방법이 보이지 않아 사용자가 취소를 눌러 입력한 내용을 잃을 수 있어요. 핵심 가치인 3초 기록을 직접 깨뜨려요.",
      "principle": "Clear Action",
      "fix": "저장 버튼을 키보드 위에 붙여 고정해요.",
      "tobe": "금액 입력 중에도 키보드 바로 위에 '저장하기' 버튼을 고정하고, '취소'는 상단 닫기로 옮겨요.",
      "evidence": {"shot": "shots/add-expense.png", "where": "화면 하단, 키보드 영역", "type": "shot"},
      "done_when": "키보드가 올라온 상태에서도 '저장하기'가 화면에 보이고, 한 번 눌러 저장돼요.",
      "confirm_needed": "실제 기기에서 키보드가 올라올 때의 동작은 이미지로 볼 수 없어요."
    },
    {
      "id": "F02",
      "screen_id": "add-expense",
      "severity": "중간",
      "lens": "문구",
      "title": "분류 이름이 내부 용어예요",
      "observation": "분류 칩 첫 줄에 '변동비', '고정비'가 있어요.",
      "why": "방금 커피를 산 사용자가 어느 쪽인지 바로 알기 어려워 선택에서 멈춰요.",
      "principle": "Casual Concept",
      "fix": "사용자가 쓰는 말로 바꿔요.",
      "asis": "변동비 / 고정비",
      "tobe": "그때그때 쓰는 돈 / 매달 나가는 돈",
      "evidence": {"shot": "shots/add-expense.png", "where": "분류 칩 첫 줄", "type": "shot"},
      "confirm_needed": "ben-ux-writing 기준 미적용"
    }
  ],
  "strengths": [
    {"note": "금액 입력칸이 화면 첫 요소이고 숫자 키패드로 열려요.", "principle": "Sleek Experience", "screen_id": "add-expense"}
  ],
  "checks_needed": [
    {"what": "문장 세부 기준(ben-ux-writing) 미적용", "how": "ben-ux-writing을 설치한 뒤 문구 지적만 다시 판정해요"},
    {"what": "저장 후 어디로 돌아가는지", "how": "저장 이후 화면을 이미지로 추가해요"}
  ],
  "summary": {"headline": "기록 속도는 좋은데 저장 버튼이 가려지고 분류가 어려워요.", "top": ["F01", "F02"]}
}
```

## 비교 모드 (compare.json)

같은 목적의 시안 여러 개를 비교할 때 쓰는 결과예요(SKILL.md 0단계). `RUN/compare.json`에 내용만 쓰고, `scripts/build_compare.py`가 검사한 뒤 고정 틀로 `compare.html`을 그려요. HTML을 직접 쓰지 않아요. `capture.json`과 `shots/` 규칙은 단일 모드와 같아요.

| 필드 | 필수 | 설명 |
|---|---|---|
| `headline` | 필수 | 결론 한 문장(예: "B안이 가장 좋아요") |
| `lead` | 필수 | 왜 그런지와 먼저 고칠 것을 두세 문장으로 |
| `title`, `kicker` | 선택 | 문서 제목, 제목 위 작은 분류 줄 |
| `variants[]` | 필수 | 시안 2개 이상. 아래 표 |
| `criteria_lead` | 선택 | 기준을 고른 이유 한 줄 |
| `criteria[]` | 필수 | 비교 기준 1개 이상. `{label, cells}`이고 `cells`는 시안 `id`마다 `{level, word, note}`예요. `level`은 `good` \| `mid` \| `bad`, `word`는 한두 단어 판정, `note`는 근거 몇 단어(선택) |
| `common[]` | 선택 | 어느 시안을 고르든 고칠 것. 아래 "지적 항목" 표의 필드에 `title`, `body`, `applies`(해당 시안, 선택)를 더해요 |
| `exclusions` | 선택 | 켠 제외 규칙 문자열 목록(`input.md`). 단일 모드 `run.exclusions`와 같아요 |
| `brief` | 선택(없으면 경고) | 리뷰 맥락. 단일 모드 `run.brief`와 같은 형식이고, 리포트 결론 아래 "검토 전제 보기"로 접혀 나와요 |
| `ut` | 선택(기본 실행) | 1위 시안 가상 UT. 아래 표 |
| `recipe` | 선택 | 추천 조합. `{lead, steps[{title, detail}], spec[{label, value}], note}` |
| `checks[]` | 선택 | 화면만으로 알 수 없는 것 `{what, how}` |
| `footer[]` | 선택 | 검토 대상, 기준, 제외 규칙 같은 메모 문장 |

**variants[]**

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | 필수 | `capture.json`의 화면 id와 같아요 |
| `rank` | 필수 | 1부터 시안 수까지 한 번씩. 1이 추천안이에요 |
| `name`, `short` | `name` 필수 | 시안 이름. `short`는 기준별 비교 머리줄에 쓸 짧은 이름(선택) |
| `shot` | 필수 | `shots/` 아래 이미지 |
| `one_line` | 필수 | 썸네일 아래 한 줄 평(열 자 안팎) |
| `why` | 필수 | 순위 목록에 쓰는 이유 한 문장 |
| `summary` | 필수 | 상세 첫 문단. 이 시안을 한두 문장으로 진단해요 |
| `goods[]` | `cons`와 둘 중 하나 이상 필수 | 지켜진 원칙과 화면 근거. 검산한 사실도 여기에 써요 |
| `goods_label` | 선택 | 잘한 점 제목을 바꿀 때(예: "살릴 것") |
| `cons[]` | `goods`와 둘 중 하나 이상 필수 | 아래 "지적 항목" 표의 필드에 `text`(화면에서 본 문제)를 더해요 |
| `source`, `alt` | 선택 | 출처 표기(예: 노드 id), 이미지 대체 텍스트 |

**지적 항목(`cons[]`, `common[]`)**은 단일 모드 `findings[]`와 같은 규율을 받아요.

| 필드 | 필수 | 설명 |
|---|---|---|
| `severity` | 필수 | `심각` \| `중간` \| `낮음` |
| `where` | 필수 | 화면 안 위치(단일 모드 `evidence.where`와 같아요) |
| `fix` | 필수 | 바로 고칠 수 있는 수정안 요약 |
| `tobe` | 심각은 필수 | 수정 후 모습(문구, 순서, 구성) |
| `done_when` | 선택(심각은 권장) | 고쳤는지 확인하는 기준 |
| `principle`, `case` | 선택 | `guideline.md`의 원칙 이름과 `cases.md`의 사례 번호. 억지 연결이면 비워요 |
| `confirm_needed` | 선택 | 이 지적에서 화면만으로 확인하지 못한 부분 |
| `id` | 선택 | 가상 UT 반응을 이을 때 쓰는 겹치지 않는 id |

**ut(비교 모드)**: `{mode: "virtual", variant: 1위 시안 id, personas[]}`이고, `personas[]`는 `{name, age_group, device_level, ux_level, traits, goal, device, design, writing, outcome, quote, cause, issue_ids}`예요. 값의 범위와 금지 규칙(수치 금지, 막힘이면 `cause`와 `issue_ids` 필수)은 단일 모드 `ut`와 같아요(`personas.md`). 비교 모드는 시안 한 장을 보니 walk 대신 페르소나마다 반응 하나를 바로 적어요.

검사 수준은 이래요.

- **오류(exit 1)**: 필수 필드와 타입, `rank`(겹치거나 빠짐), 기준 칸 누락(모든 기준에 모든 시안 칸이 있어야 하고 없는 시안 id는 안 돼요), `brief` 형식, `ut.issue_ids`가 1위 시안의 `cons`나 `common` 밖을 가리킴, `severity`·`level` 값, 심각의 `tobe`, 없는 원칙 이름과 사례 번호, 원칙 없이 사례만 있음, shot 경로, 전수 커버리지(`capture.json`과 시안 id가 서로 빠짐없이 맞아야 해요), 가상 UT 구조
- **경고(`--strict`면 실패)**: `brief` 없음, `ut.variant`가 1위가 아님, 심각의 `done_when` 없음, 훑은 흔적 없는 심각 부재 주장, `tobe` 없는 추상 수정안, 제외 규칙 위반 의심, `ut` 없음, 가상 UT 보통 반응의 연결 없음, 페르소나 구성
- 화면에 보이는 것만 근거로 쓰고 수량은 직접 센 것만 쓰는 규율은 검사기가 볼 수 없어요. 단일 모드와 똑같이 직접 지켜요.

- 글 안의 `**굵게**`와 `{자리표시}`만 서식으로 바뀌어요. 그 밖의 HTML은 그대로 글자로 나와요.

공통 문제와 시안별 문제는 겹쳐 쓰지 않아요. 둘 이상의 시안에 같은 원인이 있으면 `common`에 한 번만 쓰고 `applies`에 해당 시안을 적어요.

## 마크다운 출력 형식 (채팅 전용)

`review.json`을 쓸 수 없는 환경에서 써요. 필드는 JSON과 같지만 읽기 좋게 재배치해요. 총평(`summary`)과 검토 조건(`run`)을 맨 위에 두고, 지적은 `severity`를 제목 앞에 두고, `evidence.where`는 "화면" 줄로 올려요. 지적은 심각, 중간, 낮음 순으로 정렬해요. 값이 없는 선택 필드의 줄은 빼요.

```markdown
## 총평
**{summary.headline}**
먼저 고칠 것: {summary.top의 id와 title, 심각 먼저, 최대 3개}

검토 조건: 입력 {run.input_type} · 문구 판정 {run.writing_judge}
제품 핵심 가치: {run.product_value}
목표: {run.goal}
제외 규칙: {run.exclusions}

## 화면
### {screens.name} (`{screens.id}`)
- 화면 목표: {screen_goal}
- 한 줄 진단: {verdict}

## 지적
### [{severity}] {id} {title}  (렌즈: {lens})
- 화면: {screen_id} · {evidence.where} (근거 유형: {evidence.type})
- 관찰: {observation}
- 왜 문제인가: {why}
- 근거 원칙: {principle} {case}
- 제안: {fix}
- 수정 전: {asis}
- 수정 후: {tobe}
- 고쳤는지 확인하는 기준: {done_when}
- 확인 필요: {confirm_needed}
- 가상 UT에서 나온 지적: {from_ut의 이름}

## 가상 UT (실제 사용자 조사가 아니라 화면을 보고 추론한 가상 반응이에요)
페르소나를 이렇게 골랐어요: {고른 이유 한 줄}

### 페르소나
- {name} (`{id}`, {age_group}, 디바이스 적응도 {device_level}, UX 이해도 {ux_level}): {traits} 목표: {goal}

### {name}: {outcome}  (이탈이면 `{stopped_at}`에서 멈춤, 이유: {stop_reason})
| 화면 | 디바이스 | 시안 이해 | 문구 이해 | 한마디 |
|---|---|---|---|---|
| {screens.name} (`{screen_id}`) | {device} | {design} | {writing} | "{quote}" {막힘이면 원인: cause} |

### 반응에서 나온 지적
- {name} · {screens.name}: {막힘 또는 보통인 축} → {finding id} {title}

## 잘 된 점
- {note} ({principle}, {screen_id})

## 확인 필요
- {what}: {how}
```

`scripts/build_report.py`가 만드는 `report.md`는 끝에 "남은 지적 체크리스트"를 붙여요(`- [ ]` 형식, 지적마다 고치는 방법과 `done_when`을 하위 줄로). 이 파일은 화면에서 읽어 온 글이 들어가므로 마크다운 문법 문자(`[ ] ( ) ! * _` 와 백틱)를 이스케이프하고 `http://`, `https://`는 자동 링크가 되지 않게 끊어요.

- `screen_id`가 `null`인 흐름 지적은 화면 줄에 "여러 화면에 걸친 흐름"이라고 쓰고 `evidence.where`에 진입 화면을 적어요.
- 원칙이 `null`이면 "근거 원칙" 줄을 빼요.
- 가상 UT 절은 `ut`가 있을 때만 쓰고, 표 안에는 쉬움, 보통, 막힘만 적어요. 수치(완주율, 점수, 시간)는 쓰지 않아요. 이탈한 사람은 표가 멈춘 화면에서 끝나요.
- 채팅은 길이가 길면 읽기 어려우니, 중간과 낮음이 많으면 제목과 제안만 표로 줄이고 심각은 전체 필드를 써요.
- 검증기를 돌리지 못했다면 마지막에 "검증 스크립트는 실행하지 못했어요"라고 밝혀요.

### 비교 모드 (채팅 전용)

`compare.json`을 쓸 수 없으면 같은 필드를 이 순서로 답해요.

```markdown
## {headline}
{lead}

검토 전제: {brief의 채운 항목을 한 줄씩. 추론했으면 "(추론)"}

| 순위 | 시안 | 이유 |
|---|---|---|
| {rank} | {name} | {why} |

## 기준별 비교
| 기준 | {시안 이름들} |
|---|---|
| {label} | {word} {note} |

## 어느 시안을 고르든 고칠 것
### [{severity}] {title} (해당: {applies})
- 화면: {where}
- 관찰: {body}
- 제안: {fix}
- 수정 후: {tobe}
- 고쳤는지 확인하는 기준: {done_when}
- 근거 원칙: {principle} {case}
- 확인 필요: {confirm_needed}

## 시안별 아쉬운 점
### {rank}. {name}
- 잘한 점: {goods}
- [{severity}] {text} (화면: {where}) → {fix}
  - 심각이면 아래 줄을 꼭 붙여요: 수정 후: {tobe} · 확인 기준: {done_when} · 근거 원칙: {principle}

## 가상 UT: {1위 시안 name} (실제 사용자 조사가 아니라 화면을 보고 추론한 가상 반응이에요)
| 사람 | 디바이스 | 시안 이해 | 문구 이해 | 한마디 |
|---|---|---|---|---|
| {name} ({age_group}, 디바이스 {device_level}, UX 이해 {ux_level}) | {device} | {design} | {writing} | "{quote}" {막힘이면 원인: cause} |

## 추천 조합
1. {steps.title}: {steps.detail}

## 확인 필요
- {what}: {how}
```
