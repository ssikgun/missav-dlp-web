# Stage11 — Whisper 미출력 구간 독립 탐지 시험 준비

상태: **입력 준비 완료 / 원음 대사 판정 대기 / 신규 추론 미실행**. 기존 12개 대사 교차검증과 별도 시험이다. 선정 10개는 확인된 누락 대사나 독립 발화 수가 아니다.

## 탐색 규모

기존 전체 Whisper 524개 완료 기록 및 원본 NPY·wire·segments·done SHA와 PCM 샘플을 재검증했다. 2,521개 raw segment의 **모든 문맥/경계/충돌 대안까지** 원본 절대 시각에서 합집합으로 처리했다. 품질 경고가 있는 출력도 제외하지 않았다. 6개 빈 응답 core 역시 처리 완료이며 미분석 구간으로 세지 않았다.

| 기준 | 연속 구간 수 | 합계 | 디코딩 원음 대비 |
|---|---:|---:|---:|
| Whisper segment 출력 없음 | 931 | 4,194.20125초 (01:09:54.20125) | 40.096% |
| Whisper 출력 없음 + 정렬된 기존 JA 없음 | 755 | 3,764.81225초 (01:02:44.81225) | 35.991% |

정렬은 기존 canonical JA 313개와 기존 affine 변환을 재사용했다. 이는 자막 시각 추정에 대한 공백이며 실제 무음·실제 누락 대사량을 뜻하지 않는다. 전체 디코딩 원음은 10,460.40125초, 요청 영상 끝은 10,460.402초이며 마지막 0.75ms는 시각 양자화 차이다. 524 core의 PCM 샘플은 빠짐없이 연속한다.

## 음성 활동 근거와 선정 기준

재사용할 수 있는 전체 VAD 발화 시각표는 확보되지 않았다. 기존 Worker의 VAD region count는 구간별 음성 존재를 증명하지 못한다. 기존 315개 진폭/flatness window JSON은 있으나 파일 내부에 원음 SHA·산출 방법이 없어 넓은 문맥 참고로만 보존했다. 이번에 새 VAD나 어떤 ASR 모델도 실행하지 않았다.

독립적으로 원음 PCM에서 **음향 활동**을 측정했다. 100ms frame의 RMS, 300–3400Hz 대역 에너지 비율/flatness, 에너지 변동을 기록했다. RMS ≥ −45dBFS이고 대역 비율 ≥ 0.15인 frame 비율을 acoustic_active_fraction으로 표기했다. 이 지표는 음악·효과음·신음·호흡도 통과하므로 음성 활동 또는 실제 일본어 대사로 확정하지 않는다.

모든 현재 Whisper 출력, 기존 JA, 과거 baseline Whisper, 과거 충돌 record, 이전 12개/13개 Reazon 검증 WAV 및 대조군 30초 WAV를 제외했다. 남은 각 공백의 양쪽에 1초를 띄우고 4–12초 원음을 추출할 수 있는 182개 공백을 확보했다. 전체 시간을 10등분하고 활동 frame 비율 ≥ 0.25인 구간 중 지표 점수가 가장 큰 1개씩을 골랐다. 점수는 active_fraction × (1−flatness) × (1+min(RMS p90−p10,20)/20)이다. 특정 작품·품번·대사·사람이 알려준 양성 시각을 선택 규칙에 사용하지 않았다. 무작위 표본으로 볼 수 없으며 전체 누락 복구율 추정에는 쓸 수 없다.

선정 10개는 현재/과거 **충돌 group 전체 review envelope와도 중첩 0**임을 별도 확인했다. 과거 긴 Whisper 분석의 비충돌 후보와 시간상 겹치는 8개는 해당 원래 candidate ID를 batch-plan.json에 보존했다. 이후 대사가 확인되더라도 과거 모든 분석에서 최초 발견된 새 대사로 중복 집계하지 않는다. 가짜 Whisper 텍스트가 실제 대사를 덮고 있는 구간은 이 공백 기반 시험으로 탐지하지 못할 수 있다.

