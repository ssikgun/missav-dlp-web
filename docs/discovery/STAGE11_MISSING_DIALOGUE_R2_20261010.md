# Stage11 — 일본어 누락 대사 탐지 R2

상태: **사용자 판정 14개 기록 완료 / 신규 청취 후보 2개 / 원음 대사 여부 UNVERIFIED / 신규 모델 호출 0회**. 기존 canonical handoff 경로 `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`와 저장소 `tools/`, `docs/discovery/` 구조를 확인하고 재사용했다.

## 사용자 원음 판정 기록

기존 judgment.tsv의 22개 열 이름·순서·행 ID를 유지했다. 사용자 판정은 reviewer=USER 및 verdict에 아래 유형으로 기록했다. 신음/음악/무대사는 dialogue_presence=NO, Japanese_dialogue=NO이다. 판정하지 않은 효과음 등 다른 소리 종류는 NOT_ASSESSED로 남겼다. 기존 Whisper·JA·Reazon reference/미실행 표시·시각·WAV 경로·RMS 값은 수정하지 않았다.

| 대상 | 사용자 직접 청취 판정 | 수 |
|---|---|---:|
| Missing 01–10 | NON_SPEECH_MOAN | 10 |
| Control 01–02 | MUSIC | 2 |
| Control 03 | NO_DIALOGUE | 1 |
| Control 04 | NON_SPEECH_MOAN | 1 |

원본 표·원본 SHA 목록은 `/var/tmp/stage11-whisper-missing-probes-20261010/user-r2-evidence/`에 그대로 보존했다. 최신 사용자 판정 sidecar는 `/var/tmp/stage11-whisper-missing-probes-20261010/user-judgments-r2.json`, 호환 표는 `/var/tmp/stage11-whisper-missing-probes-20261010/judgment.tsv`이다. 원본 TSV SHA: `24e0f46007fe67ac0a99a55e0afd6f434d1b3919d7801b1000eb11226315a8a2`. 변경 TSV SHA: `a15d92ad330a0d252f9a296f9fbcbbf715a29fac681b052878c13bb41506344b`. 기존 전체 manifest에 있던 파일 중 내용 변경은 judgment.tsv 1개뿐이며, SHA 목록은 원래 목록을 보존한 후 새 사용자 자료를 포함하도록 갱신했다. 모든 STT 원본/기존 audit는 역사적 모델 증거로 그대로 남겼다.

신음은 음향 활동은 있으나 언어 대사가 없는 사례로 기록했다. 판정 범위는 사용자가 청취한 각 본문 클립이며 앞뒤 구간에 자동 확대하지 않았다. 판정 ID·시각은 입력 데이터로 읽으며 특정 작품/품번/문구/시각을 도구의 선택 규칙에 하드코딩하지 않았다.

## R2 후보 선정

기존 전체 524개 Whisper 완료 결과/2,521 raw 관측과 기존 affine 정렬 JA 313개를 재사용했다. 모든 Whisper 문맥·충돌 대안도 공백 계산에서 유지했다. 시작 모집단은 Whisper 출력과 JA가 모두 없는 기존 755개 공백이다. 이 중 1–8.5초 전체 공백을 조사했다. 기존 baseline Whisper, 역사적 긴 Whisper 후보 전체, 현재/과거 충돌 group envelope, 이전 Reazon 검증 clip, 알려진 양성 scope, 이번에 판정한 음성 본문과 겹치면 **공백 전체를 보류**하여 기존 대사를 잘라 새 대사로 만들지 않았다. 신음 판정 주변을 통째로 삭제하지 않았으며 원본 후보와 결과는 삭제하지 않았다.

문맥 조건은 ① 양쪽 기존 JA가 6초 이내, ② 과거 사용자 확인 대사 scope가 4초 이내, 또는 ③ 한쪽 기존 JA가 4초 이내이면서 앞뒤 Whisper 출력이 공백에서 각각 1초 이내인 경우이다. 이 조건을 만족하는 전체 공백은 16개였다. 인접 JA/Whisper는 확인된 정답 문장으로 승격하지 않았으며 이번 선정 후보는 ③에 해당한다. 사용자 확인 과거 양성 scope 근접 조건으로 선정된 후보는 없고, 그 scope들은 대조군으로만 활용한다.

