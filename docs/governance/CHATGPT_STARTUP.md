# ChatGPT Downloader 프로젝트 시작 지침

ChatGPT는 저장소의 `AGENTS.md`가 자동으로 주입된다고 가정하지 않는다. 새 대화방을 시작하거나 Codex 작업 지시문을 작성하기 전에 다음을 수행한다.

1. 저장소가 `ssikgun/missav-dlp-web`인지, 실제 작업 디렉터리와 브랜치가 무엇인지 확인한다. 최신 GitHub `teddy-subtitle-stage11` 정본을 확인하고 사용자가 지시하지 않은 `main`으로 대체하지 않는다.
2. 같은 정본에서 루트 `AGENTS.md`, 공통 `docs/governance/PROJECT_CONTRACT.md`, `docs/governance/ACTIVE_WORK.md` 라우팅 목록을 읽는다.
3. 작업 목적과 영향을 받는 실제 파일·자원을 함께 고려해 공통 작업, Stage11 자막 작업, 다른 등록 workstream, 여러 영역의 공유 작업 중 어디에 해당하는지 분류한다. Stage11 파일이 저장소 루트에 있다는 이유로 다른 영역으로 분류하지 않는다.
4. 선택한 모든 workstream의 계약과 `ACTIVE_WORK.md`를 읽고 계약 버전, 작업 ID, 상태, 허용/금지 범위, 완료 조건을 확인한다. 공유 작업이면 모든 관련 영역을 선택하고 동일한 승인 작업 ID가 등록됐는지 확인한다.
5. Stage11이 `INACTIVE`이면 현재 승인된 자막 작업이 없다는 뜻이므로 Stage11 작업을 시작하지 않는다. 이는 승인된 Stage11 설계 계약이 폐기됐다는 뜻이 아니다. Stage11의 비활성 상태만으로 독립된 다른 등록 workstream의 승인 작업을 막지 않는다. 작업 영역이 등록되지 않았거나 선택한 영역의 계약·작업 ID가 없으면 fail-closed로 보고한다.
6. 기존 구현과 증거를 확인해 완료 작업의 중복 지시를 막는다. Handoff는 관련 이력만 참고하며 그 안의 `NEXT` 문구는 승인이나 작업 범위를 바꾸지 않는다.
7. Codex의 기술적 PASS를 제품 목표 PASS로 간주하지 않는다. 설계 충돌은 AI가 결정하지 않고 사용자가 선택할 수 있도록 보고한다.
8. 정본 파일을 읽을 수 없거나 계약/라우팅이 불일치하면 확인 불가 사유를 밝히고 구현 지시를 작성하지 않는다. 설계 변경은 사용자 승인 후에만 반영한다.

새 `/new` 대화에서도 실제 작업 디렉터리가 의도한 Downloader 저장소/worktree인지 확인해야 한다. 이 파일은 ChatGPT에 자동 등록되지 않으므로 사용자가 내용을 ChatGPT Project Instructions에 직접 붙여 넣어야 한다.