## 선정된 시험 구간 10개

아래 WAV 전체가 청취·미래 Reazon 입력이다. 추가 문맥 대사를 덧붙이지 않았다. 음향 활동만 관측했고 대사 존재·언어·정확도·소리 종류는 모두 원음 판정 대기이다.

| ID | 원본 시작 | 원본 끝 | 길이(초) | RMS(dBFS) | 활동 frame 비율 | 과거 비충돌 후보 겹침 수 |
|---|---|---|---:|---:|---:|---:|
| missing-01 | 00:02:38.840 | 00:02:42.980 | 4.14 | -37.33 | 1.000 | 1 |
| missing-02 | 00:19:51.100 | 00:19:59.000 | 7.90 | -29.86 | 0.848 | 0 |
| missing-03 | 00:50:05.740 | 00:50:14.000 | 8.26 | -21.13 | 0.854 | 1 |
| missing-04 | 01:08:26.880 | 01:08:30.900 | 4.02 | -38.22 | 0.675 | 2 |
| missing-05 | 01:25:00.140 | 01:25:12.140 | 12.00 | -28.92 | 0.475 | 5 |
| missing-06 | 01:41:45.980 | 01:41:54.000 | 8.02 | -21.20 | 0.900 | 1 |
| missing-07 | 01:54:16.220 | 01:54:22.580 | 6.36 | -24.24 | 0.810 | 0 |
| missing-08 | 02:14:45.980 | 02:14:53.320 | 7.34 | -17.53 | 0.781 | 3 |
| missing-09 | 02:33:44.660 | 02:33:54.240 | 9.58 | -21.52 | 0.853 | 11 |
| missing-10 | 02:40:45.880 | 02:40:54.000 | 8.12 | -21.33 | 0.840 | 1 |

## 기존 무대사 대조군 4개

이전 사용자가 원음을 듣고 무대사라고 확인한 control-01~04만 재사용했다. 같은 20초 core PCM16 및 Reazon float32 입력 SHA를 그대로 유지했다. 당시 청취한 원래 30초 WAV도 byte-identical 복사했다. 음악/효과음/신음 종류는 당시 무대사 확인과 별개로 미확정이며 판정표에서 분리한다.

| ID | 기존 20초 core 시작 | 끝 | 기존 Reazon 오인식 참고 |
|---|---|---|---|
| control-01 | 00:09:20.000 | 00:09:40.000 | あれ |
| control-02 | 00:09:40.000 | 00:10:00.000 | あら |
| control-03 | 01:00:00.000 | 01:00:20.000 | うん |
| control-04 | 01:09:40.000 | 01:10:00.000 | うん |

이 대조군의 비어 있지 않은 과거 STT 출력은 false textual recognition 참고이며 새 인식 결과가 아니다. 4개 사례만으로 전체 영상 환각률을 추정하지 않는다.

## 원음과 판정 자료

- 청취 페이지: [listen.html](/var/tmp/stage11-whisper-missing-probes-20261010/listen.html)
- 원본 시각·판정표: [judgment.tsv](/var/tmp/stage11-whisper-missing-probes-20261010/judgment.tsv)
- 추론 입력·출처·전체 후보 정보: [batch-plan.json](/var/tmp/stage11-whisper-missing-probes-20261010/batch-plan.json)
- 전체 공백/선정 모집단: [gap-ledger.json](/var/tmp/stage11-whisper-missing-probes-20261010/gap-ledger.json)
- 감사 및 오프라인 검증: [audit.json](/var/tmp/stage11-whisper-missing-probes-20261010/audit.json), [offline-verification.json](/var/tmp/stage11-whisper-missing-probes-20261010/offline-verification.json)
- 원음 폴더: `/var/tmp/stage11-whisper-missing-probes-20261010/clips/` — `missing-01.wav`~`missing-10.wav`, `control-01-core20.wav`~`control-04-core20.wav`, `control-01-reference30.wav`~`control-04-reference30.wav`.

