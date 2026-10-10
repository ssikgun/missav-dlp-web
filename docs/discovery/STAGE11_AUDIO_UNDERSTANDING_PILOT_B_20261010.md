# Stage11 — Audio Understanding Pilot B: Gemma 3n 실행 가능성·본문 정답 감사

결과: **BLOCKED_SAFE_STOP / 실제 Gemma 추론 미실행 / 현재 환경 실사용 FAIL / 모델 성능 NOT_EVALUATED**. Gemma 3n E2B의 오디오 입력을 실제 작동시킬 모델·실행기·접근권한·자원 조건을 확보하지 못했다. E4B는 실행 가능성만 조사했다. 요청한 자원 제한에 따라 가중치 다운로드와 모델 로딩을 중단했으며 임의의 모델/텍스트 전용 GGUF로 대체하지 않았다.

## 요청 결과

| 항목 | 이번 실제 결과 |
|---|---|
| 실제 모델 사용 여부 | 사용 안 함; load 0 / inference 0 |
| 본문 대사 탐지 X/13 | 미측정; 추론 0개, 본문 양성 정답 미확정 13개 |
| 비대사 오인식 X/14 | 미측정; 추론 0개 |
| DIALOGUE / NON_DIALOGUE / MIXED / AMBIGUOUS 모델 출력 | 없음; 판단 불가 건수도 미측정 |
| 실제로 들린 일본어·모델 근거·발화 추정 시각 | 모델 출력 없음 |
| 환각 사례 | 미측정; 환각 0건으로 해석하지 않음 |
| 모델 성능 판정 | NOT_EVALUATED |
| 현재 환경 실사용 가능성 | **FAIL**, 확대 적용 금지 |
| 다음 작업 하나 | 양성 13개의 본문만 청취해 대사 존재·실제 발화 원본 시각 확정 |

0/13 탐지나 0/14 오인으로 기록하지 않았다. 추론을 하지 않은 상태와 실제 모델이 놓치거나 맞힌 결과는 구분했다. 이번 FAIL은 실행·검증 요건 미충족이며 Gemma 3n의 음향 분류 품질 실패를 측정한 결과가 아니다.

## 기존 저장소와 운영 환경 조사

저장소 `/opt/missav-pwa-subtitle-stage11`, 정본 `docs/handoff/missav-dlp-web/CURRENT_HANDOFF.md`를 먼저 확인했다. 기존 미커밋 파일 14개와 운영 Worker/llama.cpp를 변경하지 않았다. 실제 최신 원격 branch를 명시 fetch한 별도 worktree에서 이번 task 파일/정본 section만 push한다. 기존 로컬 작업과 이전 로컬 전용 커밋은 포함하지 않는다.

- CT108: RAM 총 10.00GiB, MemAvailable 4.01GiB, swap 여유 0.00GiB, `/var/tmp` disk 여유 23.02GiB. NVIDIA CUDA 장치 없음.
- VM122: RAM 총 31.28GiB, MemAvailable 4.35GiB, disk 여유 41.44GiB. RTX3060 12,288MiB 중 9,011MiB 사용 / 2,902MiB 여유.
- VM122 운영 llama-server PID56591과 Whisper Worker PID158369를 읽기 전용으로 조사했다. 운영 모델 Qwen3.6-35B-A3B의 RAM/GPU를 점유한 상태를 그대로 유지했다. 공간을 만들기 위한 서비스 종료·GPU offload 변경·cache 조정·재시작을 하지 않았다.
- 조사한 Gemma 파일은 Gemma 4 E2B Q4/Q8, Gemma 4 E4B Q4이다. GGUF 헤더의 실제 `general.architecture=gemma4`와 모델 이름을 확인했다. Gemma 3n E2B/E4B 체크포인트는 조사한 기존 models/HF cache/ollama 경로에 없었다.
- 기존 mmproj-BF16.gguf는 헤더상 `clip.audio.projector_type=gemma4a`, `clip.vision.projector_type=gemma4v`, Gemma 4 E4B용이다. 파일이 존재한다고 실제 오디오 동작을 확인한 것은 아니며 요청된 Gemma 3n의 projector로 사용하지 않았다.
- 기존 실행기의 Gemma 3n 언어모델/이미지 지원 존재와 오디오 지원은 별개다. llama.cpp commit `5190c2ea8d51f24c6a6f12e9d316ded72a6f2f23`의 `/home/teddy/llama.cpp/tools/mtmd/clip.cpp:2911`은 `skip_audio = ctx_vision->model.proj_type == PROJECTOR_TYPE_GEMMA3NV;`로 Gemma 3n 오디오를 건너뛴다. 해당 소스·binary SHA와 GGUF metadata를 evidence에 보존했다.
- CT108 기본 Python, VM122 기본 Python 및 기존 Whisper venv에 Gemma 3n용 torch/transformers/LiteRT-LM 실행기가 없었다. 기존 venv·llama.cpp binary·운영 환경을 설치/업데이트하지 않았다.