음향 비교는 음량 순위가 아닌 음량 정규화 후의 25ms frame/10ms hop 스펙트럼·리듬 특징이다. 6개 주파수 대역의 상대 분포 변화(flux), envelope 2–8Hz 변동 비율, envelope 교차 리듬, spectral entropy와 band motion을 3개 양성/14개 음성 사례와 비교했다. 표준화한 특징 거리가 가장 가까운 음성 사례보다 양성 사례에 더 가까운 경우만 우선 검토했다. RMS는 −60dBFS 미만 비교 불가 신호를 보류하는 데만 쓰며 순위/거리 계산에는 들어가지 않는다. **이 거리는 일본어 발화의 확률·언어 탐지 모델·성능 검증 결과가 아니다.** 작은 비무작위·상호 의존 표본과 넓은 양성 scope 때문에 다른 종류의 소리도 통과할 수 있다.

16개 중 음향 비교 조건을 통과한 것은 3개였다. 앞뒤 Whisper 문장이 동일한 1개는 기존 발화의 반복/연장 여부를 먼저 검토해야 하므로 이번 신규 청취 후보에서 보류했다. 남은 **2개만** 준비했으며 8개를 채우지 않았다. 전체 screening/context pool/보류 사유는 selection-audit.json에 남겼다. 발화 끊김 단서로 원래 요청 경계 근접 여부도 기록했으나 선정 2개에는 해당하지 않았다.

| 후보 | 원본 본문 시작 | 종료 | 길이 | 문맥에서 본문 위치 | 인접 JA 거리(앞/뒤) | 음향 패턴 거리(양성/음성) |
|---|---|---|---:|---|---|---|
| candidate-01 | 01:53:51.500 | 01:53:52.920 | 1.42s | 5.00–6.42s | 1189 / 7041ms | 0.719 / 1.167 |
| candidate-02 | 01:57:27.220 | 01:57:30.740 | 3.52s | 5.00–8.52s | 60293 / 3431ms | 0.416 / 0.822 |

본문은 공백 양끝에서 200ms를 띄웠고 문맥 WAV에는 앞뒤 각각 5초를 붙였다. 추정 경계 오차로 기존 발화가 실제로 본문까지 이어질 가능성은 남아 있다. 기존 대사의 연장이라면 EXISTING_UTTERANCE_CONTINUATION으로 표시하고 새 독립 대사로 집계하지 않는다. 후보 존재/일본어 정확도/실제 시각은 모두 UNVERIFIED다.

candidate-01: ja-000240 종료 뒤 1,189ms부터 시작하는 원래 공백이며 앞뒤 Whisper 대화 관측 사이에 있다. 인접 뒤 Whisper에 CROSS_CHUNK_READING_CONFLICT 경고가 있어 문맥의 문장 정확도 역시 미확정임을 화면에 명시했다. 본문은 그 기존 충돌 group과 겹치지 않는다.

candidate-02: ja-000247 시작 3,431ms 전까지 이어지는 원래 공백이며 앞뒤 서로 다른 Whisper 대화 관측 사이에 있다. 인접 앞 JA는 약 60초 떨어져 있어 양쪽 JA 대화가 확인된 구간으로 표현하지 않는다. 두 후보의 앞뒤 Whisper 및 JA 원본 ID·시각·경고, source sample 범위, 음향 특징·한계·중복 정보는 review-manifest.json에 보존했다.

두 본문의 Whisper/JA/baseline/과거 긴 후보/현재·과거 충돌 중첩은 0이다. 문맥에 포함된 기존 후보 ID는 별도 필드에 기록했다. 문맥에 들리는 기존 대사는 새 누락 대사로 집계하지 않는다. 확인된 새 누락 대사 수는 현재 0이다.

## 양성·음성 대조군

양성은 역사적으로 SHA가 고정된 입력의 presence_human_confirmed=true 범위 3개다. **클립 안 대사 존재를 확인한 scope**이며 정확한 일본어 청취문/모든 frame의 대사 존재/단일 독립 발화 수를 확정한 자료가 아니다.