WAV는 기존 디코딩 원음의 16kHz mono PCM을 이전과 같은 PCM16 변환으로 추출했다. 음량 정규화·필터·노이즈 제거는 하지 않았다. source_pcm_sha256: `51f551a00e713c3ad4c15e15c86fca55713210d94137da4d6055c9c96db77f75`. 보호 입력 2,152개 SHA를 작업 전후 확인했다. JA 313/KO 296/흡수 17과 기존 SRT bytes를 보존했다. 원본 파일과 새 파일은 SHA256SUMS/input-pins.json으로 검증한다. WAV는 Git에 넣지 않고 CT108의 위 `/var/tmp` 폴더에 보관한다.

## 독립 ReazonSpeech 검증 준비 여부

**10+4 입력 및 기존 설치 환경에 대한 기술적 준비와 모델 로드 전 preflight는 완료했다. 실제 일본어 누락 복구 능력 평가는 원음 정답 판정과 이후 별도 Reazon 실행이 남아 있다.** 이번 작업에서 원음을 실제 청취하거나 실제 대사를 확인하지 않았으며 확인된 누락 대사 0개로 기록한다.

`judgment.tsv`에서 대사 존재, 일본어 여부, 음악, 효과음, 신음/호흡을 각각 판정한다. 새 Reazon 문장을 보기 전에 양성/음성/불확정 여부, 들리는 일본어, 실제 대사 절대 시각을 기록해 STT에 끌려가는 판정을 피한다. 여러 소리가 함께 있으면 각 항목을 함께 표시할 수 있다. 일본어 대사가 확인된 구간에서 Reazon의 추가 탐지 여부와 문장 정확도·시각을 따로 평가한다. 불명확한 소리는 AMBIGUOUS이며 모델 간 일치만으로 승인하지 않는다. 양성 원음 대사가 없으면 복구 성공률은 산출 불가이다. 알려진 무대사 대조군의 비어 있지 않은 결과는 대조군 오인식으로 기록한다.

기존 CPU fp32/1 thread/greedy-search와 앞뒤 0.9초 padding을 재사용할 미래 runner를 준비했으며 inference/token-point loop는 기존 파일과 byte 동일하다. Token point는 확인된 word/utterance boundary가 아니다. 미래 실행 결과는 새로운 `/var/tmp/stage11-reazon-missing-probes-result-*`로 분리된다. 이번에는 `--preflight`만 실행했으며 아래 명령 역시 모델을 로드하거나 추론하지 않는다.

```bash
bash /var/tmp/stage11-whisper-missing-probes-20261010/preflight.sh
```

Whisper/ReazonSpeech/Hermes/Gemini 신규 호출 0회, 설치/모델 다운로드 0회, 승인/게시 0회, 기존 자막 수정 0회. 실제 대사 존재에 대한 근거가 없는 VAD 결과를 생성하거나 확정하지 않았다.

## 검증 결과

전체 524개 NPY exact PCM/SHA, 기존 reconciliation 관측 시각 일치, canonical JA 재투영, 독립 endpoint partition의 두 공백 총량, 선정 WAV의 원본 PCM, 후보 간/Whisper/JA/현재 및 과거 충돌 group 중첩 0, 대조군 core PCM SHA 및 30초 WAV byte 동일, 3종 손상 입력이 model import 전에 차단되는 것을 확인했다. py_compile, bash -n, git diff --check 및 실제 설치된 Reazon venv의 추론 없는 preflight가 통과했다.

재현 도구: `tools/stage11_prepare_whisper_missing_probes.py --config <bundle>/preparation-config.json --output <new-directory>` (기존 numpy 환경 사용). 원래 export한 JA 시각표는 trusted seed SHA를 검증한 뒤 기존 affine projector로 다시 계산해 동일함을 확인했다. 원음 청취 판정은 이 오프라인 무결성 검증의 범위에 포함되지 않는다.
