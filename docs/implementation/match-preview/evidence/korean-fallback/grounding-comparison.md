# 성공/본문 미생성 응답 grounding_metadata 비교

저장된 SDK 응답의 candidates[0].grounding_metadata만 추출했다. 값과 필드는 그대로이며 JSON 파일에는 들여쓰기만 적용했다. 최신 실행은 HTTP 호출/저장은 성공했지만 검증 후 본문이 생성되지 않은 사례다.

| 항목 | 이전 성공 6176a8c6 | 최신 본문 미생성 22e1a19e |
|---|---|---|
| web_search_queries | 14개 | 8개 |
| grounding_chunks | 8개 | 필드 없음 |
| grounding_supports | 9개 | 필드 없음 |
| search_entry_point.rendered_content | 있음 | 있음 |
| retrieval_metadata | 필드 없음 | 빈 객체 {} |

## 원문 파일

- [이전 성공 metadata 원문](successful-grounding-metadata.json)
- [최신 metadata 원문](no-body-grounding-metadata.json)

## 이전 성공의 출처 목록

- [0] plstats.uk — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHXooPbQJUqz6WpyDk89tY3c4zKYCbkVYP90-bibzZ2CbJNHjIltN2Zo1_1jegURJ7jXjIwQE3LSEccSY0S-jeoto27vvfzzlIHuDsJ5vHG0h-XzEf3KJTFRHdRMR5QAgko3X3N
- [1] theguardian.com — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG4Cn2GkY4-v-xku29pjvjHZEugvyg-ECRyW-yXRmee5JOP0G1OawZgEDhVt_5bpq20E5rd5H7AC6I8SMRIYUQ7R_btl9nPebffe8wPrEKKL2ahtf1WxdToHNn2N4uBksLUaZqv3lrmGwSLX4t1bCKhoTq5QoMZwRWT7zHWlUNe7Eah234vJVk7tMuSORX1KbmODDYqlO-tDndvVKNjUmblLVx1
- [2] wikipedia.org — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE6xKuFVuMdNU2z2GSYevkJCxBPzx5LDHPLiZCZq8FOe_N86wNF0YdtYijZJvEmn9qqANEaTWZRDc-b2FZCOdfxY9bqP3CQVgjx0yUNt00JCTTAA6JTGpExQPWfD7dQOkTfQA==
- [3] skysports.com — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFGbAo--6_ifvmd094cR_GzpUE0hsYlCNpRsoFKMRtPsVLSSlPrsVH470ImJZRturKPltO7b6C1c2-Xd3URiGesOy_fVcU0unzbfqIK8dYwY8OjE8NCONEHNo2UyX0lExjcrkKLnXetU_ONsfm0lrJp00MkZLRjAthJAbbvXEaGBG_A-rc_7DsOFeWBil9Gf8PV-suAyV6mBu_WJykLj2V2D87RsYnKr_7gQv7W8ThkMIysn2av
- [4] theguardian.com — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF2CRngRhnmH9zI-C6euaxRYGvc1WbMdZuc-S_xUOEStUgLgLeARfHQCb9YhEhfYfa18nPT1MRBFv6V6_TY6LjrsdfZrE_MohlkxSqfjPB2yU-TjO_kO00uuhpTcqYf2OsVcB-ZD6tXwpucY9qBJ980_SJihsaHyFcMT_QPlMT3Xbn1Ru9yuhhw4IwERPGlTpg9oB4NDLU=
- [5] wikipedia.org — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFaJtAWXBEq4-h2pnGzSE_GrwW20C9zqDwoR7NJ4QHLhOPy3Lu_5M4vTaMGpoXC28cCYVj4rf9wP9-CLozRRS6Hy6V8gtxJ9SXAKGu3ElEirVv5yhlS_IOC8q9RJfMmDlw6rZk=
- [6] thescore.com — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGNpj0KEYQ_bkPdCAOAJIJtB7ywftl9coplgj8jUaqLOmDDQfcmVdwqaFiCVjZ43ivHsv3ocE0U_r4pTw4CjDHy8LDzFQiPdlonO0T_WHZkvLWo8GXChskllLh49b-vQ-EoD3DKVB9qOgq0XxWzS-vYDhbAB4yDbQpZiXk7b_3JCUzIIzRB5EY0vWK_2krYIqnlXfCPrXcegD0=
- [7] manchestereveningnews.co.uk — https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHq4kLZpF0MBs7aVMhtF076v3E4csJlchy9cjy_ZNjCFzHB-4Sr8SOslwZ_9Vz6WvBXQ6TUBMWbFJItNARoXlXNdOyjaJ_IrhBylcfI-m-SX0VPe9cJ-8ey-BfZwd4ya_z2HfZ2yiqOGVU8ivEwBT8buavhHOwYakYRdewBz2XsVBb1jyBlSQ_7_wHADUftQzV5sPMNRN4h9qycPXYkok9w

## 이전 성공의 문장-출처 연결 원문 예시

```json
[
  {
    "grounding_chunk_indices": [
      0
    ],
    "segment": {
      "end_index": 287,
      "start_index": 131,
      "text": "\"selection_reason\": \"이번 시즌 리그 10경기에서 9골을 기록하며 득점 선두를 달리고 있는 Manchester City의 핵심 공격수입니다"
    }
  },
  {
    "grounding_chunk_indices": [
      1
    ],
    "segment": {
      "end_index": 420,
      "start_index": 289,
      "text": "최근 RB Leipzig와의 Champions League 경기에서도 결승골을 터뜨리며 뛰어난 결정력을 유지하고 있습니다"
    }
  }
]
```

grounding_chunk_indices는 위 grounding_chunks 배열의 인덱스를 참조한다. 이 예시는 index 0이 포함된 첫 문장, index 1이 포함된 둘째 문장의 연결을 보여준다. 전체 9개 연결은 원문 JSON에 그대로 있다.

## 검색 질의 원문

### 이전 성공

- "Manchester City" "Fulham" 2026
- Manchester City Premier League November 2026
- Fulham Premier League November 2026
- Manchester City squad 2026 2027
- "Erling Haaland" goals 2026 2027
- "Erling Haaland" Manchester City 2026
- Fulham top scorer 2026 2027
- Fulham squad 2026 2027
- "Oscar Bobb" Fulham 2026
- "Oscar Bobb" transfer Fulham
- "Enzo Fernandez" "Manchester City" 2026
- "Phil Foden" Manchester City 2026
- "Abdukodir Khusanov" Manchester City 2026
- "Elliot Anderson" Manchester City 2026

### 최신 본문 미생성

- Manchester City vs Fulham 2026-11-21
- Manchester City vs Fulham November 2026
- Manchester City squad news November 2026
- Fulham squad news November 2026
- "Erling Haaland" 2026/27 stats
- "Rayan Cherki" Manchester City 2026/27
- "Josh King" Fulham 2026/27
- Manchester City vs Fulham 2026-11-21 preview

## 해석 범위

두 실행 모두 검색 질의와 search_entry_point를 반환했다. 이전 실행은 출처 URL과 문장 연결도 반환했고 최신은 두 필드 자체를 반환하지 않았다. 최신 모델 본문의 players[].evidence URL은 이 메타데이터 밖에 있으며, 그 URL이 이 출처 목록에 들어 있다는 뜻은 아니다.

이 비교는 필드 차이를 확인한다. API가 왜 해당 실행에서 출처 필드를 생략했는지나 기사 내용의 참/거짓을 증명하지 않는다. 프롬프트·출력 계약과 결과가 서로 달라 메타데이터 생략 원인의 통제 비교가 아니다.