| 양성 대조군 | 원본 범위 | 확인 범위 |
|---|---|---|
| positive-01 | 00:01:04.000–00:01:10.000 | 과거 사용자 대사 존재 확인 / 일본어 문장 정확도 미확정 |
| positive-02 | 00:03:28.000–00:03:50.000 | 과거 사용자 대사 존재 확인 / 일본어 문장 정확도 미확정 |
| positive-03 | 00:55:56.000–00:56:07.000 | 과거 사용자 대사 존재 확인 / 일본어 문장 정확도 미확정 |

음성 대조군은 이번 사용자 판정 **신음 11개, 음악 2개, 무대사 1개** 전부다. R1 본문 WAV를 byte-identical 복사했다. 대조군은 탐지 방식 점검용이며 신규 누락 대사로 세지 않는다. 문맥 밖 소리 유형에는 기존 판정을 확대하지 않는다.

## 맥북 청취 파일

전체 디렉터리: `/var/tmp/stage11-missing-dialogue-r2-20261010/`
다운로드 압축: `/var/tmp/stage11-missing-dialogue-r2-20261010.tar.gz`
- `listen.html`: 후보 2개·대조군 17개, 본문/문맥 WAV 재생, 문맥 본문 위치 표시와 본문만 재생 버튼, 후보 판정 입력 및 TSV 저장.
- `clips/`: 각 본문 WAV. `contexts/`: 앞뒤 5초 문맥 WAV. 총 38개 WAV.
- `judgment.tsv`: 상대 WAV 경로와 원본 시각/문맥 본문 위치/사용자 판정 입력 열. 새 Reazon은 NOT_EXECUTED.
- `review-manifest.json`, `selection-audit.json`, `audit.json`, `offline-verification.json`, `user-judgments-r1.json`, `user-feedback.json`, `protected-input-pins.json`, `SHA256SUMS`: 출처·보류 이유·판정 구분·SHA 증거.

압축을 풀고 `listen.html`을 Safari/Chrome에서 열면 된다. WAV 경로와 TSV 데이터는 상대 경로/화면 내 데이터로 제공하여 file://에서 fetch/CORS/서버 없이 동작하도록 만들었다. 화면에 Reazon 추정 문장을 노출하지 않으며 신규 Reazon 자체도 실행하지 않았다.

다음 사용자 작업: 후보 본문 → 문맥 → 본문 순으로 듣고 대사 존재/일본어 여부/신음·호흡/음악/효과음을 각각 표시한다. 일본어가 들리면 직접 들리는 문장과 실제 원본 시각을 적는다. 기존 발화 연장이나 불분명한 소리이면 해당 판정을 유지한다. **판정 TSV 저장** 버튼으로 judgment.user.tsv를 저장해 전달한다. 양성·음성 대조군은 새 대사 후보로 세지 않는다.

## 보존·검증

보호 입력 2,152개 SHA를 전후 검증했다. 원본 TSV 열 유지, 모델 reference 열 동일, 원본 표/manifest SHA 보존, 사용자 import 재실행 무변경, canonical affine JA 재투영, 기존 validator/materializer의 JA 313/KO 296/17 absorption 및 SRT byte 일치, 본문/문맥 exact PCM, 문맥 본문 subset byte 일치, 음성 WAV byte 복사, 선택 본문의 기존 대사/후보/충돌 중첩 0, 음량 변화에도 리듬·스펙트럼 특징 유지, 상대 WAV·내장 TSV 경로와 압축 추출 SHA를 확인했다. 브라우저 검증은 정적 자산/스크립트 구조 검증이며 맥북 실제 청취·브라우저 실행 검증은 사용자 단계에 남아 있다.

Whisper/ReazonSpeech/Hermes/Gemini 신규 호출 0회, 기존 JA·KO·흡수 변경 0, 자동 승인/게시 0, Worker/서버 운영 설정 변경 0. 원본 PCM 음량을 조절한 데이터는 특징 불변성 검증에만 사용했으며 청취 WAV에는 어떠한 음량 조절·필터·노이즈 제거도 적용하지 않았다.

재사용 도구: `tools/stage11_prepare_missing_dialogue_r2.py` 및 기존 `tools/stage11_prepare_whisper_missing_probes.py`의 공백/PCM/SHA 함수. 사용자 판정은 입력 JSON이며 도구에는 특정 작품·품번·시각·대사 문구가 없다.
