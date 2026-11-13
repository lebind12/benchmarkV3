# HP-EVIDENCE — 승인한 정확한 저장 섹션의 홈 연결

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 적용한다. 기존 읽기와 미변경 해시는 재사용한다. 실제 DeepSeek flash-1017 Max 유지. 이전 기본시각 수정은 독립 검토까지 수용됐으며 이번은 실제 사용자승인 후 관측된 홈 승인조회 연결 결함이다.

## 확인된 실제 사실

사용자는 맨시티–풀럼 저장구성본 `cmp-ec3ad7cb7c47`의5개섹션을 저장버전으로 표시하도록 명시승인했다. root는 정확한 실행/섹션결과를 기존 approveSection으로 POST했고5개가모두성공했다. 원본문/결과/구성본은수정하지않았다.

| 섹션 | 결과행에 저장된 버전 | 생성된 활성승인 버전 | 실행 / 승인근거 결과 |
|---|---|---|---|
| section_ai_forecast | @8d4f5288197089fe | @c186f27356d4bb80 | d96fe824-bc38-4402-bb2c-9f16fdee4b3b / 81b710b7-7c97-4235-a550-0654df51a269 |
| section_availability | @643296ca23b42faf | @7dc7fec4ec7919ac | d96fe824-bc38-4402-bb2c-9f16fdee4b3b / 0aa7bb7c-42b4-40cd-9307-43fd09f5ca0b |
| section_odds | @49923b1c5dcb467a | @49923b1c5dcb467a | 493ef4a9-0e14-4436-8a97-d6de7ce034a7 / f6cc06ca-ea0c-423d-8eb2-c437b2348080 |
| section_outlook | @ad49f4e4058f7bbb | @0145de693ebdef28 | d96fe824-bc38-4402-bb2c-9f16fdee4b3b / 6f79463a-f154-4bf0-bdfb-d02bf57f874d |
| section_players | @f29a3253194f31b1 | @174a98077f78af37 | d96fe824-bc38-4402-bb2c-9f16fdee4b3b / 714599db-3edb-4cb9-bf19-d9b394939230 |

`@` 앞에는 해당 행의 섹션명이 붙는다. 저장된 approval ID는 root의 증거 문서에 기록한다. 공개 GET1557474는 현재 available이지만 section_odds1개뿐이며,4개는 `approved_versions`의 문자열 비교에서 제외된다. 승인에는 근거 결과가 정확히 들어 있다. `approvals.py`는 자체 manifest가 없는 옛 결과의 구성 버전을 재계산하는 기존 정책이며, F3의 옛 section_form 검사는 이 동작을 의도적으로 요구한다. 이 정책 전체를 바꿔 같은 stamp를 만드는 수정은 채택하지 않는다.

추가 정정: 구성본items의배당metadata는옛@08ed203a23b234b5지만 실제그result_id의섹션행GET은@49923b1c5dcb467a다. root가구성본보조metadata를버전정본으로봤던내용은정정한다. 경기원문/저장결과를변경해서맞추지않는다.

## 최소 결정과 수용 기준

공개 홈의 승인판정에 **활성승인이 명시적으로 가리키는 정확한 실행·섹션결과·워크플로우 근거**를 반영한다. 버전승인이 정상일치하는 기존경로는유지한다. 버전문자열이다를때는승인된바로그결과만표시할수있으며다른결과/다른경기/같은workflow의미승인버전으로확대하지않는다. 잘못된/비활성승인·mock·본문없음은여전히제외한다. 이경로는그저장결과를명시승인한사용자의의도를따르는조회이며현재생성코드전체승인을조작하는것이아니다.

구성본정확선택·타실행선택·본문없는실행건너뛰기·최신선택·화이트리스트·무쓰기/외부무호출GET을유지한다. 승인행/섹션행/구성본/원문/버전계산/생성파이프라인은수정하지않는다. 새승인POST·원시SQL쓰기·재생성·DB탐색은root만수행하며이작업에는없다.

## 소유·검사·종료

소유는 `app/services/home_preview_document.py`, `tests/unit/test_home_preview_document.py`, 새 `docs/implementation/match-preview/home-approved-evidence-report.md`뿐이다. 승인서비스/관리자/공통본문/프론트/Plans는읽기참고만한다. 필요한입력계약이이범위에서불가능하면수정전에최소범위를보고한다.

대표검사는활성승인이정확히가리키는행은버전문자열차이가있어도표시되고,근거가다른행/비활성/모의는그이유로추가공개되지않는하나의대표시나리오면충분하다. 새검사이유는'승인한문서가홈에서4섹션빠짐'이다. 기존직접명령 `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q`만수정전후필요횟수실행한다. 실제DB/모델/API/브라우저/서버/전체회귀/mutation/설치금지. 동일문제2회수정실패면원인과가장작은범위를보고한다.

완료보고에는원인·승인근거경계·개별검사결과·변경파일·스킬/원칙의결정·EDITINGSTOPPED/백그라운드0을담는다. 이번새Task/Dispatch로worker_done한번후idle. 과거종료메일/timeout/Task를찾거나복구하지않는다.