## 공식 모델·다운로드·자원 사전 확인

공식 [Gemma 3n E2B 모델 카드](https://huggingface.co/google/gemma-3n-E2B-it) 및 [Gemma3n Transformers 문서](https://huggingface.co/docs/transformers/model_doc/gemma3n)는 audio 입력을 지원한다. 이 문서상의 기능을 이번 환경에서 실제 동작한 것으로 간주하지 않았다. E2B의 effective 2B 표기가 표준 전체 체크포인트 용량 2B를 뜻하지는 않는다.

모델 metadata API의 revision·shard byte size·LFS SHA를 읽기 전용으로 확인하고 해당 revision의 파일 HEAD 접근을 시도했다. 공식 Hugging Face 계정 자격증명은 확인되지 않았고 아래 네 경로 모두 HTTP401이었다. 인증/라이선스 접근을 우회하지 않았다.

| 공식 모델 경로 | 확인한 가중치 용량 | 파일 접근 | 실행 |
|---|---:|---|---|
| [google/gemma-3n-E2B-it-litert-lm](https://huggingface.co/google/gemma-3n-E2B-it-litert-lm) | 3,655,827,456bytes (3.40GiB); standard INT4 gemma-3n-E2B-it-int4.litertlm | HTTP401 | 미실행 |
| [google/gemma-3n-E2B-it](https://huggingface.co/google/gemma-3n-E2B-it) | 10,879,085,840bytes (10.13GiB); 3 safetensors shards | HTTP401 | 미실행 |
| [google/gemma-3n-E4B-it-litert-lm](https://huggingface.co/google/gemma-3n-E4B-it-litert-lm) | 4,919,541,760bytes (4.58GiB); standard INT4 gemma-3n-E4B-it-int4.litertlm | HTTP401 | 미실행 |
| [google/gemma-3n-E4B-it](https://huggingface.co/google/gemma-3n-E4B-it) | 15,700,181,712bytes (14.62GiB); 4 safetensors shards | HTTP401 | 미실행 |

표준 Transformers E2B 가중치 10.88GB와 E4B 15.70GB는 각각 현재 가용 RAM/GPU 여유를 넘는다. 디스크 여유가 있다고 실행 메모리가 확보된 것은 아니다. 양자화·PLE offload·vision 생략을 사용하면 footprint가 달라질 수 있으나, 그 구성의 오디오 작동과 peak memory는 이번 환경에서 확인되지 않았다. 운영 GPU 메모리 부족 상태에서 실험을 강행하지 않았다.

작은 E2B 공식 LiteRT INT4도 조사했다. 표준 패키지는 3.66GB이고 Web 패키지는 3.04GB이지만 둘 다 HTTP401이었다. 패키지 byte 크기만으로 실행 peak RAM을 단정하지 않았으며 Web 파일을 Python/CUDA 호환으로 간주하지 않았다. E4B LiteRT 표준 패키지는 4.92GB이며 접근/실행기/가용 메모리 요건을 충족하지 못했다. E4B 모델 load/inference는 0이다.

신규 runtime 설치 0, 모델 가중치 다운로드 0byte, 모델 load 0, 오디오 추론 0. 다운로드한 것은 공개 metadata JSON뿐이다. 운영 서비스 자원 회수를 통해 실행하는 시도는 하지 않았다.

## 양성 13개 정답의 본문 범위 점검

Pilot A의 동일 27개 WAV·사용자 라벨을 SHA와 연결해 재사용했다. 양성 13개의 human-listening-notes와 역사적 listening manifest/TSV를 다시 확인했다. 판정 문구는 이 **클립에서** 실제 대사 존재 확인이며, 클립에는 앞뒤 문맥이 포함된다. 후보 video_start/end는 역사적 STT 추정 본문 시각이고 독립적인 사용자 발화 시작·끝 기록이 없다. 일본어 직접 청취문도 비어 있다.

따라서 **본문 대사 정답이 확정된 양성은 확인하지 못했고, 13개 모두 CORE_TRUTH_UNCONFIRMED**다. 이는 본문에 대사가 없다는 판정이 아니다. 기존 문맥 포함 양성 13개는 그대로 보존한다. YAMNet이나 기존 STT 텍스트로 본문 정답을 대신 확정하지 않았다. 특히 01/02의 공유 문맥, 05/06/07의 대사+음악, 12의 368ms 본문을 별도 보존했다.

| 원래 양성 순서 | 추정 본문 원본 시각 | 길이(s) | 기존 정답 범위 | 본문 정답 |
|---|---|---:|---|---|
| 01 | 00:01:03.500–00:01:05.220 | 1.720 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 02 | 00:01:05.220–00:01:07.872 | 2.652 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 03 | 00:03:11.840–00:03:14.020 | 2.180 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 04 | 00:03:32.820–00:03:33.936 | 1.116 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 05 | 00:03:35.880–00:03:36.620 | 0.740 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 06 | 00:03:38.940–00:03:41.360 | 2.420 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 07 | 00:03:41.360–00:03:46.020 | 4.660 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 08 | 00:04:20.360–00:04:22.000 | 1.640 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 09 | 00:04:22.000–00:04:24.580 | 2.580 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 10 | 00:04:25.200–00:04:26.240 | 1.040 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 11 | 00:55:55.932–00:55:56.832 | 0.900 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 12 | 00:55:57.732–00:55:58.100 | 0.368 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |
| 13 | 00:55:58.992–00:56:00.612 | 1.620 | 문맥 포함 클립 대사 존재 | UNCONFIRMED |

음성 14개는 기존 USER 판정 대상 본문 그대로이며 신음 11/음악 2/무대사 1로 유지했다. 문맥 WAV에 정답을 확장하지 않았다. 본문 정답과 문맥 정답을 별도 truth 파일로 기록했다: 본문은 양성 13 미확정/음성 14 확정, 문맥은 양성 13 확정/음성 14 미확정이다.

본문 WAV와 문맥 WAV의 exact PCM subset, 원본 파일 SHA, historical manifest 4개, 기존 보호 SHA 2,152개를 확인했다. 모델이 문맥에서만 대사를 출력하거나 본문 경계가 미확정인 경우 본문 탐지 성공으로 집계할 수 없도록 scope_transfer_allowed=false로 기록했다.

## 고정 프롬프트와 격리된 입력

실행 조건이 충족될 때 전체 27개에 동일하게 사용할 고정 프롬프트를 저장했다. `DIALOGUE / NON_DIALOGUE / MIXED / AMBIGUOUS`, 실제 들린 일본어, 음향 근거, 입력 오디오 기준 발화 추정 시각을 JSON으로 요구한다. 신음/호흡을 말로 바꾸거나 다른 언어를 일본어로 번역하지 않도록 명시했다. 해석 불가와 시각 추정 불가를 별도 표현한다.

프롬프트 SHA256 `5d7457334cd8faa157512cafadb980748222f89fac2e06564c2e4f4a609326b4`. **모델에 적용된 프롬프트 수는 0**이다. 본문/문맥 두 arm 각각 27개 익명 ID·상대 오디오 경로·SHA·sample count만 분리했으며 사용자 정답·Whisper/ReazonSpeech 텍스트는 모델 입력 파일에 없다. truth/scope 파일은 별도다. 프롬프트 준비를 실제 추론으로 보고하지 않았다.

## 보존·검증 및 다음 작업 하나

- Worker/llama-server PID·start ticks·argv SHA·exe와 source/binary SHA, 모델 inventory를 조사 전후 비교해 동일함을 확인했다. 기존 미커밋 파일도 이번 정본 section을 제외한 원래 byte를 보존했다.
- Whisper/ReazonSpeech 재실행 0, Hermes/Gemini 호출 0, GPU Worker/llama.cpp 서비스 변경 0, 기존 자막 변경·승인·게시 0. R2 신규 후보 2개는 기존 별도 보관 상태 그대로이며 이번 입력과 집계에서 제외.
- 호스트 증거 `/var/tmp/stage11-gemma3n-pilot-b-20261010/`: resource/model/access audit, before/after service SHA, result.json, scope-pack/의 원음 두 arm·scope/truth·고정 프롬프트·listen-core.html·core-judgment.template.tsv.
- 저장소 증거 `docs/discovery/evidence/STAGE11_AUDIO_UNDERSTANDING_PILOT_B_20261010/`: result/resource/access/scope/truth/protocol/prompt/verification. 범용 offline 감사 도구 `tools/stage11_gemma3n_scope_audit.py`는 모델·서비스를 호출하지 않는다.
- 다운로드 `/var/tmp/stage11-audio-understanding-pilot-b-20261010.tar.gz`, 사용자 사본 `/mnt/data/stage11-audio-understanding-pilot-b-20261010.tar.gz`. 원음·근거·SHA를 포함하고 모델 출력은 없다.
- 다음 작업은 **양성 13개 본문 원음만 직접 청취해 대사 존재·실제 원본 발화 시각을 기록하는 것 하나**다. 압축의 scope-pack/listen-core.html에서 본문 → 문맥 → 본문 순서로 확인하고 core-judgment.template.tsv에 적는다. 본문/문맥 판정을 혼동하지 않고 불분명하면 AMBIGUOUS를 유지한다. 모델 예측을 정답으로 삼지 않는다. 이후 실행에는 별도로 승인된 모델 접근과 충분한 독립 오디오 실행 자원이 필요하다.
