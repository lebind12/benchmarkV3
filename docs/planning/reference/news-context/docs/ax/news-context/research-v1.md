> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/ax/news-context/research-v1.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 기사·커뮤니티 문맥 연결: 선행 사례와 구현 방법 조사

상태: **개발 전 조사 결과**. 기술 선택·성능·비용·제품 검증 완료를 뜻하지 않는다. 기존 기획의 다국어 입력, 최대 5만 자, 한국어 호버, 문맥별 기록/경기/이력, 공통 판단 저장·수정·취소 요구를 유지한다.

## 1. 조사 범위와 근거 수준

미디어·DB 조회 사례 8개, 개체 연결 연구 6개, 피드백 구현 도구 5개를 비교했다. 원문 위치·검색·임베딩·LLM 출력·평가에 필요한 공식 문서도 함께 읽었다. 제작자 발표/논문/공식 코드/공식 사용 안내를 우선했고, 확인되지 않은 구현은 미공개로 표시했다.

- **운영 사례:** 발표 시점의 실제 적용을 확인했다는 의미다. 지금도 같은 구조로 운영된다는 뜻은 아니다.
- **공개 실험·POC:** 사용자가 시험할 수 있었거나 개발자가 실험한 기능이다. 상시 운영 성과와 구분한다.
- **연구:** 특정 언어·데이터·주어진 후보/mention 조건의 결과다. 한국 축구 커뮤니티 품질로 전용하지 않는다.
- **도구:** 공개 기능·코드의 존재를 확인했다. 우리 서비스에서 설치·실행·성능 검증한 것은 아니다.

이번 조사에서 제품 파일 수정, 새 패키지/확장 설치, 유료 모델 평가, 운영 DB 쓰기, 배포는 하지 않았다. DB 환경은 읽기 전용으로 조회했다.

## 2. 미디어·스포츠·DB 조회 사례 8개

### 2.1 BBC Sport / London Olympics Dynamic Semantic Publishing

**2012-09-20 제작자 발표, 당시 운영 적용 사례.** 기사와 스포츠 데이터를 스포츠 온톨로지/KB에 연결하고, 개체 후보를 주변 문맥·유형·그래프 특징으로 판별했다. 기자가 annotation을 확인하면 OWLIM에 저장하고 **이름 사전은 즉시, 통계 모델은 주기적으로 갱신**했다. 관련 선수·팀·대회 페이지에 콘텐츠와 통계를 공급했다.

