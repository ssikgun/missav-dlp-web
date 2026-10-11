# Stage11 — clip-011 발화 경계 복구 (2026-10-12)

상태: **INCOMPLETE / AMBIGUOUS**, 검토 후보 1개. Hermes 직접 실행 **준비 PASS**, 실제 실행 0회.

사용자 청취: Core에는 `いいところ`, Context에는 `いいところだね`와 이어지는 별도 `はい`.
문맥의 일본어 읽기는 사용자 보고로 STT 가설과 일치한다. 기존 Core의 전체 문장 인식 성공이나
정확한 발화 시각이 확인된 것은 아니다. 이전 사용자 판정·원음 SHA·STT 결과는 그대로 보존했다.

| 항목 | 이전 범위(원본 영상 초) | 갱신 검토 범위(초) | 판정 |
|---|---|---|---|
| clip-011 `いいところだね` | 3355.932–3356.832 | **3355.400–3357.160** | ESTIMATED: 저장된 일치 문장 segment의 최소 시작·최대 끝 |
| 뒤따르는 `はい` | clip-012 Core 3357.732–3358.100 | **3357.540–3358.120** | ESTIMATED: 별도 발화, 문맥 증거만 보존; 신규 후보 아님 |

이 범위는 모델별 시각 차이를 포괄하는 **검토용 창**이며, 실제 발화 시작·끝의 확정값이나
통계적 신뢰구간이 아니다. 전자는 시작을 532ms 앞당기고 끝을 328ms 뒤로 넓혔다.
두 추정 범위 사이 380ms도 측정된 무음 길이가 아니다. 임의 padding은 추가하지 않았다.

## 기존 시각 증거와 Core 잘림

| 재사용한 결과 | STT 실제 입력 범위(초) | 해당 문장 segment 추정(초) |
|---|---|---|
| Whisper primary A | 3351.000–3372.000 | 3355.932–3356.832 |
| Whisper primary B | 3351.000–3372.000 | 3355.960–3356.820 |
| saved full-short core-0168 / short·AB 비교 | 3335.000–3365.000 | 3355.400–3356.840 |
| saved full-short core-0169 / short·AB 비교 | 3355.000–3385.000 | 3355.900–3356.820 |
| saved medium case-04 | 3354.400–3357.840 | 3356.000–3357.160 |
| Reazon case-04 | 3354.400–3357.840 | token 시각만 있음: 마지막 `ね` 약 3356.900; 끝 시각 없음 |

Whisper A/B는 `だね`를 기존 Core 안에 배치한다. 반면 medium의 마지막 `ね`는
3356.920–3357.160으로 추정되며, Reazon의 `ね` 점도 기존 끝보다 약 68ms 뒤다.
사용자가 Core에서 끝을 못 듣고 Context에서 들었다는 보고를 반영해 **끝 잘림을 기록**했다.
어느 모델의 단어 시각도 실제 원음 경계의 정답으로 채택하지 않았다. 잘린 정확한 음소·길이,
최초 발화 시작과 문장 끝은 수동 시각 정렬 전까지 미확정이다.

재사용 WAV: `/var/tmp/stage11-gemma3n-pilot-b-20261010/scope-pack/`의 core/context clip-011·012.
clip-011 Context는 3353.932–3358.832초로 두 검토 범위를 모두 포함한다.
core-011 SHA `5c9e63db5cb814d0268ecf936661eb42a57ca30079173a21d4a946cc218eb896`,
context-011 SHA `7147925aeac9aca78a704721fdb048ac91cdb2feb69e093188e7199d9ccc3e83` 보존.
Core가 Context의 정확한 16kHz PCM sample crop임을 다시 확인했다. 원본 영상 SHA는 기존
기록을 재사용했으며 영상 전체를 새로 hash하지 않았다. 기존 영상/음성 시계·SHA 근거는 evidence에 연결했다.

## `はい`와 기존 자막·absorption

