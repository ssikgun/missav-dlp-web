# Stage11 — 단일 누락 대사 복구 Pilot (clip-011)

결과는 **AMBIGUOUS / INCOMPLETE**다. 원음과 일본어 가설 일치는 미확정, 기존 자막의 동일 발화 중복도 미확정, 실제 자막 보완 여부는 판단 보류다. **Hermes 직접 실행 준비는 PASS**: 기존 계약으로 단일 그룹 입력을 재구성하고 로컬 사전 검증 및 원격 파일 읽기 점검을 통과했다. 실제 Hermes 실행·판단·한국어 초안은 생성하지 않았다. 준비 PASS는 원문 정확성이나 복구 성공 판정이 아니다.

원음은 기존 Pilot B `scope-pack/core/clip-011.wav`와 `context/clip-011.wav`를 그대로 참조한다. 본문은 원본 절대 시각 3355.932–3356.832초, 문맥은 3353.932–3358.832초다. 본문 SHA는 `5c9e63db5cb814d0268ecf936661eb42a57ca30079173a21d4a946cc218eb896`, 문맥 SHA는 `7147925aeac9aca78a704721fdb048ac91cdb2feb69e093188e7199d9ccc3e83`이다. 사용자 본문 판정 `DIALOGUE_LIKELY`와 이전 문맥 대사 존재 판정을 별도로 보존한다. Codex가 일본어 원문을 독립 청취하여 확정했다는 기록은 없다.

원본 영상 SHA `442e19dd0c45df924ecac28c76f4b3c18b19f53f0e5a00e3abd76bb650a84651`은 기존 실행 입력의 검증 기록에서 재사용한 역사적 pin이다. 이번에 원격 영상 전체를 새로 해시한 값으로 표시하지 않는다. 부모 float32 PCM SHA `51f551a00e713c3ad4c15e15c86fca55713210d94137da4d6055c9c96db77f75` 및 관련 입력 파일은 현재 바이트로 다시 확인했다. 기존 16 kHz PCM sample [53694912, 53709312)의 본문 crop 동일성은 이전 오디오 동일성 검증과 현재 WAV SHA에 연결했다. media timeline은 공통 시작 0초, audio 시작 0초, video stream 시작 0.021초를 기록한다. 기존 절대 시간축과 JA affine 정렬을 재사용하며 새 보정은 적용하지 않았다.

STT 가설은 두 엔진 모두 `いいところだね`다. Whisper 원본 A는 3355.932–3356.832초, B는 3355.960–3356.820초이고 실제 입력은 3351.000–3372.000초의 `positive-05.float32.npy`다. 원본 정규화 결과 파일의 SHA/segment index를 기존 기록에 대조했다. Reazon은 기존 four 결과의 case-04, 원음 입력 3354.400–3357.840초이며 WAV SHA `c9530f055b1694f63e616f80f50ea39cc058b0bb56f93861e2523cbbefc86cdd`, 실제 float32 변환 입력 SHA `e10a60d08d96c0c046cf3ebb1e2034b282faba900dfad3249a695b91eb08d08d`를 보존한다. 앞뒤 0.9초 인공 패딩과 원래 추정 토큰 시점도 별도로 보존한다.

**문장 전체가 0.9초 본문에 대응하는지 아직 불명확하다.** Reazon에서 본문 안에 점이 배치된 토큰은 `ところだ`이고, 다른 `い`는 3355.820초로 본문 앞, `ね`는 3356.900초로 본문 뒤에 있다. 첫 `い`는 인공 패딩에 배치됐다. 저장된 다른 Whisper 출력은 3355.400–3356.840초 또는 3355.900–3356.820초, medium은 3356.000–3357.160초로 경계가 다르다. 모두 추정치이며, 문맥 전체의 문면 일치를 본문 전체 전사 정확성으로 바꾸지 않는다. 일본어 정확성은 `UNVERIFIED`, 수동 발화 경계는 미확정이다.

인접 기존 자막은 다음과 같으며, 현재 KO와 초기 KO가 이 네 cue에서는 동일하다.

| 기존 cue | 정렬된 절대 초 | 기존 JA | 현재 KO | absorption |
| --- | --- | --- | --- | --- |
| ja-000134 | 3337.911–3338.925 | どうですか? | 어떠세요? | 없음 |
| ja-000135 | 3339.493–3342.881 | えっと、ちょっとだけ。はい。じゃあ、こち らで。 | 어, 잠깐만요. 네. 그럼 이쪽에서. | 없음 |
| ja-000136 | 3362.108–3367.930 | あんたは黙ってなさい | 너는 조용히 해. | 없음 |
| ja-000137 | 3367.930–3372.555 | いつもこうなの? | 항상 이래요? | 없음 |

본문과 시간상 겹치는 기존 JA/KO playback cue는 각각 0개다. 직전 cue 끝과 본문 시작은 13.051초, 본문 끝과 직후 cue 시작은 5.276초 떨어져 있다. 313개 JA에 주가설 문면의 완전 문자열 포함은 0건이다. 이 사실들은 동일 발화가 직전·직후 자막에 의미상 이미 포함됐거나 정렬 오차로 옮겨졌다는 가능성을 배제하지 못한다. 단순한 문면 검색으로 “중복 없음”을 확정하지 않는다.

기존 absorption 17개의 전체 연결 기록을 조회했다. 네 인접 cue가 absorption 원본·대상인 기록은 없고, 기존 병합 후 KO playback cue도 본문 시각을 덮지 않는다. 기존 정본 결과를 canonical parser로 검증하고 메모리 안에서 기존 materializer를 적용해 **JA 313 / KO 296 / absorption 17**과 저장 SRT의 바이트 동일성을 확인했다. SRT는 파일로 다시 생성하거나 수정하지 않았다. JA 정렬은 기존 scale `1.0141571005475907`, intercept `239.12146403396832 ms`, residual threshold `1000 ms`다. threshold는 이 구간의 실제 오차 상한이나 수동 정렬 검증이 아니다. 동일 발화 중복 및 신규성은 `UNVERIFIED`로 유지한다.