공개 스택은 Ontotext CES/GATE, BigOWLIM·SPARQL·RDF, Information Workbench이며 문서·통계 처리에는 MarkLogic/XQuery도 쓰였다. 우리 요구에 가까운 점은 도메인 KB, 사람 확정, 다음 후보 생성에 교정을 반영하는 경로다. 기사 hover, 한국어, 5만 자, 판단 취소·감사이력이 제공됐다는 근거는 없다. 발표의 F1 수치는 평가 조건이 충분히 공개되지 않아 프로젝트 목표로 사용하지 않는다. [BBC 설계자 발표, 특히 20~30·42·50~60번](https://speakerdeck.com/jemrayfield/bbc-dynamic-semantic-publishing-sport%7Colympics-semtechbiz-uk)

**적용 아이디어:** 축구 DB의 안정된 ID와 문맥을 후보 생성에 쓰고, 확인된 별명/해석은 다음 검색에서 즉시 읽는다. 모델 weight 갱신은 별도 작업으로 구분한다. 당시 RDF 저장소 선택을 그대로 복제해야 한다는 뜻은 아니다.

### 2.2 Washington Post Knowledge Map

**2015-07 공개 실험.** 편집자가 설명이 필요한 구절과 보충 설명을 정하고, 독자가 기사 속 강조어를 클릭/탭하면 같은 페이지에서 짧은 설명을 읽게 했다. 읽던 문맥에서 배경 정보를 확인하는 UX가 이번 호버 목표와 가깝다.

제작진 인터뷰에서 공통 supplement DB, 문장 분석을 통한 추천, 편집한 설명의 재사용·CMS 통합은 **향후 계획**이었다. 초기 DB·언어·모델 스택은 미공개다. 이를 자동 개체 연결과 공통 학습까지 운영한 제품으로 설명해서는 안 된다. [공식 실험 발표](https://www.washingtonpost.com/pr/wp/2015/07/16/the-washington-post-tests-new-knowledge-map-feature/), [제작진 인터뷰](https://www.niemanlab.org/2015/07/how-the-washington-post-built-and-will-be-building-on-its-knowledge-map-feature/)

**적용 아이디어:** 기본 프로필과 ‘이 문장을 이해하는 데 필요한 정보’를 별도로 다룬다. 사용자에게는 그 구절과 연결 이유, 해당 기록·경기·이력을 짧게 보여준다.

### 2.3 New York Times의 편집자 태깅

**2018-03-14 담당 taxonomist의 실제 운영 설명.** 제목·본문 위치·같은 문장 단어 등을 이용해 주제·개체 후보를 추천하고 편집자가 선택하거나 어휘를 검색한다. 신규 개체는 taxonomy 팀이 확인하고 동명이인 규칙을 작성한 뒤 기존 콘텐츠도 다시 태깅했다. 확정 태그는 검색·알림·추천에 사용됐다. 특정 분류기 제품과 저장 DB는 이 자료에 공개되지 않았다.

주요 교훈은 사람이 고친 결과를 규칙·어휘 갱신으로 연결하는 운영이다. 다만 NYT는 핵심 주제를 태깅하며 모든 언급을 태깅하지 않는다고 설명한다. 원문의 여러 영역을 설명해야 하는 이번 기능과 평가 단위가 다르다. [NYT 담당자 원문](https://iptc.org/news/metadata-and-the-tagging-process-at-the-new-york-times/)

### 2.4 Guardian Open Platform의 외부 ID 연결

**2010-10-18 공개 API 적용 사례.** 기사·편집 태그에 ISBN·MusicBrainz 같은 외부 식별자를 붙이고 기존 annotation DB와 Solr 검색 인덱스를 통해 정확한 대상의 콘텐츠를 조회하게 했다. 자동 언어모델이나 원문 hover 사례는 아니다.

축구 서비스에서는 표시 이름이 달라져도 API-Football ID·내부 ID로 같은 대상을 가리키는 설계의 근거다. 동일 이름으로 기사를 찾는 것과 DB의 안정된 식별자에 연결하는 것을 구분해야 한다. [Guardian 공식 발표](https://theguardian.engineering/blog/help-insideguardian-2010-oct-18-linked-data-guardian-open-platform.html), [담당 정보설계자의 구현 설명](https://www.currybet.net/cbet_blog/2010/10/adding-linked-data-to-guardian-api.php)

### 2.5 Financial Times Knowledge Graph

**2016 전환 회고 및 2024-12-18 실무자 자료.** 기사·편집 태그·외부 개체를 공통 식별자에 연결하고 인물·조직·장소 및 관계를 Neo4j에 저장해 Enriched Content API 등으로 공급한다. 인물의 과거 소속·직책·기간도 표현한다. 과거 기사에 현재 소속만 붙이면 안 된다는 점에서 축구의 이적 전후·시즌 문맥과 연결된다.

2016 자료는 Go·neoism·API 전환을 설명한다. 2024 글에서 기존 KG는 운영 기반이지만, 벡터·그래프를 이용한 기사 클러스터링은 POC다. 이 POC 결과를 개체 연결 정확도나 운영 추천 개선으로 해석하지 않는다. [FT 2024 기술팀 글](https://medium.com/ft-product-technology/navigating-the-financial-times-knowledge-graph-00d83f0374c1), [담당 개발자 전환 회고](https://neo4j.com/blog/knowledge-graph/go-neo4j-financial-times/)

### 2.6 Thomson Reuters OpenCalais + Prefix Preditor

**2010-06-24 공급사 상용 적용 발표.** 잡지 기사·아카이브를 OpenCalais와 잡지별 규칙으로 태깅하고 Preditor CMS·아카이브에 연결해 관련 콘텐츠를 smart link로 제공했다. 자동 추출과 매체별 규칙, 과거 콘텐츠 연결을 결합한 사례다.

저장 DB·세부 UI는 미공개이며 고객 직접 증언을 포함한 공급사 보도자료다. 독립 성능 검증도, Reuters 자체 기사 hover 기능도 아니다. 과거 적용 사례로 참고하고 현재 API 채택 후보라고 간주하지 않는다. [Thomson Reuters 원문 PDF](https://ir.thomsonreuters.com/node/12136/pdf)

### 2.7 티오더 티스푼

**2026-04-17 제작자·공급사 기술 글.** Slack 질문 → 의도·용어 확인 → 스키마/쿼리 예제/JSON 필드/용어 사전 검색 → SQL 생성·EXPLAIN → 사용자 확인 → Athena 실행의 흐름이다. Claude/Bedrock, LangGraph, S3 Vectors 등을 사용한다.

유사한 문서만 검색하면 JOIN에 필요한 스키마가 빠질 수 있어 관련 테이블·패턴·의존성·용어를 단계별로 보강한다. 축구에서도 ‘득점’, ‘최근 5경기’, ‘지난 시즌’의 뜻과 실제 DB 필드를 연결할 사전이 필요하다는 근거다. 비용·스택을 그대로 도입할 이유는 없으며, SQL의 문법 통과가 의도에 맞는 집계를 보장하지 않는다는 점이 중요하다. [AWS 원문](https://aws.amazon.com/ko/blogs/tech/torder-text2sql-case/)

### 2.8 Uber QueryGPT

**2024-09-19 제작자 운영 설명.** 자연어 질문을 도메인에 배정하고 관련 테이블·SQL 예제를 검색한 후 사용자가 테이블 선택을 수정하도록 했다. 큰 스키마로 인한 token 문제에는 관련 없는 컬럼을 제거하는 단계를 추가했다.

축구의 선수 기록·팀 순위·경기·이력처럼 조회 영역을 좁히고 필요한 필드만 전달하는 데 참고할 수 있다. 영어 SQL 작성 보조 사례이며 원문 span·한국어 호버·축구 후보 연결의 증거는 아니다. [Uber 원문](https://www.uber.com/gb/en/blog/query-gpt/)

### 2.9 사례에서 가져올 설계와 가져올 수 없는 주장

| 가져올 패턴 | 참고 사례 | 이번에 별도로 증명할 것 |
|---|---|---|
| 읽던 구절에서 배경 정보 확인 | Washington Post | 호버·키보드·터치, 한국어 카드, 실제 DB 자료 |
| 도메인 KB로 후보 생성·문맥 판별 | BBC | 한국 별명·초성·다국어·동명이인 후보 recall |
| 후보 제안→사람 확인→사전/규칙 반영 | BBC·NYT | 서비스 공통 재사용·거부·수정·취소·충돌·감사 |
| 공통 ID와 과거 관계 | Guardian·FT | 시즌·대회·당시 소속·경기 날짜 및 자료 시점 |
| 용어·조회 범위·관련 스키마를 좁힘 | 티오더·Uber | 최근 경기/출전 기준, 집계 정확성, 이력 조회 |

어느 한 사례도 이번 47개 시나리오를 통째로 입증하지 않는다. 공개 구조를 조합한 후보 설계를 동일 평가셋으로 비교해야 한다.

## 3. 개체 연결 알고리즘·공식 구현 6개

개체 연결(EL)은 원문의 특정 표현을 KB의 특정 ID로 연결하는 작업이다. KB는 대상의 이름·ID·설명·관계 등을 정리한 지식베이스다. 이미 주어진 mention을 판별하는 ED 점수와, mention 위치부터 찾는 end-to-end EL 점수를 구분한다. NIL은 적절한 KB 연결 대상이 없다고 판별하는 결과이며 처리 오류와 구분한다.

| 방법·발표 | 실제 구현 흐름 | 자체 축구 KB에 필요한 것 | 다국어·도입 한계 |
|---|---|---|---|
| BLINK, EMNLP 2020 | bi-encoder로 문맥/개체 설명 검색 → FAISS 후보 → cross-encoder 재순위화 | stable ID·이름·설명·인덱스, 별도 mention 검출 | 공개본은 영어 Wikipedia 중심. 검색과 판별을 분리하는 설계 기준으로 유용 |
| ReFinED, NAACL Industry 2022 | mention/type 검출 → alias 후보 → type·설명·prior로 판별 | Wikidata QID·alias/type/설명 resource 변환 및 후보생성 교체·검증 필요. custom dataset 학습만으로 임의 private KB 지원이 완성되지는 않음 | 영어 학습. alias 후보에 정답이 없으면 후단도 복구 못함. 문서 내부 분할 코드 존재 |
| mGENRE, TACL 2022 | mention+문맥 → 허용 이름/언어 trie 안에서 생성 → canonical ID | 다국어 이름·alias·redirect→ID와 trie | 한국어를 포함한 다국어 연구. 공개 저장소 NC 라이선스·의존성 고려 |
| Bootleg, CIDR 2021 및 후속 코드 | alias 후보 + entity profile의 type/관계/설명 → 문맥 판별 | 자체 문자열 ID·alias/prior·type·관계 triples 지원 | 공개 pretrained는 영어. 초기 논문과 후속 bi-encoder 코드 구조를 구분 |
| BELA, 2023 | 다국어 mention 검출 → entity embedding 검색 → rejection | 자체 entity 설명·ID index 준비와 검증 | 한국어 포함 연구. 대형 공개 index·archived 상태 고려. window/중복 병합 코드 존재 |
| MHEL-LLaMo, EACL 2026 | BELA 후보 → 쉬운/어려운 경우 분기 → 어려운 경우 LLM의 NIL/선택 | 후보 검색·점수/분기·LLM 판별 및 자체 정답 | 역사 문서·유럽 6언어 평가. 한국 커뮤니티 품질 근거는 아니지만 혼합 방식의 직접 구현 사례 |

원문 및 공식 구현:

- BLINK: [논문](https://aclanthology.org/2020.emnlp-main.519/), [코드](https://github.com/facebookresearch/BLINK)
- ReFinED: [논문](https://aclanthology.org/2022.naacl-industry.24/), [코드](https://github.com/amazon-science/ReFinED), [custom 학습 안내](https://github.com/amazon-science/ReFinED/blob/main/FINE_TUNING.md)
- mGENRE: [논문](https://aclanthology.org/2022.tacl-1.16/), [코드·라이선스](https://github.com/facebookresearch/GENRE)
- Bootleg: [논문](https://arxiv.org/abs/2010.10363), [코드](https://github.com/HazyResearch/bootleg), [자체 entity profile](https://github.com/HazyResearch/bootleg/blob/master/docs/source/gettingstarted/entity_profile.rst)
- BELA: [논문](https://arxiv.org/abs/2306.08896), [코드](https://github.com/facebookresearch/BELA), [window·전역 offset 복원](https://github.com/facebookresearch/BELA/blob/main/bela/utils/prediction_utils.py)
- MHEL-LLaMo: [논문](https://aclanthology.org/2026.eacl-long.184/), [코드](https://github.com/sntcristian/MHEL-LLAMO)

### 3.1 긴 문서·한국어를 지원한다는 말의 경계

- BELA에는 254-token window·겹침·전역 offset 복원·중복 병합 코드가 있고 ReFinED에도 기본 510-token 내부 분할이 있다. 따라서 모두 긴 문서 미지원이라고 설명하면 부정확하다.
- 이 window는 5만 자 한국 커뮤니티 전체의 지시어·다수 언급 품질이나 Vue의 UTF-16 위치 계약을 보장하지 않는다.
- 다국어 encoder가 한국어를 표현해도 ‘흥민이’·초성·새 별명에 대한 정답 후보가 없으면 링크를 못 찾는다. 한국어 표현 능력, KB 보유, 후보 recall, 문맥 판별을 나눠 평가해야 한다.
- 선수 ID를 찾는 것과 ‘지난 더비에서 두 골’을 특정 경기·기간·지표에 연결하는 것은 다른 단계다.

### 3.2 유지보수·라이선스 관찰

조사 시점 공식 저장소에서 BLINK·GENRE·BELA는 archived였다. ReFinED와 Bootleg은 archived는 아니지만 이것이 활발한 유지보수를 뜻하지는 않는다. 코드 선언은 BLINK/BELA MIT, ReFinED/Bootleg Apache-2.0, GENRE CC-BY-NC 4.0이다. 모델 weight와 원천 corpus·KB 데이터 조건은 별도로 확인해야 한다. 따라서 논문 점수만으로 이들을 운영 핵심 의존성으로 확정하지 않는다.

## 4. 사람의 교정을 재사용하는 구현 경로 5개

| 구현 경로 | 입력→검토→저장→다음 결과 | 제공하지 않는 것/추가 작업 | 적합한 도입 조건 |
|---|---|---|---|
| Label Studio | 모델 prediction → 사람 annotation → webhook/ML backend `fit()` → 규칙 DB 또는 학습데이터 | 저장 자체가 재학습/다음 검색 적용은 아님. CE의 권한·이력·검토 기능 범위와 서비스 요구 차이 확인 | 독립 정답·표본 검토 작업량이 커질 때 |
| Prodigy | Python recipe 후보 → accept/reject/수정 → dataset → callback 또는 batch train | 서비스의 동시 수정/공통 판단 권한을 대신하지 않음. 공개 서비스 접근 조건 별도 확인 | 내부 큐레이션·능동학습 실험 |
| Microsoft GraphRAG | 문서 → entity/relation → community/report·embedding → 검색 | 오판 정정/취소가 모든 파생 요약에 반영되도록 의존성 추적·재생성 필요 | 문서 집합 전체 주제·관계 질문이 핵심일 때 |
| Graphiti/Zep | 출처 episode → 시간이 있는 fact → 충돌·무효화 → 검색 | 자동 추출/무효화가 사람 승인과 같지 않음. canonical ID·거부·권한·감사·한국어 검증 필요 | 여러 출처의 변화하는 관계를 다단계 탐색할 때 |
| LangGraph | 후보 생성 → interrupt → 사람 입력 → checkpoint 재개 → 앱 DB 반영 | checkpoint가 다른 사용자의 공통 지식은 아님. 저장/재사용·충돌·멱등성 별도 구현 | 긴 검토 대기·복구·분기가 실제로 복잡할 때 |

**Label Studio:** prediction과 annotation, 모델 버전을 구분한다. 선택적 `fit()`을 직접 구현해야 모델 갱신 또는 다른 저장 경로와 연결된다. CE는 Apache-2.0이지만 공식 비교표의 RBAC·annotation history·activity log 등은 CE에 포함되지 않아 공통 판단의 서버 권한·감사를 별도로 설계해야 한다. [prediction](https://labelstud.io/guide/predictions), [ML backend](https://labelstud.io/guide/ml_create), [기능 비교](https://labelstud.io/guide/label_studio_compare)

**Prodigy:** 저장과 `update` callback/별도 학습을 구분한다. review는 주석자 간 결과를 정리하는 기능이며 DB 동시 수정 제어를 대신하지 않는다. 상용 약관에서 외부 공개·재배포 사용 조건을 확인해야 하므로 내부 데이터 작업 도구로 먼저 검토한다. [데이터 흐름](https://prodi.gy/docs), [review](https://prodi.gy/docs/review), [약관](https://prodi.gy/docs/terms)

**GraphRAG:** 현재 공식 README는 주로 유지보수 단계임을 명시한다. 기본 산출물은 Parquet/설정한 vector store여서 graph DB가 반드시 필요한 제품은 아니다. 확인한 incremental entity 병합은 `title` 기반이며 축구 canonical ID·동명이인·취소 전파를 자동 보장하지 않는다. [README](https://github.com/microsoft/graphrag), [index 구조](https://microsoft.github.io/graphrag/index/overview/), [갱신 코드](https://github.com/microsoft/graphrag/blob/main/packages/graphrag/graphrag/index/update/entities.py)

**Graphiti/Zep:** 기록 시점과 사실의 유효 시점, 출처 episode를 구분하는 설계가 유용하다. 그러나 같은 선수의 다른 시즌·루머를 사실 충돌로 잘못 무효화할 수 있어 자동 추론과 사람 확인을 구분해야 한다. 별도 graph 저장소와 색인·요약 갱신 부담이 있다. 공급자 논문은 대화 기억 평가이며 한국어 축구 품질·정정 충돌의 증거가 아니다. [Graphiti 코드](https://github.com/getzep/graphiti), [edge 모델](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py), [원문 논문](https://arxiv.org/abs/2501.13956), [Zep 언어 관련 FAQ](https://help.getzep.com/faq)

**LangGraph:** thread별 checkpoint와 thread 간 store를 구분한다. interrupt 후 node가 처음부터 다시 실행될 수 있으므로 쓰기는 멱등성 키·트랜잭션과 함께 분리해야 한다. Postgres checkpointer를 쓸 수 있어 별도 DB 제품이 항상 필요한 것은 아니다. [interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts), [checkpointer](https://docs.langchain.com/oss/python/langgraph/checkpointers), [store](https://docs.langchain.com/oss/python/langgraph/stores)

### 4.1 이번 기능의 공통 구현 조건

사람이 고친 판단은 다음 분석의 **후보 생성·제외·순위·판별 입력**에서 실제로 조회되어야 한다. 적용한 판단 ID와 지식 버전을 결과에서 추적해야 효과를 확인할 수 있다.

별명 사전, 해당 문서만의 지시어 교정, 경기 선택, 기록 용어의 의미, 명시적 거부를 같은 전역 문자열 치환으로 처리하지 않는다. 시점·팀·대회·언어·근거와 적용 범위를 기록한다. 활성 판단과 변경 사건을 같은 트랜잭션으로 관리하고 수정·취소 후 이전 판단이 다시 사용되지 않게 한다. 이는 위 도구를 도입해도 필요한 프로젝트 설계다.

기존 SQLAlchemy 버전 제어는 활용할 수 있지만 `version_id_col`은 ORM flush 단위이며 bulk update/delete까지 자동 보호하지 않는다. 기존 서비스의 `expected_version`/409 패턴과 실제 저장 경로를 함께 검증해야 한다. [SQLAlchemy 공식 안내](https://docs.sqlalchemy.org/en/20/orm/versioning.html)

## 5. 원문 위치·다국어 검색·LLM·평가 기술의 구현 근거

### 5.1 원문 위치와 호버

W3C Web Annotation은 정확한 인용문과 앞뒤 문맥을 가진 TextQuoteSelector, 위치를 가진 TextPositionSelector, 원본 상태를 정의한다. Unicode code point와 양방향 텍스트의 논리 순서도 명시한다. 동일 문자열이 반복될 수 있으므로 문서 버전·위치·인용문을 함께 대조하는 근거가 된다. [표준](https://www.w3.org/TR/annotation-model/)

Hypothesis의 2013 구현 글은 XPath만 쓸 때 문서 구조 변경에 약했던 문제와 인용문·앞뒤 문맥을 함께 쓰는 anchoring을 설명한다. 우리 서비스는 현재 입력 스냅샷이므로 fuzzy match로 다른 위치에 자동 연결하기보다 정확히 일치하는 구간을 우선 검증해야 한다. [제작자 구현 설명](https://web.hypothes.is/blog/fuzzy-anchoring/)

Vue 3.5.13은 Floating UI Vue의 현재 최소 버전 조건에 맞는다. 이 라이브러리는 위치·경계·스크롤 대응을 도우며 후보 선택 카드의 키보드/포커스/터치 동작 전체를 보장하지 않는다. 해당 동작은 별도 구현·브라우저 검증한다. [공식 Vue 사용법](https://floating-ui.com/docs/vue)

### 5.2 Postgres 안의 후보 검색

- `pg_trgm`: 철자·표면형 유사도와 인덱스. 이름/alias 근사 후보에 적합하지만 의미·문맥·초성 해석 자체가 아니다. [공식 문서](https://www.postgresql.org/docs/17/pgtrgm.html)
- PGroonga: 다국어 텍스트 검색 확장. 한국어 등 비영어 텍스트 검색을 비교할 후보이지만 정답 개체·역사 관계 판별을 대신하지 않는다. 언어별 tokenization과 실제 alias 검색 recall을 측정해야 한다. [Supabase 안내](https://supabase.com/docs/guides/database/extensions/pgroonga)
- `pgvector`: 다국어 설명·문맥의 의미 후보 검색을 같은 DB에 결합할 수 있다. Supabase의 hybrid 예시는 `tsvector`와 vector 결과를 RRF로 합친다. 예시의 `english` 사전을 다국어 요구에 그대로 쓰지 않는다. [hybrid 검색](https://supabase.com/docs/guides/ai/hybrid-search)

**현재 환경의 실제 관찰:** Postgres 17.6/UTF8이며 `pg_trgm` 1.6, `vector` 0.8.0, PGroonga 3.2.5가 `pg_available_extensions`에 있다. 세 확장은 모두 `installed_version=NULL`이다. 제공 가능 목록 확인이며 설치·권한·성능 보장은 아니다. 확장 설치는 수행하지 않았다. 원본 근거는 외부 입력 보관소의 `db-search-capabilities-v1.json`이다.

### 5.3 임베딩 후보

| 후보 | 공개 지원/구현 | 선택 전 확인할 것 |
|---|---|---|
| Vertex `gemini-embedding-001` 등 관리형 다국어 임베딩 | 기존 Google 인증 경로와 연결. 모델별 입력 token·출력 차원·task type을 확인 | 전체 5만 자를 한 벡터로 넣지 않음. 대상 설명·선택 문맥 단위. auto truncation 방지·호출 비용·alias recall 측정 |
| BGE-M3 자체 호스팅 | 공식 card: 1024차원, 8192 sequence, dense/sparse/multi-vector, 다국어 | 모델 프로세스·메모리·추론 속도·배포 비용. 언어 지원이 축구 별명 품질은 아님 |
| 임베딩 없이 이름/alias 검색+LLM 판별 | 운영 구성요소가 적고 정식명·확정 별칭에 직접적 | 다른 언어·낯선 표현의 후보 누락을 동일 정답셋에서 비교. 기능 범위를 줄인 비교안이 아님 |

[Vertex 공식 embedding 안내](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/embeddings/get-text-embeddings), [BGE-M3 공식 model card](https://huggingface.co/BAAI/bge-m3)

현재 pgvector 문서에서 일반 `vector` HNSW index는 2,000차원, `halfvec`은 4,000차원까지다. 따라서 기본 3,072차원 embedding을 단순히 일반 HNSW에 넣는 설계를 피하고 차원 축소·정규화·halfvec 또는 소규모 exact 검색을 비교해야 한다. 이 수치는 출력 차원·저장 타입·인덱스의 관계이며 프로젝트 최적 차원이라는 뜻은 아니다. [공식 pgvector](https://github.com/pgvector/pgvector)

### 5.4 LLM과 5만 자 처리

현재 뉴스 어댑터의 `gemini-3.5-flash`는 공식적으로 structured output/function calling을 지원하며 1,048,576 context·65,536 최대 출력 token을 안내한다. 현재 코드의 4,096 출력 설정은 이 모델 전체의 상한과 다르다. 다만 문서상 한도나 출력 예산 확대만으로 모든 구절의 정확한 처리를 증명할 수 없다. [모델 문서](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash)

structured output은 JSON 구조를 제한한다. ID·문맥·날짜·기록의 사실성은 서버와 DB가 대조해야 하며, 복잡한 schema는 별도 제한이 있다. token/finish reason·검증 실패를 명시하고 `MAX_TOKENS` 결과를 성공으로 병합하지 않는다. [공식 structured output](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output)

비교할 처리법은 **전체 글 단일 호출**과 **문서 공통 문맥+문단별 제한된 호출+전역 구간 병합**이다. 후자는 경계의 지시어·대명사·중복 처리 실패를 추가 검증해야 한다. 앞/중간/끝·다수 언급·언어별 token 수를 고정한 5만 자 평가가 필요하다. Lost in the Middle은 긴 context를 쓸 수 있음과 필요한 위치의 정보를 활용함이 다름을 보여준 과거 연구이며, 현재 Gemini가 같은 수준의 오류를 낸다는 직접 증거는 아니다. [TACL 원문](https://aclanthology.org/2024.tacl-1.9/)

### 5.5 평가·관측

| 후보 | 제공 기능 | 도입 경계 |
|---|---|---|
| pytest/Playwright + 고정 JSONL/정답 | SQL·ID·span·권한·피드백·브라우저의 결정론적 검사, 기존 환경과 연결 | 실제 모델 실행 결과와 대역을 분리하고 직접 지표/보고 작성 |
| Promptfoo | 여러 prompt/provider·반복 실행·JSON/custom assertion 비교 | UI·DB·피드백 전 과정을 자동으로 대신하지 않음. 대상 호출 경로와 실제 증거 연결 필요 |
| Langfuse | 버전 있는 dataset·experiment·trace·human score/annotation queue | 점수 저장과 서비스 판단 지식은 별개. self-host는 추가 인프라 부담. 원문 전문 자동 수집을 막을 설정 필요 |
| Phoenix | trace·dataset·experiment·평가 관측 | 별도 서비스/계측 검토. 도입 자체가 제품 기능의 완료를 보장하지 않음 |

[Promptfoo assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/), [Langfuse datasets](https://langfuse.com/docs/evaluation/experiments/datasets), [Langfuse 구조](https://langfuse.com/handbook/product-engineering/architecture), [Phoenix datasets](https://arize.com/docs/phoenix/learn/datasets-and-experiments/datasets-concepts)

## 6. 조사로 좁힌 기술 선택 방향

현재 근거로 우선 비교할 것은 **기존 Postgres 축구 KB의 후보 검색 + LLM의 문맥 판별 + 서버의 기록 조회 + 버전 있는 공통 판단 지식베이스**다. 전용 EL·graph memory·workflow는 해결하는 문제와 운영 비용을 따로 비교한다.

이 결론은 라이브러리 수를 줄이기 위해 요구를 줄인 안이 아니다. 세 후보 아키텍처 모두 다국어·5만 자·한국어 호버·문맥 자료·사람 교정·공통 재사용·취소·감사를 동일하게 평가해야 한다. 구체적인 비교안과 채택 조건은 [기술 선택 메모](technology-options-v1.md)에 정리했다.

실제 프로젝트의 후보 recall·연결 정확도·5만 자 시간·비용·피드백 개선 효과는 아직 측정하지 않았다. 공개 사례·연구·도구 기능과 프로젝트 성능을 구분한다.

종합 문서의 독립 읽기 전용 검토에서 전용 EL과 그래프의 선택 축 분리, 모든 비교안의 공통 교정 요구, 영어/다국어 공개 모델 구분, ReFinED private KB 전환 부담 4건을 보완했다. 이 검토는 조사 문서에 대한 검토이며 제품 동작·프로젝트 성능의 검증 판정이 아니다.