`はい`는 사용자 문맥 청취와 기존 clip-012 결과를 연결한 별도 발화다.
Whisper 추정 A/B 3357.732–3358.092 / 3357.780–3358.100,
full-short 3357.540–3358.100 / 3357.720–3358.120. Reazon은 `い` 점 약3357.912만
유효한 시각을 제공한다(`は`는 padding 내 시각). 별도의 확정 경계로 사용하지 않았다.

현재 JA/KO 전체와 absorption 17개를 대조했다. 두 갱신 범위 모두 시간 중복 JA0/KO0,
해당 구간의 흡수된 JA0, 인접 absorption0. clip-011의 직전 자막 끝과 12.519초,
직후 시작과 4.948초 간격이 있다. `はい` 구간에는 시간상 이를 포함하는 JA·KO가 없다.

- 직전 ja-000135: 3339.493–3342.881, `えっと、ちょっとだけ。はい。じゃあ、こち らで。`
  / 현재 KO `어, 잠깐만요. 네. 그럼 이쪽에서.`
- 직후 ja-000136: 3362.108–3367.930, `あんたは黙ってなさい` / `너는 조용히 해.`

직전 자막에도 `はい`가 있지만 시간상 다른 발화이며, 단순 문자열 일치로 이번 응답이
포함되었다고 계산하지 않았다. 다른 위치의 부분 일치·독립 `はい`도 evidence에 보존했다.
지역 정렬 오차와 의미 중복까지 완전히 배제한 것은 아니므로 **동일 발화 중복/신규성은 미확정**.
JA313·KO playback296·absorption17, 기존 KO SRT bytes 모두 유지했다.

## Hermes 단일 후보 준비

기존 canonical builder/parser·직접 runner를 재사용했다. canonical request SHA
`929e7abd8d922d56619dc2770a9082bbb8ee5ec941cea6b21cf4a8a862c1172f`와 기존 ASR core 시각은
변경하지 않았다. 원본 증거의 재현성을 보존하고, 단일 후보의 **현재 검토 시각**은 별도
`timing_revision.main.range_ms`와 `review-candidate.json`에 기록했다.
Hermes 입력에도 원래 시각은 역사적 ASR 근거, 갱신 시각은 추정 검토 창임을 명시했다.
`はい`는 context-only이며 추가 응답 cue로 생성할 수 없다. 파싱된 검토 sidecar에도
원래 ASR 시각과 갱신 review 시각을 구분한다. native 응답 계약은 변경하지 않았다.

이전 생성 검증기의 과도한 문자열 치환이 CLI `argc==3`까지 `==1`로 바꾼 오류를 수정했다.
새 번들에서 group 개수만 치환한다. 이전 번들은 역사적 자료로 유지하며, helper SHA 변경으로
이전 실행 명령은 superseded 상태다. **아래 새 경로만 사용한다.**

입력 SHA·canonical 재현·SRT byte 비교·shell syntax·19개 offline 계약 검사 PASS.
실제 생성 검증기의 CLI를 네 action 모두에서 임시 합성 응답으로 시험했고 즉시 삭제했다.
이는 Hermes 판단 결과가 아니다. 원격은 기존 임시 profile SHA와 native CLI 경로만 읽었다.
실제 추론 시 tools.count=0·새 세션·엄격한 ID/SHA 검사 등 기존 안전 경계가 적용된다.

입력·안전 검증만 수행(실제 호출 없음):

```bash
bash /var/tmp/stage11-clip011-boundary-recovery-20261012/native/ct108-native-single-command.sh --preflight
```

사용자가 별도로 실제 문맥 검토를 실행할 명령(Codex는 실행하지 않음):

```bash
bash /var/tmp/stage11-clip011-boundary-recovery-20261012/native/ct108-native-single-command.sh
```

모든 결과는 approved=false / srt_eligible=false / publishable=false. 기존 자막 삽입 경로 없음.
모델 호출·설치·원음 재생성·SRT 변경·승인·게시·운영 서비스 변경 0회. 보호 자료2325개 SHA 유지.

**남은 문제와 다음 작업 하나:** 기존 Context WAV에서 `いいところだね`와 별도 `はい`의
실제 음소 시작·끝을 사용자가 시각으로 표시해, 모델 추정 창을 수동 확인 경계로 교체한다.