검토 후보로는 사용할 수 있다. 사용자 대사 가능성 판단, 출처와 시간 정보가 있는 복수 STT 가설, 현재 자막의 시간 공백이 근거다. 그러나 일본어 원문·문장 전체 발화 시각·의미 중복을 확인하기 전에는 실제 KO 삽입 후보로 승인할 수 없다. 신규 승인 0, `publishable=false`, `srt_eligible=false`다. 주변 STT의 `はい` 및 `弟さんと住んでるの?`는 문맥 증거만 전달하며 추가 출력 후보가 아니다.

기존 실행 경로 조사: `teddy_discovery_stage11_controller.py`의 hybrid review 진입점과 `teddy_discovery_stage11_deployment.py`의 `SSHRemoteHermesBridge.launch_quality_review`는 모델 transport 주입 및 native 세션 경계를 사용한다. 이번 단일 supplemental 작업에는 기존 `ct108-native-supplemental-command.sh` 직접 경로와 canonical `build_supplemental_review_request` / `parse_supplemental_review_result`를 재사용했다. 운영 controller/bridge는 변경하거나 실행하지 않았다.

단일 입력은 기존 두 A/B candidate ID를 동일한 1개 group ID에 유지한다. canonical request에는 일본어 가설, 시작·끝, 앞뒤 JA/초기 KO/STT, 출처 증거가 원래 계약대로 들어간다. 보조 `candidate-evidence.json`에는 현재 KO, absorption 17개, 실제 recognizer 입력 범위, 사용자 판정, 시각 경계 및 정렬·중복 불확실성을 붙였다. 이는 보조 증거이며 새 모델 응답 계약이 아니다. text 모델에 원음이 전달됐다고 주장하지 않는다.

기존 native canary helper의 오래된 SHA pin 1개는 이후 이미 검증된 draft bundle의 현재 source pin으로 연결했다. 원래 helper 파일과 기존 bundle은 수정하지 않았다. 갱신 내역은 `native/source-pin-revision.json`에 보존했고, 현재 canonical builder로 기존 3-group request 바이트를 그대로 재현한 뒤 1-group request를 만들었다. 오디오·자막·정답 자료의 SHA를 임의로 갱신한 것은 아니다.

직접 실행 bundle: `/var/tmp/stage11-single-dialogue-pilot-20261011/native/`.

사전 검증만 수행하며 모델을 호출하지 않는 명령:

```bash
bash /var/tmp/stage11-single-dialogue-pilot-20261011/native/ct108-native-single-command.sh --preflight
```

사용자가 별도로 실행할 실제 Hermes 명령:

```bash
bash /var/tmp/stage11-single-dialogue-pilot-20261011/native/ct108-native-single-command.sh
```

실제 명령은 local SHA와 canonical 입력 검증을 먼저 수행한 뒤, 기존 CT120 임시 profile의 config/prompt SHA 및 경로를 점검하고 `prompt-size --json`의 `tools.count=0`을 확인한다. 이어 기존 provider/model/reasoning 그대로 fresh `chat -Q`, `--max-turns 1`을 실행한다. resume이나 반복 호출은 없다. 기존 SSH 키·known_hosts 검증 및 정확히 알려진 tirith prefix 분리만 유지한다. 결과는 새 `/tmp/stage11-single-supplemental-result-XXXXXXXX/`에 저장하고 기존 strict parser로 1개 ID/순서/request SHA/action-category/대체문 규칙을 검증한다. KEEP/REPAIR도 승인 또는 SRT 적격으로 전환하지 않는다. 미래 실행에서도 원음 검증 및 별도 중복 검토가 필요하다.

예상 출력은 기존 계약의 **schema_version=2, request_sha256, cues**이며 cue 필드는 **cue_id, action, category, reason, replacement_ja, replacement_ko**다. `decision`은 action, `japanese_text`/`korean_draft`는 충분한 근거가 있는 REPAIR에서만 replacement_ja/replacement_ko에 대응한다. KEEP/OMIT/AMBIGUOUS의 대체문은 null이다. `source_evidence`는 입력 sidecar, `unresolved_issues`는 입력의 미확정 목록과 응답 reason으로 추적한다. 이 별칭을 native JSON 필드로 추가하면 strict parser가 거부한다. 파싱 후 review sidecar에 `publishable=false`가 부착된다. `response-contract.schema.json`은 구조 설명만 담고 실제 Hermes 판단은 담지 않는다.

검증: local preflight PASS, 원격 임시 profile SHA/CLI 파일 읽기 점검 PASS(원격 쓰기 0, Hermes invocation 0), shell syntax PASS, 12개 synthetic in-memory 계약 점검 PASS. 합성 점검은 승인 차단·잘못된 SHA/ID/추가 후보/대체문/응답 필드 거부를 확인했으며 모델 결과 파일로 저장하지 않았다. 모델 품질·실제 실행 결과·원문 정확성은 검증하지 않았다. 2302개 기존 보호 SHA와 작업 전의 다른 Git 변경은 보존했다.

이번 작업의 신규 Whisper/Reazon/Hermes 및 다른 모델 실행 0, 설치·다운로드 0, 실제 SRT/JA/KO/absorption 변경·승인·게시·운영 서비스 변경 0. 가장 중요한 다음 작업 하나는 **원음에서 실제 일본어 청취문과 문장 전체 발화 경계를 확인하는 것**이다. 준비된 Hermes 입력은 그 확인을 대신할 수 없다.
