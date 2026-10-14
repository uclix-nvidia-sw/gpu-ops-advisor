## Explicit exploratory permission and rule publication — 2026-10-14

- PASS (local): 1,201 non-E2E tests; 45 E2E cases deselected. Existing Windows-incompatible Report cleanup module excluded; no full cross-platform claim. Rule, explicit opt-in and missing-condition stop paths retain uncertain evidence semantics.
- PASS (isolated integration): 3 temporary PostgreSQL/Backend/JC/Incident/official-MCP fixture E2E cases covering registration/review/publication, rule selection and explicit JSON exploration through result publication. No production DB used by tests.
- PASS: Ruff lint/format; Korean repair diagnostic spans preserve original Unicode offsets, mask known identifiers, and persist only positions/hash, not rejected prose. This improves repair feedback without weakening validation.
- PASS (live, deployed predecessor plus new published content): dgx02 injection at 11:57:34 KST selected XID79 revision 6 and SXID11001 revision 5. Both recorded `method=runbook_rules`, `attempts=0`; XID D09/D44/D02 and SXID D09/D02 succeeded. Jobs created around 12:00:48; both published partial results with complete narratives. Both synthesis repairs passed on the second response; final editors passed without repair. Physical cause/device state remains unconfirmed.
- Published content hashes: XID79 `13a44c8cc52087158f47e9b1ee69cc5df2bcd6af3d1a08e8c3f70ebd43561fcc`; SXID11001 `ee1475be64daec318d40c435ee69a5c176b3019f21a177e47adfdde40dacaf0d`. Previous revisions were preserved, not retired by this operation.
- NOT DEPLOYED: the local explicit-only exploration gate, missing-condition UI wording and language-span feedback. Live rule selection success does not prove these unshipped changes. No commit, PR or code deployment performed in this task.

## Unified evidence evaluation — 2026-10-14 (local)

- PASS: 1165 non-E2E tests; 45 E2E cases deselected. Existing Windows Ops cleanup tests remain excluded as documented below.
- PASS: 3 isolated PostgreSQL/Backend/JC/MCP fixture E2E cases. Both rule and legacy exploratory selection publish two evaluation records with rounds 0/1 and zero old `unexpected_evidence`/`sufficiency` stage records.
- PASS: lint/format. Policy semantics, plan-extension provenance and historical result summary alias retained.
- Production deployment, live model/Grafana quality and new Runbook publication remain unverified/not performed.

## Runbook conditional auxiliary selection — 2026-10-14 (local)

- PASS: 1,165 non-E2E Agent tests with UTF-8 enabled; 45 E2E cases deselected. Unchanged Windows-incompatible Ops cleanup module excluded after two file-lock/fsync failures; no claim of full cross-platform suite success.
- PASS: three isolated E2E cases: Backend Runbook registration/review/publication and RCA consumption, plus legacy JSON and deterministic rule selection through result publication. Native loopback temporary PostgreSQL, current Backend/JC/Incident binaries, official MCP and fixture upstreams; no production DB.
- PASS: Backend vet, race tests (CGO/w64devkit), build; Ruff, formatting, documentation links. Initial race invocation lacked CGO; rerun with compiler passed.
- XID79/SXID11001 new draft conditions require scoped reported facts. Empty D09 blocks authored auxiliary queries; code does not promote inventory, timestamps, device state or cause. Rule selection has zero LLM attempts; no unconditional fallback when the model is unconfigured.
- Not performed: commit/push, deployment, new production revision registration/publication, or live XID/SXID validation. Existing immutable published revisions remain unchanged. Remaining catalog entries retain explicit policy or legacy exploration; no blanket 265-item conversion.

## RCA JSON selection — 2026-10-14 (local)

- PASS: 38 targeted RCA selection/workflow tests, including real LLM transport with fixture tool rejection, HTTP 401/500, invalid candidate, maximum batch, explicit stop and repair failure.
- PASS: isolated Worker/JC/Incident/MCP-to-publication E2E with fixture upstreams; tool calls rejected, JSON selection succeeds and unsafe synthesis subset remains filtered.
- First E2E setup used an obsolete JC binary; rebuilt current local JC/Incident and passed. Production HTTP 500 root cause and post-deployment behavior remain unverified. No shared LLM/Ops runtime changes.

## Ops GPU identity transitions / GPU 연결 변경 검증 — 2026-10-14

Base: freshly fetched origin/main `a317bf7`, branch `fix/report-gpu-identity-transitions`. Local-only changes. No RCA/shared runtime, Backend/JC/Incident, frontend runtime, DB schema, Helm or production data mutation.

- PASS: live read-only Grafana/Mimir inspection of October 13 CPC-1 09–10 / 12–13 KST and CPC-2 13–14 KST. Thirteen GPU-hour transitions across eleven distinct GPUs had disjoint old/new label intervals, separated by 15 seconds. Same-UID Pod metadata transitions included `pod_ip` becoming populated. Actual timestamp bounds and Pod identity were inspected; sum-of-counts alone was not treated as proof.
- PASS: local replay of stored report aggregates with the newly observed timestamp/Pod bounds through the production transition validator. Verified transitions: 8 + 3 + 2. Serving A100 80GB: valid hourly buckets 23→24, mean 3.7688626→3.8747123%, prior comparison −5.3146107%p and 19 low-mean buckets enabled. Serving A100 40GB: 9→10 buckets, 0.5106481→0.4620359%. Three CPC-1 test namespaces: 4→5 buckets. CPC-2 test namespaces: 3→4 buckets, means 62.9972222→47.8965153% and 53.9375→40.9651899%. Partial start buckets contribute their real sample counts, not a full hour of zeros. Prior-day absence remains uncomparable.
- PASS: 46 focused calculation/transition tests. Covers true overlap, interleaving, gaps, same-UID metadata changes, different UID/node, unknown/shared/MIG labels, outside-Namespace identities, evidence/aggregate mismatch, query failure, 32-call cap and publication-time reserve. No production endpoints in these tests.
- PASS: existing UI consumers, 35 tests across AggregateReport, NamespaceCharts and report helpers, Node 22.23.2. No UI edits or live browser preview of a newly generated report in this task.
- PASS: final full Agent/E2E suite, 1,211 passed / 0 skipped in 122.91s, three existing MCP deprecation warnings. Uses Python 3.11.16, current-main-built Backend/JC/Incident, native temporary PostgreSQL bound to loopback, real Worker/NAT/official Grafana MCP, and fixture Grafana/LLM upstreams. `AGENT_E2E_DATABASE_URL` is explicitly unset; production DB is not used.
- Initial new E2E failed because its synthetic aggregate response returned an unselected Namespace despite the query filter. Corrected the test upstream to respect the filter; production scope guards were retained. Both normal-transition publication and overlapping-identity partial publication are included.

UNVERIFIED: deployment/new-image production publication, production LLM latency, weekly/max-size/concurrent or high-churn load. Targeted verification adds reads, not a claimed speedup. All-period completeness/comparison rules remain; A→B→A bounds, missing retention or exhausted verification budgets can still leave partial analysis. Existing published reports are immutable and not rewritten. PR/commit/push/deployment have not been performed.

## RCA selection and subset recovery — 2026-10-14 (local)

- PASS: 1,127 Agent tests; 41 skipped without E2E flags. Existing Windows-incompatible
  Report cleanup suites excluded; no Ops runtime changes.
- PASS: final focused workflow/selection/synthesis/repair checks, 81 tests.
- PASS: five isolated E2E scenarios in total: three webhook variants, numeric repair,
  and missing-tool-call JSON recovery plus unsafe identity-cause/Korean subset
  filtering through Worker/JC publication. Fresh loopback PostgreSQL, actual
  Worker/JC/Incident/official MCP; Grafana and LLM upstreams are fixtures.
- The first new E2E attempt bypassed model selection via fixture policy. The fixture
  was corrected to leave D02 approved without forcing it, then passed.
- PASS: Ruff and local document links. No production DB, Runbook publication or
  deployment. Live XID/SXID model selection and language quality remain unverified.

## RCA label mirror CI correction — 2026-10-13

- Synchronized the packaged RCA labels with the frontend dictionary: six collection termination reasons and the sufficiency explanation. No workflow, Ops or production data changes.
- PASS: 105 Korean/report, synthesis-context and collection regressions, including the CI-failing mirror equality test.
- PASS: three webhook-to-RCA-publication E2E cases using fresh loopback PostgreSQL, actual Worker/JC/Incident/MCP and fixture Grafana/LLM. Production behavior remains unverified.
- Local sandbox blocked Windows asyncio socketpair setup; rerunning the same tests outside that sandbox passed without code changes.

## RCA bounded evaluation and Korean repair — 2026-10-13 (local only)

- Python regression: 1,105 passed, 41 skipped (E2E flags disabled); Windows-incompatible report cleanup tests excluded. No Ops implementation changes.
- Six focused RCA E2E cases passed using a fresh loopback PostgreSQL, rebuilt current Job Controller, real workers and official MCP with fixture upstreams: webhook intake, fallback and numeric repair/publication.
- Frontend: 265 tests, build and format passed. Actual-component local preview verified main headings at 18px, title at 22px and reference subheadings at 15px.
- First E2E setup failed with a stale local JC binary (invalid report criteria profile). Rebuilding current JC resolved setup; production was not accessed.
- Live SXID repair remains unverified. Do not expand/publish the remaining 265 guidance revisions until XID and SXID both pass production review. This change does not repair producer time or device identity.

# 2026-10-13 Ops report detail producer / 보고서 상세 자료 생성 후속 검증

Base: origin/main `e639839` (merged UI #113). Isolated worktree `/private/tmp/gpuops-report-details-pr`; no production DB/data changes. Runtime edits are confined to four Ops modules. RCA/shared runtime, Backend/Incident/JC, queries, migrations and Helm are unchanged.

기준 main `e639839`의 화면에 필요한 노드·알림 종류를 Ops에서 생성하는 후속 변경이다. 운영 DB·데이터를 변경하지 않았고 제품 코드 수정은 Ops 4개 파일에 한정한다.

- **PASS** Python 3.11.16: `PYTHONPATH=<worktree>/shared/python/src:<worktree>/rcca-agent/src:<worktree>/ops-agent/src RUN_AGENT_E2E=1 ... python -m pytest -c agents/pytest.ini agents/tests -q`: **1,160 passed, 0 skipped, 108.40s**, three existing MCP deprecation warnings. Fresh loopback-only PostgreSQL, current-main-built Backend/Incident/JC, real RCA/Ops Worker/NAT/official MCP; Grafana and LLM upstreams are fixtures. Explicitly unset `AGENT_E2E_DATABASE_URL` and use the local server binaries at `namespace-tools/postgres/bin`.
- **PASS** New/extended checks: verified nodes only; previous-only nodes excluded; prior comparison availability; per-cluster XID/SXID/component/unknown categories; duplicate incident IDs; current vs previous-only counts; firing/test markers. Actual DB title fallback/truncation/full-source hash, JSON-null node fallback, metadata allowlist, scope and period boundaries. Real Ops Worker publication retains nodes/categories/status timestamp and excludes private raw payload.
- **PASS** Additional main-versus-change comparison across 20 synthetic cases (activity 0/4/5/60/100 × complete/missing identity/query failure/incomplete hour): every existing Namespace result field matches after excluding only the added metadata. This is calculation equivalence on fixtures, not a production performance benchmark.
- **PASS** Full Ruff lint and format check (126 files), `git diff --check`, UTF-8 CRLF and documentation links (115 documents, 1,433 links/assets, zero errors).
- **PASS** Frontend consumer regression: **264 tests / 25 files**, format and TypeScript/Vite build, Node 24. Existing bundle-size warning remains. UI code is unchanged from #113; rendering assertions cover added fields and absent-field compatibility. No new browser/live Grafana session was used for this follow-up.
- Setup correction: the first run pointed at client-only Homebrew libpq and could not initialize PostgreSQL; corrected to the existing local server tools. A new assertion initially excluded previous-only recurrence groups; corrected to preserve the existing `(current=0, previous=1)` behavior. Final full rerun above passed without product workarounds.

**미검증 / UNVERIFIED:** Production image deployment and new live CPC-1/CPC-2 report publication, production LLM quality/latency, weekly/max-size/concurrent load. CI Python 3.12 result is separate from the local Python 3.11 run. No performance reduction is claimed. Existing published reports are not rewritten; generate a new aggregate report after upgrade, and retain unknown when source metadata is missing. No settings or migration are required. LLM operational interpretation and policy integration remain separate work.

로컬 실제 프로세스 검증은 통과했지만 운영 배포·운영 자료 기반 새 보고서 발행까지 확인한 것은 아니다. 과거 보고서 자동 보완 없이 배포 후 새 보고서로 노드·알림 제목·종류별 현황·상태 기준 시각을 확인한다. 기존 계산은 유지하며 원천에 없는 정보는 미확인이다.

## Structured RCA guidance — 2026-10-13 (local verification)

- Python agent regression: 1,100 passed, 41 skipped; Windows-incompatible report cleanup suite excluded (Report implementation unchanged).
- RCA fixture integration: six webhook/fallback/repair cases passed; Runbook API lifecycle passed separately using current Backend/JC, temporary PostgreSQL, official Grafana MCP and fixture upstreams. This checks registration/review/publication and selected XID/SXID guidance in the result, not live model quality.
- Backend: vet, race tests and build passed. Frontend: 255 tests, format and build passed (existing bundle-size warning). Local actual-component browser preview checked at 5291.
- Selected Runbook originals survive missing applicability facts; this does not authorize recommendations. XID/SXID unidentified-device claims are rejected for covered wording patterns; this is not an exhaustive semantic proof.
- Not performed: production publication, retirement, deployment or live RCA. Publish reviewed new revisions after compatible Backend/Worker deployment. Producer zero timestamps and unmatched device identities remain unresolved.

## PR CI portability follow-up / PR CI 환경 차이 수정

Initial Python 3.12 CI: 1,149 passed and one new Backend intake E2E failed because it required BACKEND_BINARY. The test now uses the same platform-aware `.local/backend-e2e` fallback as existing E2E cases. With BACKEND_BINARY unset, both new aggregate publication/intake E2E cases passed locally (2 passed, 28 deselected; fresh loopback DB and fixture upstreams). Product code and RCA are unchanged. Remote rerun status is tracked on PR #110.

최초 CI의 신규 테스트 1개에서 Backend 경로 환경변수 누락을 확인했다. 기존 테스트와 동일한 기본 경로를 사용하도록 수정했으며, 환경변수를 제거한 조건으로 신규 집계 보고서 공개·접수 E2E 2개를 재검증했다. 제품 코드·RCA 변경은 없다.

# 2026-10-13 Ops aggregate report — local verification / 로컬 검증

Base: origin/main `f7cf8c9`; branch `feat/ops-report-aggregation`. Local verification for PR; not deployed. [Design, query semantics, measured data size and limitations](../docs/specs/ops-agent/aggregate-report-v1.md).

- PASS: Python 3.11.16, both-worker complete suite: 1,150 passed / 0 skipped after integrating latest main (112.91s; three existing MCP deprecation warnings). Actual local PostgreSQL/Backend/JC/Worker/NAT/official MCP processes, fixture Grafana/LLM. New report works without the D registry; manual intake, publication/read and daily/weekly schedule acceptance, monthly rejection verified.
- PASS: Go 1.26.2, shared/backend/job-controller/incident `go vet ./...`, `go test -race ./...`, `go build ./...`. Backend and Incident `go test -tags=e2e ./... -count=1 -timeout=10m` use a newly initialized loopback-only temporary database; stopped after tests. Includes JC lifecycle/report compatibility checks.
- PASS: Frontend 251 tests in 24 files, format check, TypeScript and Vite build (Node 22.23; CI Node24 not locally exercised). Existing bundle-size warning remains.
- PASS: Helm 3.17.3 contract/render/package/mirror checks and 22 CI tool tests. New report profile is also in the opt-in independent-worker values example.
- PASS: Browser on local fixture preview: namespace selection changes the graph and matching summary; exact hourly values expand; empty/unavailable input remains blocked rather than zero; weekly automatic form displays weekday/time; desktop and narrow form checked; no browser console errors observed. One static design detector pass completed without findings.
- LIVE READ ONLY: final three PromQL expressions executed against CPC-1 for Oct12 KST. Same-period serialized Grafana data decreased about90.16% (1,698,241→167,175 bytes), samples103,716→1,968. Request time improvement is NOT established (different execution/cache conditions: earlier391+121ms vs546ms). Detailed calculation differences and methodology are in the design document.
- UNVERIFIED: production deployment/publication with live LLM, CPC-2 end-to-end new collection, complete weekly comparison, maximum256GPU capacity and multi-worker concurrent load. Local browser samples are synthetic, not production reports. No production data is committed. RCA implementation, D definitions and production settings were not changed.

## 2026-10-13 RCA identity-cause and repair regression

- PASS: worktree PYTHONPATH, Python UTF-8 mode; 1077 passed / 38 skipped in agents/tests, excluding test_report_cleanup.py. That unchanged Report module has Windows open-file unlink and directory fsync failures; no Report fix is included. Optional E2E skips are not passes.
- PASS: six selected real local lifecycle E2E cases (Grafana webhook through Incident, no published Runbook, numeric repair), using fresh temporary PostgreSQL, Incident/JC/RCA and official Grafana MCP with fixture upstream Grafana/LLM responses. Not production integration.
- PASS: Korean identity uncertainty paraphrases are rejected as causal hypotheses even without inventory relation metadata; repair moves them to limitations, and a second invalid Korean response is marked validated_subset. Raw rejected model text is not added to diagnostics. Full Ruff checks/format and documentation links pass.
- UNVERIFIED: new production LLM responses and deployment. Pattern validation does not prove every unsupported hypothesis is caught. Ops runtime, shared contracts and published Runbooks are unchanged.

# 2026-10-13 RCA operator wording — final checks

- Focused RCA regression: 99 passed, including conditional uncertainty wording and preserved assessment/evidence references.
- Local temporary PostgreSQL + Incident/JC + real RCA Worker/NAT + official MCP: 6 passed, 21 deselected (webhook, missing Runbook and numeric repair/publication). Grafana and LLM upstreams were fixtures. No production DB used.
- Agent non-E2E: 1041 passed, 38 deselected before main integration; existing Windows Report cleanup module excluded (unrelated open-file deletion/directory fsync limitations). Relevant RCA checks pass; no full-suite-green claim.
- Production deployment and new live RCA remain unverified; review the new result after deployment.

# 2026-10-13 RCA general expansion — local verification

- Separate expected cause/state uncertainty from missing required evidence when
  deciding whether to add a general Runbook. Preserve all missing inputs and
  approved optional queries; query failure, conflict and identity gaps still
  permit fallback. No Ops/shared runtime, DB or published Runbook changes.
- Focused requirement, workflow, Fleet and synthesis tests: 81 passed using
  local fixtures. New-code live RCA and full E2E remain unverified; these tests
  do not establish physical GPU health or production LLM accuracy.
- Agent non-E2E regression: 1037 passed, 38 deselected, excluding the existing
  Windows-incompatible Report cleanup test module described below. Ruff check,
  format and document links passed. No full-suite/E2E-green claim.
- Read-only D09 UI inspection of the new synthetic run found 44 stored rows:
  11 synthetic Unhealthy reports and 33 existing Fleet Healthy reports. Valid
  synthetic timestamps do not validate the other source reports or GPU health.

# 2026-10-12 RCA evidence diagnostics — local verification

- Read-only production inspection of `6b31300c-1767-4265-9d38-a1db62ddbfa1`:
  XID79 revision 4 and general revision 3; D09 31 reports, D44 19 samples;
  D02 remained with query budget 46. Synthesis repair ran and failed with
  `non_korean_claim`; it was not skipped for time/budget.
- Grafana same-period Loki query confirmed the 18:00:03 KST Unhealthy report.
  Producer time is the year-one initial value; error PCI `0000:01:00` differs from
  inventory `0000:08:00.0`. JSON-string inventory exists. Reported error is supported;
  current state, event time, cause and physical error-device identity are not.
- RCA-only changes: third bounded collection round; explicit stop reason/remaining
  queries; inventory decoding without fact promotion; producer-time/state counts;
  field-specific LLM repair guidance; Korean incident-time display and correct
  hypothesis-versus-limitation diagnostics. Ops and shared Python are unchanged.
- Focused RCA tests: 61 passed. Broader Agent run: 1030 passed, 38 E2E deselected,
  excluding Report cleanup. The original Windows run had a locale failure resolved
  with UTF-8 mode and two Report cleanup failures (open file deletion/directory
  fsync); those unrelated tests/code were not modified. No full-suite-green claim.
- Frontend: 232 passed; typecheck/build/format passed, existing bundle-size warning.
  Ruff and document links passed. Fixtures are not live model validation.
- New-code production RCA, full E2E, commit/push, deployment and any DB/Runbook
  mutation were not performed. Past results retain their original contents.
# 2026-10-13 운영자 확인 중심 보고서 — 로컬 최종 검수

- 시작 기준 원격 main `9707b15`, 작업 브랜치 `feat/operator-report-insights`. 이 절은 로컬 구현·합성 회귀 결과이며 운영 배포·원격 PR·실제 자료 검증을 뜻하지 않는다.
- criteria 1.3의 O08/O01/O05/O11은 기존 지표·고정 DB snapshot에서 대상·기간·확인 이유·다음 확인과 유효 metric/evidence 참조를 구성한다. RCA Agent·공통 Python·JC·DB schema는 수정하지 않았다. O05는 정확한 사건 ID로 공개 RCA와 조치 기록만 연결하고, 알람 snapshot 상태와 실제 복구를 구분한다.
- 수집은 통합 binding + criteria 1.3의 O01 D06, O05 D10/D22를 제외한다. O05 단독은 실제 fixture 원격 호출 0회를 검증했다. 기본 O01/O05/O08/O11은 다른 주제가 소비하므로 기존 D 8종이 유지되고, O05를 함께 선택해도 D06의 안전한 Namespace/Pod 제한이 유지된다. 구 criteria/구 binding/다른 D06 소비자 조합은 회귀로 보존한다.
- Python 3.11.16, 저장소 루트 `.venv/bin/python -m pytest -c agents/pytest.ini`에서 `test_operator_insights.py`, `test_basic_report.py`, `test_report_minimization.py`, `test_report_pod_pruning.py`, `test_report_query_pruning.py`, `test_binding_contract.py`, `test_report_parallel.py` 초기 확장 검사 **160 passed**(3.75초). 이후 O05 증상 표시·상태별 다음 확인 4사례 추가 후 최종 `test_operator_insights.py` **16 passed**(0.17초). 두 실행은 겹치는 검사이며 합산하지 않는다.
- 확인한 경계: 일부 GPU만 저활동, 짧은 저활동 사이 공백을 연속으로 연결하지 않음, 빈/실패 표본을 0% 또는 전체 정상으로 해석하지 않음, 알려진 Node 조건만 점검 후보화, 실제 측정 시각 미확인 온도를 과열로 단정하지 않음, 수집 실패/미관측 분리, 사건 ID와 subject 종류가 다른 RCA/조치 제외, 발생 중·RCA 유무·해제·미확인별 안내, 계산값·단위·상태·자료 부족 판정 보존.
- **최종 통과:** 전체 Agent **1096 passed / 0 skipped**, 104.17초. 기존 MCP deprecation warning 3건. Python 3.11.16, 외부 DB/credential 변수를 제거한 새 loopback PostgreSQL, main 기준에서 빌드한 JC/Incident/Backend와 실제 두 Worker·공식 MCP를 사용했다. Grafana/LLM은 fixture다. 신규 확인 사항의 참조 검증·JC 발행, Backend 결과 조회·export 및 기존 RCA 회귀까지 포함한다. 최초 sandbox의 loopback bind 제한은 로컬 서버 허용 후 해소했고, 새 E2E의 '사건 없음' 단정은 실제 고정 DB snapshot의 사건 ID 집합과 대조하도록 바로잡았다.
- 전체 Python Ruff check/format, 최종 Frontend **236 tests / 22 files**·format·build, 문서 링크·diff 검사를 통과했다. Go 구현/DB schema는 미변경이라 해당 모듈의 전체 race suite는 별도 실행하지 않았고 실제 API/발행 소비 경로는 위 Agent E2E로 검증했다.
- **미검증:** 운영 Grafana/LLM/DB·동일 운영 데이터 전후 시간·원본 물리 저장량·실사용자의 판단 품질. 기간 이전 미해결 사건을 별도 조회하거나 이전 결과를 재작성하지 않는다. 합성 자료의 조회 수 감소를 운영 속도 향상률로 대체하지 않는다.


## 동일 합성 자료의 이전/수정본 비교

[재현 스크립트](tests/benchmark_operator_report.py)로 `9707b15`의 Ops/shared와 수정본을 비교했다. 24시간·15초 표본, GPU 연결 Pod 1개와 같은 Namespace의 일반 Pod 99개, 사건 1개, 각 3회 중앙값이다. 첫 시나리오는 기존 기본 O01/O08/O11과 새 기본 O01/O05/O08/O11을 비교하고, 나머지는 같은 단독 주제의 전후를 비교한다. 시간은 다른 부하 검사 종료 후 순차 측정했다.

| 시나리오 | 원격 지표 호출 | evidence snapshot JSON | 결과 JSON | 로컬 수집+계산+고정 설명 |
|---|---:|---:|---:|---:|
| 기본 보고서 | 19 → 19 | 825,615 → 825,615 B | 158,399 → 143,090 B | 3.401 → 3.579초 |
| O01 장비 단독 | 17 → 5 | 10,440,954 → 518,390 B | 35,293 → 14,510 B | 5.400 → 3.159초 |
| O05 장애 단독 | 2 → 0 | 207,762 → 264 B | 6,908 → 4,850 B | 0.0378 → 0.0004초 |

기본 보고서 설명은 4,157 → 1,439자(-65.4%), 결과 JSON은 9.7% 감소했다. 기본 조회와 원본 크기는 동일하며 처리 속도는 개선되지 않았다(+5.2%). O01 원본은 약95.0%, 로컬 처리 약41.5% 감소했지만 호출 차이는 이 fixture의 D06 분할 호출까지 포함한다. O05의 0회는 원격 지표만이며 기존 DB 사건·공개 RCA·조치 조회는 유지한다. DB context는 고정 fixture라 O05 시간은 실제 DB 조회 비용을 포함하지 않는다.

공통 주제의 계산값·단위·대상·기간·산식·품질·주제 상태·누락 사유는 정확히 일치했다. 새 evidence UUID·참조 수·수집 메타데이터·확인 문장 및 새 기본의 O05 추가는 동일성 대상이 아니다. 압축 전 JSON 바이트는 PostgreSQL 물리 용량이나 네트워크 전송량이 아니다. 운영 Grafana/MCP 전송·LLM·DB·Pod 메모리의 개선률로 해석하지 않는다.

재현은 스크립트 상단의 PYTHONPATH 예를 따르며 `--scenario equipment` 또는 `--scenario incidents`로 단독 주제를 비교한다. 측정 원본·전체 검사 XML·합성 미리보기는 `.local/operator-report/`의 로컬 검수 자료로 PR에 포함하지 않는다.

---

# 2026-10-12 보고서 D09/D13 제거·D06 Pod 범위 축소 — 로컬 검수

- 시작 원격 main `4ddeff1`, 종료 확인 시 추가된 RCA UI PR #103의 `bc2577d`를 fast-forward로 반영했다. Agent/공통 Python은 두 main 사이에 변경이 없다. 검수 당시 브랜치는 `fix/report-collection-pruning`의 로컬 수정 상태였다. 이후 사용자 요청으로 같은 변경의 PR을 준비한다. 운영 배포·데이터 변경은 하지 않았다.
- 구현: Ops O05/O06/O10이 계산에 사용하지 않는 D09/D13을 계획·부가 참조에서 제외하고 생략 사유를 표시한다. 기존 namespace 축소가 허용된 통합 binding의 O08 및 기본 조합에서 완전한 기간·GPU/Namespace/Pod/Node 단서가 있을 때 D06 Pod 이름을 추가 제한한다. UID/Node 필터는 걸지 않아 재생성·충돌·이동 판단을 보존한다. 다른 D06 소비 주제 혼합·누락 신원·과대 정규식은 기존 범위다.
- 전체 Agent 검사 **1077 passed / 0 skipped**, 109.19초. 기존 MCP deprecation warning 3건. Python 3.11.16, 외부 DB 변수를 제거한 임시 loopback PostgreSQL, 최신 소스에서 빌드한 JC/Incident/Backend와 실제 두 Worker·공식 MCP를 사용했다. Grafana/LLM은 fixture다. 최초 sandbox의 loopback bind 제한을 해소했고, 제거된 로그를 기대하던 기존 계획/E2E assertion을 수정한 후 전체 통과했다.
- 새 회귀: 같은 Namespace의 CPU Pod 제외, UID 충돌·재생성, Node 이동, 관측 공백, 라벨 누락·부분/빈 응답·기간 누락·과대 필터 fallback, 정규식 escaping, scope별 캐시 분리, RCA의 기본 무필터 수집. 사건 수·실제 신원 관계·조치 전후 에너지의 값/단위/방법/상태/누락 사유가 제거 전과 일치한다. 새 evidence UUID·사용하지 않는 로그 참조·수집 메타데이터·설명 문구는 동일성 대상이 아니다.
- Ruff check/format, 문서 링크, diff 공백 검사 통과. Go/Frontend 구현·DB schema·Helm 값은 변경하지 않았다. 해당 모듈 전체 unit suite는 이 변경의 별도 필수 대상으로 잡지 않았으며 발행·API/export 소비는 Agent E2E에서 검사했다.

## 같은 24시간 자료의 baseline/main 대조

[재현 스크립트](tests/benchmark_report_pruning.py)를 baseline `bc2577d`에서 추출한 Ops/shared Python과 수정본으로 각각 실행했다. 24시간·15초 표본, 같은 Namespace의 GPU 연결 Pod 1개와 일반 Pod 99개, 로그 query당 1000개 합성 줄을 사용했다. 각 3회 중앙값, 측정은 다른 검사 종료 후 순차 실행했다. 원본 크기는 **압축 전 JSON 바이트**이며 PostgreSQL 물리 저장량·네트워크 시간·실제 소스 부하가 아니다.

| 항목 | 이전 | 수정 후 |
|---|---:|---:|
| 기본 O01/O08/O11 실제 수집 호출 | 19 | 19 |
| 기본 D06 응답 JSON | 9,922,564 B | 99,727 B |
| 기본 전체 응답 JSON | 10,643,388 B | 820,551 B |
| 기본 저장할 evidence snapshot JSON | 10,643,632 B | 820,795 B |
| 기본 수집 처리 | 2.337초 | 0.160초 |
| 기본 수집+계산+고정 설명 처리 | 7.057초 | 3.264초 |
| 기본 결과 JSON | 약 157,756 B | 약 158,315 B |
| 확장 O05/O06/O10 실제 수집 호출 | 20 | 18 |
| 확장 evidence snapshot JSON | 11,039,703 B | 10,545,581 B |
| 확장 수집+계산+고정 설명 처리 | 3.121초 | 3.098초 |

기본 원본 저장 크기 약 92.3% 감소, 로컬 처리 약 53.7% 감소. 기본 계산값·자료 부족 판정은 같고 결과 JSON은 조회 범위 메타데이터 때문에 약 0.6KB 늘었다. 호출 수는 같아도 불필요한 Pod 표본을 덜 읽는다. 확장 조합은 D06 범위를 유지해 로그 원본만 약 4.5% 줄었고 처리 시간 차이는 약 0.7%로 유의미한 속도 개선이라고 주장하지 않는다. 두 시나리오 모두 모든 계산값·단위·방법·상태·누락 사유 대조 통과.

재현: baseline의 `ops-agent/ shared/python/`을 `.local/report-pruning/baseline/`에 추출한 뒤 스크립트 상단의 PYTHONPATH 실행 예를 따른다. `--scenario extended`로 확장 조합도 실행하고 같은 시나리오의 이전 JSON을 `--compare`에 전달한다. 로컬 비교 파일은 `.local/report-pruning/`, 전체 test XML은 `.local/report-pruning-tests.xml`에 남긴다.

**미검증:** 운영 Mimir/Loki/DB 조회 시간·실제 보고서 생성 시간·Pod 메모리 감소, 실제 LLM 설명 품질. 기존 evidence/보고서는 그대로이며 과거 용량을 자동 축소하지 않는다. 원천 집계·연속 표본 압축·공유 중복 저장 제거는 이번 범위가 아니다.

---

# 2026-10-12 수집 최소화·삭제 기능 최종 검수

- 원격 main `029fbed`를 작업 시작·종료 시 재확인했다. 작업 브랜치는 `fix/minimal-report-evidence`이고 커밋·PR·운영 배포·실제 보고서 삭제는 하지 않았다.
- 최종 전체 Agent suite **1050 passed / 0 skipped**, 기존 MCP deprecation warning 3건(110.53초). 외부 DB 환경변수를 제거하고 새 loopback PostgreSQL 16.9, 최종 소스에서 빌드한 Backend/JC/Incident, 실제 두 Worker와 공식 MCP를 사용했다. Grafana/LLM은 합성 응답이다.
- 실제 보고서 발행→Backend 삭제→JC 전용 DB 자료 제거→Ops 프로세스 파일 정리까지 통과했다. 같은 삭제 재전송, 목록 제외·작업 이력 보존, export 410, 다른 후보 보존, 0바이트 삭제 표식, 파일 정리 완료 상태를 확인했다. 초기 테스트의 응답 전체 비교는 매 요청 바뀌는 request_id를 제외하도록 바로잡았다.
- 삭제 표식과 POSIX 부모 디렉터리를 fsync한 뒤 완료 처리한다. flush 실패 시 failed로 남기고 재시도해 complete로 전환하는 회귀도 통과했다. 운영 NetApp RWX에 대한 쓰기·삭제 검수는 수행하지 않았다.
- Shared/JC/Backend/Incident vet·race·build와 Backend/Incident 격리 DB E2E 통과. Backend/JC 삭제 경합·마이그레이션 검수는 각 QA 문서에 기록했다. API 테스트의 첫 sandbox 포트 제한은 로컬 테스트 서버 실행 허용 후 통과했다.

---

# 2026-10-12 삭제한 보고서의 Ops 파일 정리 — 로컬 검수

- 구현: JC의 `report_deletions` 기록에 있는 종료 보고서만 Ops Worker가 30초마다 최대 1건 정리한다. DB 본문 삭제와 파일 정리 상태는 분리하며, 여러 Ops Pod는 행 잠금과 `SKIP LOCKED`로 같은 대상을 동시에 맡지 않는다. RCA와 공통 Python Worker의 실행 코드는 변경하지 않았다.
- 통과: `test_report_cleanup.py` **15개**와 `test_report_cleanup_e2e.py` **1개**, 합계 **16 passed**. 후자는 외부 DB 환경변수를 제거하고 새 loopback PostgreSQL 및 현재 트리에서 빌드한 JC로 보고서 접수→취소→삭제, 정리 실패→재시도 성공, 동시에 들어온 정리 요청의 잠금 건너뛰기를 검사했다. 운영 DB/PVC는 사용하지 않았다.
- 경로 회귀는 정규 UUID, 상위 심볼릭 링크 거절, 하위 링크의 외부 파일 보존, 누락된 저장소 루트, 지연 저장 스레드, 디렉터리 재생성 경쟁, 취소 시 파일 작업 종료까지 잠금 유지, 마이그레이션 미적용 중 분석 루프 지속을 포함한다. 정리한 경로의 0바이트 파일은 늦은 쓰기가 디렉터리를 다시 만들지 못하게 하는 삭제 표시이며 보고서 내용은 포함하지 않는다.
- 통과: Ops 및 두 정리 테스트 파일의 Ruff check/format. 실제 보고서 발행 후 Backend/JC/Worker 삭제 연동은 전체 `test_e2e.py` 검증 기록을 따른다. 실제 RWX 볼륨·다중 Kubernetes Pod·운영 삭제는 이 로컬 검수로 확인하지 않았다.

---

# 2026-10-12 RCA 숫자 거절 진단 및 수정 요청 예산

- RCA synthesis만 수정했다. 거절된 필드의 해시·길이·숫자 위치를 기록하며 원문이나 숫자 값은 저장하지 않는다. 수정 요청의 출력 상한은 실제 LLM 전송 계층과 동일하게 남은 예산에 맞춘다. 예산 부족과 시간 만료를 별도 진단한다.
- 로컬 검증: Python 3.11, UTF-8 환경의 전체 비 E2E Agent 검사 **976 passed / 36 deselected**. 실제 LLM 전송 클래스의 합성 HTTP 검사는 출력 상한 일치를 확인했다.
- 추가 E2E **1 passed / 26 deselected**: 새 loopback PostgreSQL, 현재 JC·Incident 실행 파일, 실제 RCA Worker와 공식 Grafana MCP를 사용했다. 합성 Grafana/LLM으로 숫자 응답 거절 → 수정 1회 → 결과 발행 및 hash 일치 → 진단 보존을 확인했다.
- 운영 DB·배포·Runbook 발행 상태는 변경하지 않았다. 과거 거절 응답 원문은 복원할 수 없으며 실제 모델의 새 RCA 검수는 배포 후 필요하다. 로컬 합성 검사는 운영 분석 품질 검증이 아니다.

---

# 2026-10-12 기본 보고서 E2E의 CI 기본 경로 수정

- PR #96과 머지된 main `eccb662`의 GitHub Actions에서 새 보고서 E2E가 `KeyError: BACKEND_BINARY`로 실패했다(1 failed / 1005 passed). CI는 `.local/backend-e2e`를 빌드하지만 해당 선택 환경변수를 지정하지 않는다. 이전 로컬 검증은 변수를 지정하여 이 차이를 놓쳤다.
- `test_e2e.py`의 해당 테스트만 기존 사례와 같은 기본 경로 처리로 수정했다. 환경변수가 있으면 사용하고 없으면 `.local/backend-e2e`(Windows는 `.exe`)를 사용한다. 제품 코드·워크플로·테스트 통과 기준은 변경하지 않았다.
- 재검증: 기본 경로에 Backend를 새로 빌드하고 `BACKEND_BINARY` 및 외부 DB 환경변수를 제거한 상태에서 `RUN_AGENT_E2E=1` 전체 **1006 passed / 0 skipped**, 기존 MCP deprecation warning 3건. 임시 loopback PostgreSQL·실제 두 Worker·현재 서비스 실행 파일·공식 MCP를 사용했으며 Grafana/LLM은 fixture다. Ruff check/format·문서 링크·diff 검사 통과.
- 범위: 운영 배포와 실환경 분석 검증이 아니다. 실패한 main 실행에서는 이미지·차트 발행이 건너뛰어졌다. 수정 PR의 원격 CI와 머지 후 발행 성공은 별도 확인 대상이다.

---

# 2026-10-12 기본 운영분석 O01·O08·O11 — 로컬 검수

- 기준: 원격 main `a0fcae2`에서 `feat/default-operations-report`로 로컬 변경했다. 기본 선택은 O01/O08/O11이며 기존 O와 저장 결과는 유지한다. `report-namespace-v2`/criteria 1.3에서 시간대별 Namespace 활동률·동시 연결 GPU 수·연속 저활동, Fleet 기록 시각, D10/D22 수집 상태를 추가한다. 기존 criteria 1.2 계산은 유지한다.
- 통과: 전체 Agent suite **1006 passed / 0 skipped**, 기존 MCP deprecation warning 3건. `RUN_AGENT_E2E=1`로 임시 loopback PostgreSQL, 현재 트리의 Backend/JC/Incident, 실제 두 Worker와 공식 Grafana MCP를 실행했다. Grafana/LLM은 합성 fixture이며 운영 데이터·슬롯은 사용하지 않았다.
- 통과: JC/Backend/Incident Go vet·race·build, 임시 DB의 Backend 전체 E2E, Helm 렌더링·패키징·잘못된 설정 거절, CI unittest 22개. 새 v2 발행·hash·CSV/HTML, 구 v1 호환, Namespace 이동·관측 공백·모델 분리·시간 경계·null/0 차이 및 고유 metric ID를 검사했다. 브라우저에서 발견한 모델별 미관측 시간대 누락도 수정하고, null 시간대를 보존해 그래프가 공백을 가로질러 연결되지 않는지 확인한 후 전체 suite를 재실행했다.
- 범위: RCA 분석·슬롯 배분·DB 구조는 변경하지 않았다. 공통 artifact 출력은 report criteria 1.3에만 새 열을 적용한다. 기존 일정의 선택 주제와 접수된 작업은 보존하지만 배포 후 새로 접수되는 일정 회차는 새 Backend 기본 프로필을 사용할 수 있다.
- 미검증: 운영 배포, 실제 D 바인딩과 수집량·시간 개선, 실제 보고서의 해석 품질. 새 기본 구성의 D 합집합은 11종이며 실환경 호출 횟수·전송량 감소를 측정한 것은 아니다.

---

# 2026-10-08 D20 Node condition JSON — 로컬 검수

- 기준: 원격 `origin/main` `854a030`(#92 포함)에서 `fix/report-node-condition-json`을 생성했다. 제품 코드는 Ops의 `additional_inputs.py` 한 줄만 변경한다. O01의 D20 관측 구간을 JSON 배열로 구성하며 공통 정규화·해시/결과 검증·Worker·RCA·JC·DB·수집 설정은 유지한다.
- 수정 전 재현: 실제 `prepare_result()`를 호출하는 6개 사례 중 유효 D20 gauge/info 2개가 `ValueError: not JSON`으로 실패했고, 빈 응답/조회 실패 4개는 통과했다. 수정 후 6개 모두 통과한다. 합성 두 클러스터·두 Node의 라벨, 시각 구간, 0/1 값, evidence 참조, 원본 불변, JSON 왕복/해시와 기존 주제 상태를 확인했다.
- 통과: 관련 binding/cluster parameter 검사 **102 passed**. 전체 Python Ruff check/format와 `git diff --check` 통과. 저장소 링크 검사는 116문서·1,380개 링크/자산·오류 0건.
- 통과: Python 3.11.16에서 `RUN_AGENT_E2E=1 python -m pytest -c agents/pytest.ini agents/tests -q` 전체 **701 passed, 0 skipped**(95.31초), 기존 MCP deprecation warning 3건. `DATABASE_URL`, `AGENT_E2E_DATABASE_URL`, `E2E_DATABASE_URL`을 제거하고 임시 loopback PostgreSQL 16.9를 생성했다. Go 1.26.2로 현재 트리에서 새로 빌드한 JC·Incident·Backend와 실제 두 Worker·공식 Grafana MCP 1.4.2를 사용했다. Grafana/LLM 응답은 합성 fixture이며 운영 서비스에 연결하지 않았다.
- 통과: 기존 두 Worker binding E2E 6개 사례에 D20을 추가했다. 활성 literal/parameter/discovery binding에서 두 Node의 Ready true=1/false=0 총 4개 관측과 각각의 120개 30초 구간, 저장된 D20 evidence ID, JC 발행 결과와 content hash를 확인했다. 비활성 binding은 빈 관측과 무조회 동작을 유지한다. 이 사례들은 전체 701개에 포함된다.
- 독립 검토: 직접 결과로 나가는 D20 구간을 Ops 구성 지점에서 변환하는 범위가 적절하며, 추가 수정이 필요한 결함을 찾지 못했다. Backend/Frontend가 읽는 JSON 필드와 결과 스키마는 변경되지 않는다. Frontend 단독 suite와 Go 단독 vet/race suite는 이번 Python 결과 구성 수정에서 실행하지 않았으며, 실제 Backend/JC 소비는 위 프로세스 E2E로 검증했다.
- 미실행: 운영 배포·실제 D20을 수집한 새 보고서의 재검증. 배포 후 O01 포함 및 전체 주제 새 보고서에서 D20의 유효 관측, 최종 발행·근거·내보내기·슬롯 반환을 확인해야 한다. 과거 실패 작업은 재작성하지 않는다. 실제 운영 예외 traceback은 없으므로 운영 로그 조건이 재현 결함과 일치한다는 판단과 코드 결함 재현을 구분한다. MCP 통신 오류·공통 Worker 상세 오류 로깅은 이번 수정 범위가 아니다.

---

# 2026-10-08 O01 optional metric IDs — 로컬 검수

- 기준: 최신 원격 `origin/main` `125e06e`에서 `fix/report-metric-ids`를 생성했고 최종 fetch에서도 같은 기준을 확인했다. 제품 코드 변경은 Ops의 `additional_inputs.py`에 한정한다. 항목별 순번을 붙여 `O01.<metric_name>.<순번>`을 생성하고 값·단위·target·기간·근거·부족 사유는 유지한다. 공통 검증·Worker·RCA·JC·DB·수집 설정은 변경하지 않았다.
- 재현: 합성 2개 클러스터에서 메모리 여유량 18행, CPU 4행, load 시간창 12행, 메모리 사용 비율 18행을 계산했다. 같은 target의 별도 원천 시리즈를 추가한 53행 사례도 포함한다. 수정 전 두 사례 모두 실제 `prepare_result()`의 `duplicate value id`로 실패했고, 수정 후 행/값/단위/대상/근거와 CSV ID를 보존하며 통과했다. 이 행 수는 합성 입력이며 운영 장비 수를 뜻하지 않는다.
- 통과: Python 3.11.16에서 `RUN_AGENT_E2E=1`로 전체 `python -m pytest -c agents/pytest.ini agents/tests -q` 실행: **695 passed, 0 skipped**, 기존 MCP deprecation warning 3건. 테스트 전 `DATABASE_URL`, `AGENT_E2E_DATABASE_URL`, `E2E_DATABASE_URL`을 제거하고 임시 loopback PostgreSQL 16.9, 현재 트리에서 빌드한 JC/Incident, 실제 두 Worker와 공식 Grafana MCP를 사용했다. Grafana/LLM은 합성 fixture이며 운영 시스템에는 연결하지 않았다.
- 통과: 기존 binding E2E 6개 사례를 다중 GPU·Node·load 창으로 확장했다. 활성 binding은 4종 지표 2/2/6/2행의 고유 ID·값·target·근거와 DB 후보 저장/JC 공개를 확인하며, 비활성 binding은 단일 null 행과 무조회 동작을 유지한다.
- 통과: 전체 검사 중 기본 Backend 실행 파일을 사용하는 5개 API 연동 사례는 현재 트리의 Backend를 별도 빌드한 뒤 다시 실행했다(`test_namespace_report_through_backend_with_report_only_criteria`, `test_gui_model_auth_and_pinned_revision_reach_real_worker`, `test_runbook_api_lifecycle_and_real_rca_consumption`): **5 passed / 20 deselected**. 새 임시 DB로 보고서 접수·HTML/CSV 내보내기 및 관련 Worker 연동을 확인했다.
- 통과: Frontend 포맷·**184 tests / 17 files**·TypeScript/Vite 빌드. Backend `go vet ./...`, `go test -race ./...`, `go build ./...`. 최초 Backend race 검사의 sandbox loopback bind 제한은 승격 후 동일 검사를 통과해 해소했다. Backend 자체 `-tags=e2e` 전체 suite는 별도로 실행하지 않았으며 위 Agent API 통합 검사와 구분한다.
- 통과: 구형 ID/`.0`/`.17` ID에서 네 항목의 한글명·0/null·단위와 CSV 원문 보존 검사, 전체 Python Ruff check/format, 저장소 링크, `git diff --check`. Frontend/Backend 제품 코드는 변경하지 않고 기존 소비자 테스트만 확장했다. 독립 코드 검토에서 추가 수정 사항은 발견되지 않았다.
- 미실행: 운영 배포 및 새 3개 주제/11개 주제 보고서의 실환경 재검증. 배포 후 기존 실패 요청과 같은 범위의 새 요청으로 발행·슬롯 반환을 확인해야 한다. 과거 실패 작업·결과는 재작성하지 않는다. 오전 자동보고서 timeout, D21/D22 조회 실패, 공통 Worker 상세 오류 로그 개선은 이번 검증/수정 범위에서 제외했다.

---

# 2026-10-08 RCA final-editor repair — 검증 범위

- Passed: 658 non-E2E Agent tests / 35 deselected. Includes bounded selection repair,
  safe failure reasons, rejected-prose exclusion, cancellation/remote uncertainty,
  and the unchanged single-attempt Ops default.
- Passed: four selected Backend/JC/Worker/official-MCP integration cases / 21 deselected,
  using a new localhost PostgreSQL instance with external database variables removed.
  Grafana and LLM responses are fixtures; this is not live RCA quality validation.
- Production Runbooks: nine reviewed transition revisions have been published via
  Backend API. Eight were re-read and selected with local Worker code. Only XID79 r3
  has a new live RCA selection/result-publication check. See the [publication record](../rcca-agent/runbooks/REVIEW-20261008.md).
- Pending: deploying the editor change and checking a new live result; event-source
  completeness; eight error-specific live RCA checks; remaining 258 Runbook transitions.
  Historical editor rejection cannot be assigned a precise cause from the stored flag.

# 2026-10-08 Runbook PR preparation — 검증 범위

- Passed: full non-E2E Agent regression, `pytest -c agents/pytest.ini agents/tests -m "not e2e" -q`: 623 passed / 35 deselected in 26.75s on the final PR candidate. The refinement plus Fleet parser regressions also passed 23 targeted tests, including two new time-gate cases.
- Passed: four selected Backend/JC/Worker/MCP integration cases in `test_e2e.py`: Runbook API lifecycle and real Worker consumption, no-published-Runbook RCA variants, and report topic/Runbook-sufficient behavior. Current-tree Go binaries, temporary localhost PostgreSQL 16.15 and the available official MCP executable were used; external DB variables were removed. Grafana observations and model replies were fixtures. No production jobs or slots were used.
- Initial integration failure: the v7 fixture lacked D33/D34/D44 used by current draft plans. Added explicit synthetic queries in the test stack, then reran all four selected cases: 4 passed / 21 deselected in 34.93s. Other E2E cases were not run for this change.
- Passed: whole Python Ruff check/format; repository links; catalog authoring audit: 267 structurally valid, all 267 retain Fleet time-gated required facts. The audit now names those facts, including error_code-only requirements, without granting approval.
- PR scope: contract diagnostics, local audit, nine Runbook investigation-plan/limitation updates and final-editor fallback diagnostics. Fleet event-time/health semantics activation, operational Runbook approval/publication and live RCA completion remain outside the verified outcome. The production nine-draft registration described below remains unapproved.

# 2026-10-08 Runbook draft registration — 운영 초안 등록

- Passed: owning Backend API registered nine new draft revisions under existing knowledge IDs. XID 79 is revision 3; XID 32, 48-63-64, 54, 63, 64, 74, 163 and SXID 11001 are revision 2. Fresh GETs matched draft state, content, content hash and compatibility to the submitted inputs.
- Passed: existing target published revisions retained state, content hash, version and publication/review hash fields. No approval, publication, retirement, SQL mutation, job/slot operation or Worker restart was performed.
- Boundary: this verifies live draft persistence only. Earlier 238 tests remain fixture validation; operational RCA, Fleet state/time semantics and concurrent slot behavior are unverified here. Private receipts are excluded from Git. See [review details](../rcca-agent/runbooks/REVIEW-20261008.md).

## Offline Runbook diagnostics — 2026-10-08

Isolated worktree based on `9f632989`; no production DB/API requests, deployment, publication, or revision retirement.

- Runbook selection retains `invalid_contract` and adds a validator-owned first-failure reason. Offline audit shares the runtime content/hash validator; unrelated-but-valid books are not contract failures.
- Saved published snapshot: 268 revisions; 1 content-contract pass, 267 failures at unregistered/disallowed observation query. All 267 rejected revisions retain D05. This is a cached snapshot audit, not a new live DB inventory.
- Repository authoring inputs: 267/267 pass. Empty compatibility is allowed in authoring mode; this does not authorize publication or establish content/source validity.
- RCA report fallback now records editor configuration/response/exception reasons separately from synthesis. It still preserves every supplied statement and remote-call fencing. No historical result is rewritten; the exact historical editor failure is not established by this change.
- Static review inventory: all 267 drafts retain unbound compatibility and the unverified Fleet observation-time gate. Manifest classification is 187 documented, 63 unused/legacy, 13 conflicting, 3 source-only; the generic book is outside that error manifest. These are review tasks, not automatic approval. XID 79 now distinguishes collected Fleet observations from separately required kernel/PCIe originals.
- Follow-up: [offline review](../rcca-agent/runbooks/REVIEW-20261008.md) records cached Fleet source boundaries and XID 48/63/64/SXID 11001 collection gaps. Draft limitations now explicitly preserve these gaps. No time semantics flag or binding was promoted.
- Validation: 238 focused Runbook/import/retrieval/Fleet/RCA analysis/report and binding contract/discovery tests passed; Ruff passed; documentation links passed. Added fixtures cover repeated old-state reporting, unverified GPU inventory, unsupported disk health adaptation and successful synthesis preservation when the final editor rejects empty/unknown IDs or prose. Tests use local fixtures, not live Grafana/LLM or a database.
- Full plan inventory: 266 drafts use D02/D09 and one uses D02/D03/D09. The ten manifest evidence groups are compared with their additional evidence needs in the review document. Rejected saved revisions now retain independent review findings: 267 identify D05 explicitly; structural failure does not hide migration work. This does not validate each vendor procedure or turn missing sources into available observations.
- Subsequent plan changes: XID 54 adds optional D11; XID 163 adds optional D04/D11 before D02. Six fixture Worker runs verify samples/empty/failure paths preserve missing health and withhold confirmed causes/actions. Two current-profile checks verify arbitrary cluster parameters, units, and candidate blocking. The Worker runs use the v7 test profile; current-profile discovery and production execution remain unverified. No CPC-specific runtime branch or profile change was introduced.
- PCIe/NVLink follow-up: XID 32/79 add optional D44; XID 74 adds optional D33/D34. Nine more Worker fixture cases preserve uncertainty under samples/empty/failure. Three more current-profile checks cover units and candidate blocking. The replay counter is not converted into event counts and NVLink rates do not prove endpoint topology. D07 remains unchanged because O07 still consumes it.
- Current-profile follow-up: 15 Worker cases now also run with the unmodified common config and mock MCP discovery, checking cluster/GPU/node selectors and binding provenance. Ten collection checks reject missing GPU label configuration or ambiguous datasources before metric calls. Production discovery and physical device identity are still unverified; no DB was accessed.
- Remaining: source-by-source Fleet time/health semantics review; substantive Runbook content review; precise live report-editor failure verification; Backend/JC integration and real-system verification after the DB hold ends. Do not set `loki_timestamp_is_observed_at=true` merely to make required facts pass. No claim that state facts, all Runbooks, or operational RCA are fully verified.
# 2026-10-08 종류별 독립 실행 용량 — 두 Worker 회귀

- 기준: 원격 main `5570a0e`, `feat/independent-agent-capacity`. JC의 종류별 배분 조건과 선택 Helm 구성을 바꿨으며 RCA/Ops 분석 코드와 공통 Python Worker는 변경하지 않았다.
- 통과: Python 3.11.16(지원 범위), PostgreSQL 16.9, Go 1.26.2, 공식 Grafana MCP 1.4.2에서 `RUN_AGENT_E2E=1 .venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/independent-capacity/agents-results.xml` — **598 passed / 0 skipped, 89.32초**, 기존 MCP deprecation 경고 3건. `PG_BIN`, `GRAFANA_MCP_BINARY`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `HELM_BINARY`는 로컬 도구/새 빌드 경로를 지정했고 외부 DB 환경변수를 제거했다. 새 localhost 임시 DB·실제 두 Worker/NAT/JC/Incident/Backend/공식 MCP 프로세스와 Grafana/LLM 응답 fixture 검사다.
- 통과: `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`와 동일 경로 `ruff format --check`. 종류별 3+3 인수·한도·늦은 결과 거절 및 Helm 검수는 [JC 검증 기록](../job-controller/QA.md)을 따른다.
- 미검증: 실제 Kubernetes 6개 Agent Pod 동시 발행, 기존 RWX claim의 mount/쓰기, 운영 Dynamo/Mimir/DB 부하. 전체 Worker 회귀는 6개 실제 Pod 부하 시험이 아니며 실제 모델의 잔여 추론 종료도 증명하지 않는다. 위 로컬 검수 시점에는 커밋·푸시·PR·운영 배포·운영 DB/PVC 변경을 수행하지 않았다.

# 2026-10-07 D07/D13 source contracts — 원문 조회 보존

## 2026-10-07 실패 보고와 실행 슬롯 반환 회귀

**통과:** `.venv/bin/ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`, 동일 경로 `ruff format --check`; `RUN_AGENT_E2E=1 .venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/slot-release/agents-results.xml` — **598 passed**, MCP SDK deprecation 경고 3건. Python 3.11.16(지원 범위, CI는 3.12), PostgreSQL 16.9, Go 1.26.2, 공식 Grafana MCP 1.4.2. `PG_BIN`과 JC/Incident/Backend/MCP 바이너리를 로컬 도구 경로로 지정하고 운영 DB 환경변수를 제거했다. 격리 DB·실제 양 Worker/NAT/MCP 프로세스와 Grafana/LLM 응답 fixture를 사용했다.

혼합 예외 그룹·cleanup 오류가 fail 보고를 건너뛰지 않는지, 정상 complete 뒤 fail을 보내지 않는지, 외부 취소·치명적 종료 신호 전파, 원격 상태 보존, 후속 작업 완료를 RCA/report에 확인했다. 저장 중 heartbeat·취소/만료/시도 교체 rollback과 기존 보고서/RCA 계산 회귀 포함. 초기 sandbox에서는 임시 서버 bind/shared-memory 권한으로 실패했으며 격리 로컬 실행을 허용한 뒤 전체 통과했다.

**미검증:** 운영 Worker 종료의 실제 원인, 실제 Dynamo 요청의 종료·지속 시간·중첩 부하. 이 변경은 원격 종료를 입증하지 않으며 새 JC는 unknown을 기록한 채 실행 슬롯을 반환한다. **미수행:** 배포·운영 DB 변경. 원격 CI는 PR 제출 후 별도 확인한다.

- 기준: main 8bd727e, 공통 cluster_id와 MCP 탐색 유지. D13 원문 로그 문맥 binding을 추가하고 업무/상태 fact 승격을 차단한다. 미검증 대상 필터는 전체 클러스터로 확대하지 않는다. D07은 기존 scheduler 원천을 먼저 검토하며 별도 서비스 설치를 전제하지 않는다.
- 통과: Python 3.12, 격리 localhost DB, RUN_AGENT_E2E=1 전체 검사 580 passed / 0 skipped, 기존 MCP 경고 3건. 대상 별칭 차단 후 집중 검사 128 passed. Ruff, Helm 계약/패키징, CI helper 18개, 문서 109개/링크 1356개 오류 0건. 두 Worker E2E의 Grafana/LLM은 fixture다.
- 미검증: D07 scheduler 버전·실제 원천·UID/시간/상태 연결, D46 단위, 새 설정 배포와 실제 Worker 결과. 제공된 KSM Pod YAML은 D07 유효 요청량 존재를 증명하지 않는다.
- 상세: [D07/D13 원천 검토](../docs/evidence/d07-d13-source-review-20261007.md).

# 2026-10-07 Shared observation expansion — 공통 조회 확장

- 기준: main `566ec4a` (PR #81 병합), `feat/shared-observation-expansion`. 전체 45개 D를 대조했고 공통 profile에서 42개 관측 조회를 선택한다. 원래 exporter 후보를 보존하며 Fleet 대체 binding 11개를 추가했다. cluster registry는 비어 있고 이름·UID 고정이 없다.
- 실환경 읽기: Grafana instant inventory 118개 행과 메트릭/클러스터별 대표 표본 108개 행, 제공된 배포·CSV·Alloy 자료, Fleet 1.5.0-rc.1 및 DCGM 4.2.3/4.4.2 코드를 대조했다. Fleet의 시각은 gather 시각이며 하드웨어 측정 시각을 증명하지 않으므로 forward hold=0과 한계를 RCA 입력까지 보존한다. D17 ratio, D31~D34 rate gauge, ECC counter, raw enum/bitmask를 구분한다.
- 통과: Python 3.12, 격리 localhost DB, `RUN_AGENT_E2E=1` 전체 Agent 검사 **572 passed, 0 skipped**, 기존 MCP deprecation warning 3건. 두 Worker/JC/Incident/Backend/공식 MCP 프로세스와 fixture Grafana/LLM 검수이며 운영 활성화 완료 증거는 아니다. Ruff lint/format, Helm 계약·lint·패키징, CI helper **18 passed**, 추적 소스 링크 **108 documents / 1351 links / 0 errors** 통과. 최초 링크 사본은 Git 한글 경로 quoting 때문에 불완전했고 `ls-files -z`로 교정 후 통과했다.
- 남은 조건: D07 effective-v1 생산자, D13 workload 로그 의미, D46 단위 근거. 사용자가 동일한 공통 Alloy 전송 helper를 적용했고 실제 저장 표본 D12 720개, D35 120개, D49 135개를 재조회했다. 세 binding을 r2에 반영했다. D35가 없는 환경은 unknown이며 예외 분기가 없다. helper는 metric keep regex 하나만 비교 후 바꾸며 클러스터 라벨·Secret·PVC를 건드리지 않는다. D16 MiB 및 D15/D20/D22 추가 회귀를 포함한 후속 집중 검사 43개도 통과했다. 새 profile 배포·두 Worker 실제 결과·Runbook DB 발행과 전체 신규 분석 계산은 미검증이다. Ops invalid-result 사건 수정은 포함하지 않았다.
- 상세: [전체 관측 검수·공통 전송 절차](../docs/evidence/d-observation-expansion-20261007.md).

# 2026-10-07 Shared core observations — 로컬 검수

- 기준: main `0af217c`, `feat/rca-core-observation-bindings`. 기존 원장·표본·CSV·Alloy 경로를 재대조하여 D03/D06/D10을 공통 MCP 발견 계약으로 전환했다. 공통 JSON과 Helm 사본이 같으며 CPC 이름·UID 고정은 없다. 후보 40개는 유지한다. XID48 작성 원본에 선택 D03을 추가하고 필수 D09 상태 근거와 investigation_only를 보존했다.
- 통과: 루트 Python 3.12, `RUN_AGENT_E2E=1`, 격리 localhost DB에서 전체 `agents/tests`: **551 passed, 0 skipped**, 기존 MCP deprecation warning 3건. 두 Worker/JC/Incident/Backend/공식 MCP 프로세스와 fixture Grafana/LLM 검사다. 새 클러스터의 D03/D06/D10 자동 탐색·필터·단위·원본 값·RCA 입력 전달을 별도 검사했다.
- 통과: Ruff check/format, Helm lint/패키징/설정 사본 검사, CI helper 16 tests, 추적 파일과 신규 문서의 링크 검사 107 documents / 1347 links. CI helper 최초 실행은 Git Bash PATH 누락으로 실패했고 경로 지정 후 통과했다. Runbook 계획 검사는 기존 두 D 가정을 XID48 선택 D03으로 갱신한 뒤 전체 통과했다.
- 미검증: 새 공통 profile의 운영 배포·실제 Worker 결과, XID48 신규 DB revision 발행. D04/D11 의미 검토 및 D07/D12/D13 원천 연결은 남아 있다. 메모리 사용량·Pod 배치·scrape 상태를 장비 정상/오류 원인/직접 GPU 할당으로 승격하지 않는다. 이전 266개 발행 준비 목록은 실제 발행 전에 이번 XID48 변경을 포함해 다시 대조해야 한다.

# 2026-10-07 RCA Runbook 선택·보완 진단 — 로컬 검수

- 기준: main `9b634c8`, 브랜치 `fix/rca-runbook-diagnostics`. 발행 Runbook과 builtin 일반 템플릿이 함께 사용됐는데 보고서가 발행본 부재로 설명하던 오류를 수정했다. 선택/추가 조사 근거를 참조하고 normalized_health/unknown_value 설명을 추가했다. 판단·상태 fact·조치 적격성 계약은 변경하지 않았다.
- 통과: 저장소 루트에서 격리 localhost DB와 `RUN_AGENT_E2E=1`로 `python -m pytest -c agents/pytest.ini agents/tests -q`: **548 passed, 0 skipped**, MCP deprecation warning 3건. 실제 Worker/JC/Incident/Backend/MCP 프로세스와 fixture Grafana/LLM을 사용하는 회귀검사이며 운영 통합 검수와 구분한다. Ruff check/format 및 diff 검사 통과.
- 운영 읽기 검수: XID79 발행 revision 2 선택 → D09/D02 조회 → missing_evidence/unknown_value 일반 조사 보완 → partial 발행을 확인했다. 당시 선택 진단의 267개 invalid_contract를 현재 발행본에 대조했으며 모두 observation_plan 미등록/비허용 조회 검사에서 탈락했다. 저장소 원본 변경으로 DB 발행본이 갱신되지 않는 문제이며 무검토 일괄 발행으로 해결하지 않았다.
- 미검증: 수정 코드 운영 배포와 새 RCA 결과. 과거 불변 보고서·DB 발행본은 변경하지 않았다. producer 시각/상태 fact 검증과 기존 Runbook 새 revision 검토·발행은 남아 있다. Ops Report 실패 조사 범위는 포함하지 않았다.

# 2026-10-07 Shared binding MCP discovery — 공통 알림 경로 검수

- 기준: 원격 main `85eae1fc87056e0fff4326001b5e6439ee5ea117` (PR #78 병합). 이전 Worker 출력은 candidate/UID null로 D02·D09가 `binding_unselected`였으며, 발행 성공을 유효한 원인 분석으로 해석하지 않았다.
- 구현: 공통 `shared-grafana-discovery-20261007-r1`, D02·D09의 검토된 관측 계약만 활성화하고 나머지 43개는 차단한다. 요청 cluster_id → 승인된 후보 라벨 → 유일한 datasource UID를 MCP로 해석한다. 값 별칭·CPC 목록·CPC별 profile을 추가하지 않는다. Fleet machine_id는 JSON 수집 조건에 전달한다. 시각/health fact 제한은 유지한다.
- 검증 결과: 루트에서 `RUN_AGENT_E2E=1` 및 격리 localhost DB로 `python -m pytest -c agents/pytest.ini agents/tests -q` 실행: **544 passed, 0 skipped**, MCP deprecation warning 3건. 실제 Incident/JC/Backend/두 Worker·공식 MCP와 fixture Grafana/LLM을 사용했다. 임의의 신규 등록 cluster_id 알림 → Incident snapshot → JC → RCA 실제 발행, D02·D09의 UID/라벨/자동 선택 evidence, Report 발견 경로 및 후보 차단을 확인했다. 최초 전체 검사에서 발견한 machine_id JSON 조건 누락을 보완한 뒤 전체 재검사 통과.
- 통과: 전체 Python Ruff check/format, Helm lint/render/package와 source/mirror 계약, CI helper unittest 16개. Git Bash PATH 누락으로 처음 실패한 helper 검사는 경로 보완 후 통과했다. 추적 파일과 신규 문서만 복사한 트리에서 106개 문서·1341개 링크/자산 오류 0건(사용자 미추적 checkout 제외).
- 실환경 근거: [관측 계약 검토](../docs/evidence/d-binding-discovery-20261007.md). 기존 XID79 발행본의 D05 참조를 D09 계약으로 변경한 revision 2를 공식 검토·발행 API로 별도 게시하고 저장된 incident snapshot과 매칭했다. 정규화 health 요구와 investigation_only는 유지했다.
- 미검증: 새 코드의 운영 배포, 두 Worker의 실제 새 profile 적용 및 새 Fleet 사건의 조회·Runbook·결과 검수. Grafana/LLM fixture 검사는 실환경 인과 분석 품질을 증명하지 않는다. 기존 Helm 전체 override가 기본 설정을 가리는지도 배포 시 확인한다. 알림식의 CPC 확장과 Report invalid_result 수정은 이번 범위에서 제외했다.

---

# 2026-10-07 공통 cluster_id 파라미터 — 로컬 검수

- 기준: 원격 main `bfe59478c19701ac3aa254276d6956d7e1496416`과 작업 기준 일치 확인. 브랜치 `feat/parameterized-cluster-bindings`.
- 변경: CPC별 direct 전체 설정을 제거하고 공통 원본/Helm 사본의 45개 후보 binding에 `environment.scope_labels`를 적용했다. 요청 cluster_id를 정확 일치 selector로 주입하며 고정 범위·target 충돌과 누락값을 거부한다. 공통 verified source 계약은 `verification.applicability`가 필요하다. 기존 literal 설정 호환은 유지한다. `auto_select_verified_bindings`가 켜진 경우 유일한 verified 파라미터 후보만 자동 선택하고 명시적 선택/null·모호성 차단·대안 동등성 조건을 지킨다. 자동 선택 방식은 evidence에 기록한다.
- 통과: 루트에서 `python -m pytest -c agents/pytest.ini agents/tests -q`를 `RUN_AGENT_E2E=1`로 실행해 **518 passed / 0 skipped**, MCP deprecation warning 3건. 임시 loopback PostgreSQL 16.15, 실제 JC/Incident/Backend/두 Worker 및 공식 MCP를 사용했고 Grafana/LLM은 fixture다. `DATABASE_URL`과 외부 E2E DB 설정을 제거하여 운영 DB에는 연결하지 않았다. 파라미터/기존 literal·선택/미선택 조합의 두 Worker 결과 발행을 포함한다.
- 통과: 새 CPC 이름·특수문자 escaping·다중 CPC selector 분리·원본 설정 불변·누락 scope·정적 selector/target 충돌·후보 실행 차단·D20 gauge 소비와 기존 binding 검사 **94 passed**. 전체 테스트에 포함된다.
- 통과: `python tools/ci/check_chart.py`의 Helm lint/render/package, source/mirror 및 배포 계약 검사. `python -m unittest discover -s tools/ci/tests -v` **16 passed**. 전체 Python Ruff check/format 통과.
- 문서: 루트 `tools/check_links.py`는 사용자 소유 미추적 `_codex_dcgm_publish/frontend/index.html`의 Vite 경로 2건만 실패했다. 해당 디렉터리는 보존했으며 현재 추적 파일만 복사한 트리에서 **105 문서 / 1336 링크·자산 / 오류 0건**을 확인했다.
- 미실행: 운영 배포·실제 새 job의 조회 및 발행 검수. 공통 예제 binding은 모두 후보/미선택이며 기존 운영 Helm override는 변경하지 않았다. 신규 CPC 자동 발견·등록 기능은 이 파라미터 전달 변경에 포함하지 않는다. Report 발행 결함 수정은 사용자 요청으로 보류·분리했다.

---

# 2026-10-06 P1 환경 조사와 소비 차원 검증 — 후속 로컬 검수

- 기준: fetch 후 최신 `origin/main`과 로컬 HEAD `2849de1` 일치, PR #71 병합과 PR CI required 성공 확인. 후속 브랜치 `feat/binding-environment-validation`에서 작업했다. [실환경 조사 기록](../docs/evidence/d-binding-cpc-20261006.md)과 [90개 환경 항목 원장](../docs/evidence/d-binding-cpc-20261006.json)을 작성했다.
- **통과 — 실제 Grafana 읽기 조사:** CPC-1/CPC-2 각 28개 D 메트릭의 원본 표본과 D09 제한 로그 표본 확보. 각 15개 후보 이름은 조회 창에서 미관측, D13은 workload 원본 미확정으로 미조회. 이름·label·원본 표본 시간·관측 공백만 확인했으며 producer 버전/단위/invalid/reset/보존 정책의 의미 검증 완료를 뜻하지 않는다. 원본은 `.local/p1-binding/`에만 보관하고 민감 신원과 로그 본문은 원장에 포함하지 않았다.
- **통과 — 최신 main 통합:** 준비 중 추가된 PR #72의 `a3dd8c4`를 fast-forward로 반영했다. 변경은 Frontend 8개 파일이며 공통 설정·두 Worker·Go 서비스·이번 Python 검증본은 동일하다. 최종 원장/PDF 대조·문서 링크·Ruff·diff 검사를 수행했다. 이번 변경은 UI/API 결과 형식을 바꾸지 않아 main의 UI에 대한 별도 전체 재시험은 수행하지 않았다.
- **통과 — 소비 차원:** verified D19는 `window`, D20은 `condition/status` 매핑을 요구하고 신원 라벨과 중복된 원본 필드를 거부한다. Fleet의 실제 `load_duration` 형태를 재현한 합성 입력으로 O01의 기간별 분리 출력과 원본 snapshot 보존을 확인했다. 집중 계약 검사 74 passed.
- **통과 — 전체 두 Worker 회귀/E2E:** 루트 Python 3.12에서 `RUN_AGENT_E2E=1`로 `python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/p1-binding/agents-results.xml`: **496 passed, 0 failures/errors/skips, 140.84초**, 기존 MCP deprecation warning 3건. 외부 DB 환경 변수를 제거하고 임시 loopback PostgreSQL, 로컬 JC/Incident/Backend/공식 MCP/두 Worker 바이너리를 사용했다. 이 테스트의 Grafana/LLM은 fixture이며 위 실제 읽기 조사와 구분한다.
- **통과 — 정적/원장:** 변경 Python 2개 파일 Ruff check/format, PowerShell 읽기 조회 스크립트 문법, 45 D × 두 cluster의 누락/중복 검사, 정상 export 해시 대조, 미선택 상태와 공통 JSON/Helm 사본 byte 일치. JSON SHA-256은 기존 `85b348a142b7656a7e35058995131bbecd4a0d1b8cddf9c7bde03e28ed3bd932`를 유지한다. Helm lint/render/package와 설정 계약 검사는 통과했다. 문서 링크는 사용자 별도 checkout을 제외한 발행 대상 소스 복사본에서 검사했다. 임시 디렉터리의 최초 권한 오류는 권한을 맞춰 재검사했다.
- **통과/부분 — PDF 재검증:** [감사 기록](../docs/evidence/fleet-dcgm-pdf-audit-20261006.md)에 105개 대응표 번호, 9/31 분류, 267개 investigation-only 런북, 수량/차이 산술과 Fleet/Exporter tag 소스 정의를 대조했다. Fleet tag/digest 및 DCGM/Exporter tag는 사용자 출력으로 원장에 추가했다. 추가 첨부로 PDF의 metrics 수량/UUID 비교를 재현했고 표 420칸 중 419칸은 일치, 에너지 1칸은 오류로 정정 기록했다. 두 번째 환경 states 24개 중 3개는 time이 없으며 events null/빈 배열은 전체 이력 부재를 입증하지 않는다. image-to-source provenance는 미검증이다.
- **미완료/미검증:** KSM 버전·Exporter digest·collector/전송 설정 회신, 첫 환경의 이전 states/events 내용·원천 시각/이력 검증, 환경별 binding 활성화, 실제 두 Worker/LLM 결과 검수, 전체 신규/조건부 분석, 개별 Runbook 보완·발행. **검수 시점에는 로컬 수정·검수 단계였다. 사용자 요청으로 `feat/binding-environment-validation`의 후속 PR을 준비하며, 운영 활성화·배포는 별도 미완료 단계다.** UI/Go 공개 결과 형식은 변경하지 않아 해당 모듈의 별도 전체 suite는 해당 없음이며 실제 Go 서비스 연동은 위 Worker E2E에서 검사했다.

---

# 2026-10-06 D binding 전환 — 로컬 검수

- **PR 준비:** 최신 `origin/main` `3a273f9`를 반영했다. 추가된 UI 변경과의 통합 후 Frontend 포맷·**150 tests / 16 files**·빌드를 재검증했다. 공통 Python·두 Worker·Backend·설정은 위 main 반영 전 검증본과 동일하다. 사용자 요청에 따라 `feat/d-binding-runtime`에서 PR을 준비하며, 아래 로컬 단계 기록은 검증 당시 상태다.
- 기준: 원격 `main`과 로컬 HEAD `05bb4f69aec024ed72da72e266d63fa267be8f9a`, 사용자 확인 JSON `d-contract-restart-20261006-r1`. [구현 범위·전환 순서](../docs/specs/common/d-binding-runtime.md). 업로드 2개·공통 원본·Helm 사본 SHA-256은 `85b348a142b7656a7e35058995131bbecd4a0d1b8cddf9c7bde03e28ed3bd932`로 동일하다.
- **통과 — 두 Worker 전체 회귀/E2E:** Python 3.12.14, 루트에서 `.local/d-contract-venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests --junitxml=.local/binding-all.xml -q`: **492 passed, 0 failures/errors/skips**. `RUN_AGENT_E2E=1`, `PG_BIN/JC_BINARY/INCIDENT_BINARY/BACKEND_BINARY/GRAFANA_MCP_BINARY/HELM_BINARY`를 로컬 테스트 도구로 지정하고 외부 `DATABASE_URL/AGENT_E2E_DATABASE_URL`을 제거했다. 임시 loopback PostgreSQL 16.15, 실제 JC/Incident/Backend/두 Worker 및 공식 Grafana MCP 1.4.2를 사용했다. Grafana/LLM은 fixture다. 기존 MCP deprecation warning 3건.
- **통과 — 새 계약:** 45개 미선택 D의 원격 호출 0, verified 필수 필드/참조·클러스터 override·대안 동등성 검사, source UID/selector/label·binding revision 보존, Namespace 범위 확대 거부, 원본 snapshot 보존, sentinel 시각의 연속성 중단, counter reset/gap 거부 함수, D02/D06 UID 연결, O08 두 기준의 기존 값, O01 여유량 12MiB·용량 비율 0.25 및 D16 실패 시 기존 VRAM 보존, 추가 입력의 기본 수집/재시도 예산 보호. 실제 두 Worker의 미선택/선택 profile로 JC 결과 발행과 저장된 binding 근거를 검사했다.
- **통과 — D09 추가 집중검사:** 위 전체 실행 이후 추가한 producer 시각/freshness gate 테스트 1건을 `pytest .../test_binding_contract.py -k freshness`로 별도 실행했다. 보고 관측은 유지하되 시각 의미 승인 전에는 상태 fact를 만들지 않고, 명시적 승인 후에도 freshness를 벗어나면 fact를 보류한다. 결과 `.local/binding-freshness.xml`.
- **통과 — 작성 원본/사본:** 267개 Runbook을 HEAD와 구조 대조해 D05→D09 필수 조회·fact·목적 병합 외 변경이 없음을 확인했다. `knowledge_key`, compatibility, 문헌·지침·조건 등 보존, 일반 패키지 content와 표시 label 사본 일치. 로컬 원장 `.local/binding-identity-and-runbooks.json`. 개별 Runbook의 신규 분석 의미나 DB 발행 검수가 아니다.
- **통과 — 소비자:** `frontend/`에서 `npm run format:check`, `npm test` **146 passed / 15 files**, `npm run build`. 합성 결과의 새 metric/단위·null 사유 렌더링을 검증했다. `backend/`에서 Go 1.26.2 `go vet ./...`, `CGO_ENABLED=1 go test -race ./...`, `go build ./...`: 통과. HTML/CSV의 새 metric 및 0/null 구별을 단위검사하고 기존 실제 Backend 보고서 흐름은 위 Python E2E로 검증했다. 브라우저 실환경 검수는 수행하지 않았다.
- **통과 — 배포 정적 검사:** 루트의 `tools/ci/check_chart.py`(Helm lint/render/package 포함)와 `python -m unittest discover -s tools/ci/tests -v` **5 passed**. Windows에서는 `PYTHONUTF8=1`과 Helm/Git Bash PATH를 사용했다. 최초 cp949/Bash 경로 문제는 환경을 바로잡고 재검사했다.
- **통과 — 정적 코드:** Ruff check/format **82 files**, UTF-8 CRLF와 `git diff --check` 통과. 루트 `tools/check_links.py`는 사용자 소유의 별도 미추적 checkout `_codex_dcgm_publish/frontend/index.html`의 Vite root 경로 2건만 오류로 보고했다. 해당 checkout은 변경하지 않았으며, 추적 파일과 이번 신규 파일만 복사한 소스 트리로 동일 checker를 실행해 **103개 문서·1311개 링크/자산, 오류 0건**을 확인했다.
- **미완료/미검증:** 실제 Grafana의 binding 증거·선택, 실환경 LLM, 전체 신규/조건부 분석, counter별 결과 연결, 267개 개별 추가 의미 검토·비코드 Runbook, DB draft/발행, 부하/성능, 원격 CI와 배포. JSON은 후보 예제이고 전체 설계의 P1~P4 완료가 아니다. 로컬 수정/검수 단계이며 커밋·push·배포는 하지 않았다.

---

# 2026-10-06 종합·다중 선택 보고서 — 로컬 검수

- 기준: PR #67 병합 `origin/main` **d6f4ca6**에서 `feat/report-multi-selection`으로 로컬 작업했다. 7종류 다중 선택/전체 종합의 topic 합집합은 한 job이다. Backend·JC 접수·Ops 계산과 공통 입력 검증/내보내기를 수정했으며 RCA 분석, JC 실행·lease·슬롯 정책, DB 구조·배포 설정은 변경하지 않았다.
- **통과 — 실제 접수/계산/발행:** 루트에서 Python 3.11.16으로 외부 `DATABASE_URL`/`AGENT_E2E_DATABASE_URL`을 제거하고 `RUN_AGENT_E2E=1`, 로컬 `PG_BIN/JC_BINARY/INCIDENT_BINARY/BACKEND_BINARY/GRAFANA_MCP_BINARY/HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/report-prerequisites/multi-agents.xml`: **420 passed, 0 failures/errors/skips, 72.29초**. 임시 loopback PostgreSQL과 새로 빌드한 Backend·JC·Incident·두 Worker·공식 MCP 프로세스이며 Grafana/LLM은 fixture다. 종합 11주제의 map/criteria 1.2 보존, O08 단독과 같은 고정 수치, O10 조건 부재의 blocked/전용 D09 미조회, HTML/CSV 표시 기준을 확인했다. 기존 MCP deprecation warning 3건.
- **통과 — Go/일정 보존:** shared/backend/job-controller/incident 각각 Go 1.26.2 `go vet ./...`, `go test -race ./...`, `go build ./...`. `.local/report-usability/save-go-e2e.py`로 별도 임시 DB에서 Backend·Incident `go test -tags=e2e ./tests -count=1 -timeout=10m` 통과. 새 map을 일정에 저장해 revision만 증가하고 이전 revision·예약 outbox·실행 시각·중지 상태가 보존된다. 이 일정 시험의 JC는 영속 접수 fixture다. 잘못된/불완전 map은 shared/JC/Python 경계 검사로 거부한다.
- **통과 — Frontend:** `frontend/`에서 `npm run format:check`, `npm test` **145 passed / 15 files**, `npm run build`. 다중 선택 합집합/기준 map, 전체 종합 기본값, 조건 없는 O10, 구 이력·일정 렌더링과 새 요청 상세의 소주제별 표시를 확인했다.
- **통과 — 브라우저(모의 API):** `http://127.0.0.1:5191/reports/new`에서 Namespace+장비/에너지/사건 2종류=4주제 한 요청, 전체 11주제 일간 09:00 자동 일정, topic_group_by 전달과 비교/조치값 미생성을 수신 JSON으로 확인했다. 실제 Ops 계산 함수에 합성 표본을 넣어 만든 `reports/multi-demo#final-report`는 11개 소제목·기준·null/근거 부족과 O08 유효 수치를 모두 표시한다. 화면 예시 데이터는 실제 클러스터 데이터가 아니며 모의 API의 요청은 분석을 실행하지 않는다.
- **통과 — 정적:** Ruff check/format(77 files), Go formatting, UTF-8 CRLF, diff·문서 링크 검사. 02/04/05/07/08/12와 모듈 안내를 갱신했다. 새 필드는 선택적이며 구 입력/결과는 보존한다. 새 입력을 구 Worker가 무시하지 않도록 소비자 교체/drain 후 생산자 활성화 순서를 02에 명시했다.
- **미수행/미검증:** 실환경 배포·실제 Grafana/LLM 보고서·성능/부하·원격 CI. 전체 종합은 O08 단독보다 수집량이 늘 수 있으며 일반 group_by(OP-01), 클러스터별 O09 분해, D 통합을 새로 구현한 것은 아니다. 로컬 파일·검수 단계이며 커밋·푸시·PR·배포는 하지 않았다.

---

# 2026-10-06 Ops 불필요한 수집 제거 — 로컬 검수

- 기준: `origin/main` **baf6722**와 PR #66의 UI 커밋 **3d87983** 위에서 검증했다. PR 준비 시 #66이 병합된 최신 `origin/main` **6087d14**와 검증 기준의 파일 트리가 동일함을 확인했다. `fix/report-query-pruning`은 이 main 위에 수집 최적화만 올린다.
- 변경: O01의 미사용 D06 조회 제거, 고정 DB snapshot의 사건 목록이 명시적으로 비어 있는 O06에서 D13 로그 제외. 다른 주제가 같은 query를 필요로 하면 유지하며, 사건 있음/목록 미확인에서는 생략하지 않는다. O06 D08/D06 관측·미준비 진단과 기존 null/blocked는 보존한다. 생략 사유·DB 참조를 quality와 보고서 문장에 남긴다.
- **통과 — 집중 61건:** 저장소 루트 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests/test_report_query_pruning.py agents/tests/test_report_collection.py agents/tests/test_report_observation.py agents/tests/test_ops_report.py -q --tb=short`. O01 관측 GPU 수/메모리/온도 전후 일치, 무관한 Pod 조회 실패 배제, 다른 주제의 D06 보존, 1/7/31일 계획, O06 사건 유무/미확인·O10 공유 로그 조회, 원본 scope/profile/context 불변, 생략 설명·근거를 검사했다.
- **통과 — 실제 collector 호출 비교(합성 upstream):** 기본 프로필·2개 클러스터·하루 O01/O09/O05를 같은 고정 응답으로 전후 실행했다. query 호출과 evidence 행이 각각 **34→10**, 수집 complete는 둘 다 true였다. 새 workflow의 O06 사건 0건은 **26회**, D13 호출 없음. 계획상 이전은 28회다. 운영 호출량이나 실행시간 측정은 아니다.
- **통과 — 전체 두 Worker 회귀:** Python 3.11.16, 외부 `DATABASE_URL`/`AGENT_E2E_DATABASE_URL` 제거, `RUN_AGENT_E2E=1`, 로컬 `PG_BIN/JC_BINARY/INCIDENT_BINARY/BACKEND_BINARY/GRAFANA_MCP_BINARY/HELM_BINARY`로 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/report-prerequisites/pruning-agents.xml` 실행: **413 passed, 0 failures/errors/skips, 67.03초**. 임시 loopback PostgreSQL·실제 두 Worker/JC/Backend/Incident/공식 MCP 프로세스, Grafana/LLM 응답은 fixture다. 기존 MCP deprecation warning 3건. 최초 실행의 클라이언트 전용 PostgreSQL 경로 오류는 기존 로컬 서버 바이너리 경로로 바로잡고 전체 재실행으로 확인했다.
- **통과 — 정적/문서:** Ruff check/format(75 files), UTF-8 CRLF, diff 검사, 링크 검사. 개발명세 12와 Ops README에 초기 계획 수와 생략 조건·진단 보존·후속 범위를 반영했다.
- **해당 없음:** RCA·공통 Python·JC·Backend/Frontend 제품 코드·DB·프로필·조회 한도 변경. 보고서 문장은 Ops에서 생성하며 기존 결과/quality 구조를 사용한다. UI·Go 코드가 바뀌지 않아 별도 전체 Frontend/Go suite 재실행은 하지 않았다; Worker E2E에서 실제 Go 서비스 연동은 검사했다.
- **미수행/미검증:** 실환경 배포·새 보고서·전송 바이트·실행시간·Mimir 부하 감소. O08 단독/전체 11주제는 필요한 다른 소비자가 있으므로 이번 변경으로 호출이 줄지 않는다. D 통합·evidence 중복 저장/보존 정책·다운샘플링·작업 간 캐시·사건별 범위 축소는 후속 검토다. 완료 단계는 로컬 수정·검수이며 커밋/푸시/새 PR/배포는 하지 않았다.

---

# 2026-10-06 보고서 선택 개편 전 분석 조건·호환성 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **baf6722**. UI 개편 전 7개 종류의 topic_ids/group_by 기본값, 실제 집계 단위, 자료 준비 조건과 기존 일정/결과 보존 기준을 [12번 설계서](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#보고서-선택-개편-전-확정-기준--2026-10-06)에 확정했다. 7개 선택 화면과 일반 group_by 계산을 새로 구현한 것은 아니다.
- 변경: Ops는 D08 `observed_pod_labels`를 할당 계약으로 사용하지 못하는 O02/O03/O04/O06에 기존 `allocation_contract_missing` 사유를 표시한다. 수집 실패·빈 응답·독점 episode 부족과 구분하고, O02 관측 수치·다른 클러스터의 유효 수치를 보존한다. Worker 문장·Frontend·Backend 내보내기의 사유 설명을 맞췄다. RCA/공통 Python/JC/DB/실행 프로필/일정 로직은 변경하지 않았다.
- **통과 — 집중 사례:** 저장소 루트 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests/test_report_observation.py agents/tests/test_ops_report.py agents/tests/test_namespace_usage.py -q`: **69 passed**. 계약 미준비와 조회 실패 동시 표시, 빈 응답, unknown 모드의 실제 할당 + 활동률 0%, 다중 클러스터 O09 전체 범위 합계, O08 기존 집계를 확인했다.
- **통과 — 두 Worker 회귀:** Python 3.11.16, `RUN_AGENT_E2E=1`과 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/report-prerequisites/agents.xml` 실행. 실제 프로세스는 새로 빌드한 서비스/Worker/공식 Grafana MCP이며 Grafana·모델 응답은 fixture다. 외부 DB 환경변수를 제거하고 loopback 임시 PostgreSQL을 만들었다. **400 tests, 0 failures, 0 errors, 0 skipped; 68.10초**를 확인했다. 기존 MCP deprecation warning 3건이 남는다.
- **통과 — Backend:** `backend/`에서 로컬 Go 1.26.2로 `go vet ./...`, `go test -race ./...`, `go build ./...`; 별도 임시 PostgreSQL에서 `go test -tags=e2e ./tests -run '^TestBackendE2E$' -v -count=1 -timeout=5m`의 10개 사례 통과. 일정 주제 변경 시 새 revision만 생기고 이전 revision/예약된 outbox 입력/실행 시각/중지 상태가 보존됨을 추가 확인했다. 재시작 후 공개 결과 조회와 HTML/CSV 내보내기도 통과했다. 원격 일정은 조회/변경하지 않았다.
- **통과 — Frontend:** `frontend/`에서 `npm run format:check`, `npm test -- --run` **136 passed**, `npm run build`. 기존 결과의 수치/null·관측 해석·수정된 사유 문구를 렌더링 테스트로 확인했다. 새 UI는 아직 구현 전이므로 브라우저 상호작용 검수 대상이 아니다.
- **통과 — 정적:** Ruff check/format, Go formatting, UTF-8 CRLF, `git diff --check`, `.venv/bin/python tools/check_links.py`. 테스트 DB는 종료했으며 공유/운영 DB에 접근하지 않았다.
- **미수행/미검증:** 실제 배포 프로필의 D08 의미·클러스터/기간별 실데이터 가용성, 신규 7개 선택 UI, 운영 배포, 실환경 실행시간 비교, CI. 조회 최적화(O01 D06 제거/O06 사건 0건 생략)는 후속 범위다. 로컬 수정·검증 단계이며 커밋/푸시/PR/배포는 하지 않았다.

---

# 2026-10-06 대용량 수집·MCP 통신 복구 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **b4ca5c7**, `fix/report-collection-resilience`. 공통 MCP 전송과 크기 초과 복구, Ops D06 초기 조회 구간을 보완했다. 기본 프로필 `builtin-grafana-v7`과 Helm 미러에 `report.query_chunk_seconds={"D06":7200}`을 추가하고 계획·실행에 같은 상한을 적용한다. 다른 query는 기존 Ops 기본 24시간, RCA는 기존 1시간을 유지한다.
- **통과 — 전체 회귀:** 저장소 루트, Python **3.11.16**, NAT 1.5.0에서 `RUN_AGENT_E2E=1`과 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/collection-resilience-results.xml` 실행: **388 passed, 0 skipped, 66.61초**. 외부 DB 환경변수 두 개를 제거하고 매번 새 임시 loopback PostgreSQL을 사용했다. 현재 소스로 다시 빌드한 Go 서비스·별도 두 Worker·공식 Grafana MCP 1.4.2는 실제 프로세스이며 Grafana/LLM 응답은 fixture다. 기존 MCP deprecation warning 3건이 남는다.
- **통과 — 통신 회귀:** 실제 localhost HTTP 소켓에서 5.2초 지연 응답 성공, 연결 단절 뒤 두 Worker의 heartbeat·실패 보고·다음 실행 성공, 세션 종료 404 뒤 다음 호출 재연결을 확인했다. 실패한 조회를 자동 재전송하지 않는다. 도구 deadline·외부 취소·동시 호출 중 한 호출 취소·일반 도구 오류·종료 후 태스크 회수도 검사했다. 세션 종료 처리는 `get_tools`/`call_tool`의 공통 경로에 둔다.
- **통과 — 큰 응답과 의미 보존:** 공식 MCP로 보낸 Prometheus 인공 응답 **11,536,878바이트**는 전송된 뒤 Agent의 2MiB 제한에서 분할됐다. 별도 단일 실행에서는 3600초 요청을 버린 뒤 523초 구간 6개와 마지막 462초, 총 8회로 수집했고 원본 121개 표본·전체 기간·대상 필터가 보존됐다. **MCP의 10MiB 제한을 모든 출처에 적용되는 것으로 해석하지 않는다.** 원격 10MiB 제한은 기존 Loki E2E에서 확인했으며, Prometheus 원격 크기 오류 분기는 오류 주입 fixture로만 검사했다.
- **통과 — 수집 계획:** 1/7/31일 원본 표본, 2개 클러스터·11주제 초기 계획 46/322/1426회와 작은 사용자 예산의 사전 거절, Pod 이름 재사용·UID 충돌·표본 공백, 분할 중 호출/deadline 소진의 미확인 구간 보존을 검사했다. D06의 2시간은 확인한 하루 약 32MiB 응답을 줄이는 초기 상한이며 최적 구간이나 월간 완료 보장이 아니다. 구간별 소요시간·크기·표본 수·분할 사유를 새 진단 로그에 남긴다.
- **통과 — 정적·설정 검수:** Ruff check/format, Helm lint/template/package와 설정 미러, CI 도구 unittest 5건, 문서 링크·diff·CRLF 검사. 독립 검토에서 찾은 만료 세션 재사용 문제를 수정하고 최종 전체 회귀를 다시 실행했다. 새 수집 진단은 원본 payload·조회식·인증 값을 출력하지 않지만 NAT의 기존 원문 오류 로그까지 정리한 변경은 아니다.
- **미수행/미검증:** 운영 배포·수정본으로 같은 24시간/주간/월간 실제 보고서 재실행·운영 부하와 처리시간·원격 CI. 이번 운영 실패가 Mimir 과부하나 Prometheus 원격 10MiB 제한 때문이었다고 확정하지 않는다. 완료 단계는 로컬 파일이며 커밋·푸시·PR은 하지 않았다.
- **해당 없음/후속:** DB migration·API/result schema·JC lease/슬롯 정책·RCA 계산/판정·UI 변경은 없다. 공통 전송 변경은 두 Worker 이미지에 적용해야 하며 사용자 정의 전체 Agent 프로필은 D06 맵과 revision을 별도로 반영해야 한다. 기존 격리 해제와 11개 주제 축소·중복 evidence 저장/보존 정책은 이번 변경에 포함하지 않았다.

---

# 2026-10-06 PR 최종 재검수 — Fleet 지표와 실행시간 표시

- **통과:** 새로 fetch한 `origin/main`과 작업 시작 커밋은 모두 **2d9ee8f**이며 양쪽 단독 커밋은 0개였다. 기존 로컬 Fleet 설정과 Frontend 실행시간 표시를 함께 검토했다. 아래 10월 2일 기록은 당시 기능별 검수 범위를 뜻한다.
- **통과:** 저장소 루트의 격리 로컬 DB·실제 두 Worker·공식 MCP E2E를 포함해 **364 passed, 0 skipped, 61.85초**. Python 3.11.16, 앞선 검사와 같은 로컬 도구/외부 DB 환경 제거 조건이며 결과는 `.local/report-usability/pr-fleet-execution-results.xml`이다. Grafana/LLM 상위 응답은 fixture, 기존 MCP deprecation warning 3건이다.
- **통과:** Ruff check/format, Helm 계약·설정 미러, CI 도구 unittest 5건, 문서 링크·diff와 독립 검토. Frontend **136 passed**·format/build와 상세 표시 검수는 [Frontend QA](../frontend/QA.md)를 따른다.
- **범위/미검증:** RCA 판단 코드·Ops 산식은 바꾸지 않지만 D04/D11 공통 설정은 두 Worker에 적용된다. 특정 Namespace의 온도/전력 귀속, D07/D12 원본 확보, 운영 배포/수정본 실제 재실행은 미검증·미구현이며 이번 PR 범위에 포함하지 않는다. 원격 CI 상태는 PR에서 확인한다. 기존 운영 데이터·DB schema 변경은 없다.

---

# 2026-10-02 Fleet 온도·전력 조회명/대상 라벨 — 로컬 검수

- 기준: 최신 `origin/main` **2d9ee8f**, `fix/fleet-metric-bindings`. 기본 profile `builtin-grafana-v6`의 D04/D11을 실제 소문자 Fleet 이름과 `uuid`/`node` 필터에 연결하고 query revision을 `builtin-v6`로 변경했다. Helm 미러도 동기화했다. 공통 설정이 두 Worker에 적용되며 RCA 판단·Ops 산식·수집 코드·UI·DB/API/result schema는 변경하지 않았다.
- **통과 — 실환경 읽기 확인:** 로그인된 Grafana Mimir-Operations에서 2026-10-01 00:00~10-02 00:00(Asia/Seoul), CPC-1/CPC-2를 조회했다. 소문자 온도/전력의 원본 존재·`uuid`/`node`·Namespace 라벨 부재, 기존 대문자 GPU_UTIL/FB_USED·Pod/up 지표의 존재를 확인했다. 대문자 GPU_UTIL에는 `UUID`와 `uuid`가 모두 있어 D02/D08 필터를 유지한다. D07/D12 및 확인한 이름 변형은 이 기간에서 없었고 원시 Container 요청은 다른 계약이므로 대체하지 않았다. 이는 해당 기간/클러스터의 확인이며 전역 가용성 보장이 아니다.
- **통과 — 표본 공백:** 기간 끝 15분의 일부 전력 원본에는 60/120/180초 간격이 있었다. 기존 max_hold 30초를 유지하고 유효 관측 구간만 계산한다. 표본 공백을 채우거나 24시간 전체 에너지가 확보됐다고 판단하지 않는다. 단위 동등성은 [Fleet/Exporter 소스 대조](../docs/specs/rca-agent/references/domain-category-metric-mapping.md)에 근거하며 배포된 전체 producer 설정/지원 sentinel은 재검증하지 않았다.
- **통과 — 로컬 전체:** 저장소 루트, Python 3.11.16, `RUN_AGENT_E2E=1`과 `.local/namespace-tools`의 PostgreSQL/MCP/Helm, 로컬 JC/Backend/Incident를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/fleet-bindings-results.xml` 실행: **364 passed, 0 skipped, 63.38초**, 기존 MCP deprecation warning 3건. 외부 DB 환경 변수를 제거하고 임시 loopback PostgreSQL을 사용했다. 두 Worker·공식 MCP 1.4.2는 실제 프로세스이며 Grafana/LLM 상위 응답은 fixture다.
- **통과 — 회귀:** fixture는 잘못된 대문자 온도/전력 이름에 빈 결과를 반환한다. 전체 Namespace에서 40°C·250W×1시간=0.25kWh·GPU 신원, 특정 Namespace에서 필터 유지·빈 근거/null을 확인했다. RCA D04의 정확한 조회명·uuid/node 필터·원본 라벨, 60/120초 간격과 실제 0 표본의 총 유효 90초/0.0025kWh 계산을 검사했다. Ruff check/format, Helm 계약/미러, CI 도구 unittest 5건, 문서 링크·diff 검사도 통과했다.
- **미수행/미검증:** 운영 설정 변경·배포·수정본으로 실제 보고서/RCA 재실행·원격 CI·커밋/푸시/PR. 특정 Namespace의 GPU 온도·전력 귀속은 미지원이며 기존 제한을 유지한다. 수집 주기 보완/유지시간 확대·D07 유효 요청 producer·D12 용량 전송·D 통합/신규 D 구현은 포함하지 않았다. DB migration·과거 결과 재작성은 해당 없음.

---

# 2026-10-02 Loki 응답 용량·잘림 복구 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **a1d73e2**, `fix/loki-response-size-recovery`. 공통 Observation에서 MCP 본문 크기 초과와 Loki 행 잘림을 기존 기간 분할로 복구한다. 두 Worker의 수집 동작에 적용하며 RCA 판단·Ops 산식·D 정의·프로필/한도·DB/API/result schema는 유지한다.
- **통과:** 저장소 루트, Python 3.11.16 전체 Agent 검사 **362 passed, 0 skipped, 61.71초**. `RUN_AGENT_E2E=1`과 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/loki-size-results.xml`을 실행했다. 외부 DB 환경 변수를 제거하고 새 임시 loopback PostgreSQL·최신 소스 JC/Backend/Incident·두 Worker·공식 Grafana MCP 1.4.2를 사용했다. Grafana/LLM 응답은 fixture이며 기존 MCP deprecation warning 3건이 남는다.
- **통과:** 공식 MCP/NAT E2E에서 상위 HTTP fixture의 11MiB 응답으로 실제 `response body exceeds maximum size of 10485760 bytes` 오류를 발생시킨 뒤 D09/D13·파생 D05의 연속 구간 복구·요청 기간 끝까지 수집·대상 필터와 정상 응답 필드 보존을 확인했다. D13 로그는 건강 관측으로 승격하지 않는다. 이 fixture는 조회 구간에 따라 응답을 생성하므로 동일 사건 집합 보존은 별도 고정 사건 단위 검사로 확인한다.
- **통과:** `test_discovery.py` **67 passed**. NAT 문자열/isError envelope·행 잘림/행 수 도달, 원본 고정 로그 집합·범위·query revision·파생 참조, 성공한 앞 구간과 예산/deadline 소진 나머지, 최소 구간 초과·원본 오류 비노출·취소 전파·일반 오류/Prometheus 미재시도·기존 시각 정밀도 회귀를 확인했다. 수정 전에는 새 복구/사유 검사 16건이 실패했다.
- **통과:** Ruff check/format 72개 파일, 문서 링크·diff 검사. 기존 `response_byte_limit` 사유를 재사용하므로 RCA/Frontend/Backend 이름 맵·UI 변경은 없다. 독립 코드 검토에서 차단할 문제는 발견하지 않았다.
- **미검증:** 원격 CI, 운영 배포 후 동일 기간의 실제 Grafana 재조회·보고서 공개·운영 부하/메모리. 로컬 fixture 성공은 실제 운영의 전체 기간 수집 보장이 아니다. 기존 예산/마감 안에 복구하지 못한 구간은 계속 미확인으로 남는다.
- **반영:** 병합·CI 성공 후 두 Worker 이미지를 함께 갱신하고 새 보고서로 확인한다. MCP 이미지·설정·DB migration·기존 결과 재작성은 필요 없다. 배포와 운영 변경은 이번 PR 생성에 포함하지 않는다.

---

# 2026-10-02 Ops 계산 중 heartbeat 유지 — 로컬 검수

- 기준: 최신 `origin/main` **03105a4**, `fix/report-calculation-heartbeat`. Ops 주제 계산만 요청 순서대로 별도 스레드에서 실행하고, 해당 주제에 필요한 할당·활동 입력만 정규화한다. 취소 시 현재 계산을 회수하며 다음 주제·문장 구성·저장으로 진행하지 않는다. RCA·공통 Worker/Store·JC·조회 한도·lease·스키마는 변경하지 않았다.
- **통과:** Python 3.11.16 전체 Agent 검사 **344 passed, 0 skipped, 54.93초**. 저장소 루트에서 `RUN_AGENT_E2E=1`과 준비된 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/calculation-results.xml`을 실행했다. 외부 DB 환경 변수를 제거하고 임시 loopback PostgreSQL·최신 소스 JC/Backend/Incident·두 Worker·공식 Grafana MCP를 사용했다. Grafana/LLM 응답은 fixture이며 기존 MCP deprecation warning 3건이 남는다.
- **통과:** 새 Worker 검사 7건은 lease보다 긴 CPU 계산 중 heartbeat, criteria 1.1/1.2의 11개 주제 순서·산출물, 취소·반복 취소·409·deadline·계산 오류를 확인한다. 취소 후 계산 오류가 발생해도 원래 취소를 보존하며 Worker 반환 전에 계산을 회수한다. 수정 전 `run()`만 메모리에서 복원하면 성공 사례 2건이 계산 중 heartbeat 0회·lease 만료로 실패한다.
- **통과:** 실제 JC/DB E2E는 시험 job에만 2초 lease를 적용하고 2.6초 CPU 계산 중 heartbeat 200 유지, 11개 주제·기본 보고서 저장, checksum 일치와 `succeeded` 공개를 확인했다. 운영 설정은 변경하지 않았다.
- **통과:** main과 수정 코드의 11개 주제 × 기준 버전 2개 × 정상/빈 fixture 결과 44건이 동일했다. 별도 286 Pod·8 GPU·1시간 합성 자료에서 계산 0.506→0.258초, 10ms 주기 확인의 최대 공백 0.516→0.024초였고 수치·입력은 동일했다. 단일 로컬 측정이며 운영 처리시간이나 속도 개선율의 보장이 아니다.
- **통과:** Ruff check/format, 문서 링크 검사, diff 검사. 수집·주제 계산·문장 구성 시작/완료 로그로 후속 지연 구간을 구분한다.
- **미검증:** 운영 배포·실제 Grafana/LLM 보고서 재실행·운영 메모리/성능. 운영 로그의 약 75초 heartbeat 공백 전체가 계산에 쓰였는지는 당시 계측 부재로 확정하지 않는다. 기존 격리는 자동 해제하지 않으며 원격 종료 확인 뒤 별도 운영 절차를 따른다. DB migration·기존 결과 재작성은 해당 없음.

---

# 2026-10-02 O08 클러스터별 관측 요약 — 로컬 검수

- 기준: `b79758a`, 로컬 `fix/report-cluster-observation`. Ops O08 criteria 1.2에 요청 클러스터별 관측 GPU·연결 GPU·연결 시간·라벨 부재·신원 미확인 지표를 추가했다. RCA·공통 정규화·DB/API/result schema는 변경하지 않았다.
- **통과:** Python 3.11.16 전체 Agent 검사 **335 passed, 0 skipped, 43.00초**, 기존 MCP deprecation warning 3건. `RUN_AGENT_E2E=1`과 로컬 도구 경로를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/cluster-results.xml`을 실행했다. 임시 loopback PostgreSQL·실제 JC/Incident/Backend·두 Worker·공식 Grafana MCP를 사용했고 Grafana/LLM 응답은 HTTP fixture다.
- **통과:** 빈 작업 라벨은 유휴로 단정하지 않음, 클러스터별 evidence 참조, UUID 중복 제거, 공유 연결 시간 합집합, 선택 Namespace 범위, 부분 시간 조인, 유효 표본 없음·MIG·조회 실패·부분/미수집과 확인된 0 구분, 정상 빈 응답, 기존 Namespace 활동률·RCA 회귀. Ruff check/format 통과.
- **미수행/미검증:** 운영 조회·배포·기존 결과 재계산·실제 클러스터의 유휴 여부·커밋·푸시·PR·원격 CI. 브라우저 예시는 합성 D01/D02를 실제 계산 함수와 결과 검증기로 처리했다.

---

# 2026-10-02 Runbook-first RCA / R 실행 의존 제거

- **PR 준비 재검증 통과:** 최신 `main` **5f52fe5**를 반영하고 문서 2곳의 양쪽 변경을 보존했다. Python **324 passed, 0 skipped**(123.49초), Frontend **118 passed**·format/build, 4개 Go 모듈 vet/race/build, Backend·Incident DB/E2E, Ruff·문서 링크·diff 검사 통과. Windows 로컬 pytest 실행에는 실제 Worker와 같은 `WindowsSelectorEventLoopPolicy`를 적용했다. 아래 315/101건은 main 반영 전 최초 검증 기록이다.
- **통과:** Python 3.12.14 전체 Agent 검사 **315 passed, 0 skipped**(121.74초). 저장소 루트에서 `RUN_AGENT_E2E=1`과 현재 소스 JC/Incident/Backend 바이너리, 격리 로컬 PostgreSQL, 공식 Grafana MCP, Helm을 지정해 `python -m pytest -c agents/pytest.ini agents/tests -q --tb=short`를 실행했다. Grafana·LLM 응답은 HTTP fixture이며 운영 DB는 사용하지 않았다.
- **통과:** R 없는 신규 1.5 입력 → Incident outbox → JC → RCA Worker → 결과 발행, 기존 1.3 입력·불변 snapshot 호환, 1.4/1.5 입력 검증, Runbook 계획의 D04 선택, 미등록 값·실패·stop·일반 조사 전환, 미일치·비호환 Runbook의 패키지 fallback, 원인 미확정·추가 근거 유지. 기존 R 목적에 따라 강제하던 GPU–Pod 조회는 이제 해당 Runbook의 필수 계획으로 검증한다.
- **통과:** `shared`, `backend`, `job-controller`, `incident` 각각 `go vet ./...`, `go test -race ./...`, `go build ./...`. Windows 경로의 대괄호와 Go embed 제약 때문에 동일 소스를 임시 경로에 복사해 검사했다. Backend·Incident에서 격리 DB와 실제 Backend 바이너리를 지정한 `go test -tags=e2e ./tests -v -count=1 -timeout=10m`도 통과했다. 006의 기존 Worker 행/제약 → 007 업그레이드, 반복 시작, 1.5 허용·미지원 버전 거부를 포함한다.
- **통과:** `frontend`에서 `npm test` **101 passed**, `npm run build`. 신규 조사 질문 표시와 과거 purpose_id 결과 표시를 함께 검사했다. 루트 Ruff check/format, 문서 링크, `python tools/ci/check_chart.py`, `python -m unittest discover -s tools/ci/tests -v` **5 passed**도 통과했다. 처음의 도구 경로 오류는 설치된 Git Bash·Helm 경로를 명시해 해결했다.
- **미검증:** 원격 CI·운영 배포·실제 Grafana/LLM의 분석 품질. 완료 단계는 로컬 파일이며 commit/push/배포·Runbook DB 발행은 수행하지 않았다. 적용 순서는 JC → RCA Worker → Incident/화면이다. D 구조 확대는 이번 범위에서 제외했다.

---

# 2026-10-02 대량 저장 중 heartbeat·lease 보호 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **5ddfe21**, 로컬 브랜치 `fix/worker-save-heartbeat`. 공통 Store/Worker와 JC 행 잠금만 수정하며 Worker별 분석·관측 계획·해시 규칙·스키마·lease/슬롯 설정은 유지한다.
- **통과:** Python 3.11.16, 루트 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/save-results.xml` — **315 passed, 0 skipped, 43.36초**, 기존 MCP API deprecation warning 3건. `RUN_AGENT_E2E=1`, `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 준비된 로컬 도구로 지정했다. 새 임시 loopback PostgreSQL·실제 JC/Incident/Backend·두 Worker·공식 Grafana MCP를 사용하며 데이터소스/모델 응답은 HTTP fixture다. 테스트 DB는 종료했다.
- **통과:** `test_store.py`의 실제 JC/DB 검사: 합성 evidence 217건, 2초 시험 lease보다 긴 2.6초 저장 지연 중 heartbeat 갱신과 최종 공개·동일 완료 재전송·원본 JSON/checksum 보존. 저장 중 취소·lease 만료·attempt 교체·deadline 만료는 evidence/candidate를 모두 롤백한다. JC의 실제 행 잠금 대기를 확인한 뒤 lease를 만료시키면 heartbeat 409로 갱신을 거부한다. 실제 운영 41 MiB snapshot의 성능 재현은 아니다.
- **통과:** Worker 저장 도중 취소/409 lease 상실 시 저장 task를 회수하고 complete를 보내지 않는 검사. JSON 큰 정수·소수·한국어·특수문자 보존, 기존 RCA/Ops 회귀 포함.
- **통과:** Ruff check/format 70개 파일. JC·Backend·Incident 각각 Go vet/race/server build, 별도 임시 PostgreSQL의 Backend·Incident 전체 `-tags=e2e` 검사. 관련 JC 배분·취소·완료·재시도 경로 포함. 문서 링크와 diff 검사 통과.
- **미수행/미검증:** 커밋·푸시·PR·원격 CI·배포·운영 보고서 재실행·기존 격리 해제·실제 Grafana/LLM·운영 메모리/저장 성능. 기존 운영 실패의 CPU와 DB 대기 시간 비율은 당시 계측 부재로 확정하지 않는다.
- **해당 없음:** DB migration, API/result schema, Frontend 변경. 배포 시 JC → 두 Worker 순서로 함께 반영하며 기존 격리는 모델 서버 종료 확인 후 별도 운영 절차로 해제한다.

---

# 2026-10-02 보고서 계획 기반 병렬 MCP 수집

- **통과:** Python 3.12.14 전체 Agent 검사 **306 passed, 0 skipped** (94.70초). `RUN_AGENT_E2E=1`, 격리 로컬 PostgreSQL, 최신 소스 Backend/JC/Incident, 공식 Grafana MCP 1.4.2와 Helm으로 실행했다. 데이터소스·모델은 HTTP fixture이며 운영 DB는 사용하지 않았다.
- **통과:** `test_report_parallel.py`는 동시성 1/3의 수치 동일성, 상한, 중복 query 제거, 의존 순서와 Namespace 범위 축소, 완료 응답 재사용, 발견 예산 상한, 취소 후 task 회수, 독립 실패와 비교 기간 분리를 검사한다. 기존 기간 수집·RCA 병렬 회귀도 통과했다.
- **통과:** Ruff check/format, 문서 링크 검사, 실제 Helm lint/template/package 및 설정 미러 검사. Linux Bash 실행을 포함하는 배포 파이프라인 단위 검사는 Windows에 Bash 실행 파일이 없어 로컬에서 실패했으며 PR CI에서 확인한다.
- **시간 비교:** 독립 MCP 6회에 각 40ms 지연을 주는 고정 검사에서 순차 0.281초, 동시성 3에서 0.094초였다. 실제 Grafana 성능 측정이 아니다.
- **미검증:** 운영 배포·실제 일간/주간/월간 자료의 처리시간·부하·메모리·관측 의미·모델 품질. 추가 보완 라운드·자유 생성형 조언은 이번 구현 범위가 아니다.
- 실행: `.local/rca-dev-venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests --tb=short` (위 E2E 환경과 현재 서비스 바이너리 지정). 로컬 준비 스크립트는 검증 도구 경로만 지정하며 제품 코드에 포함하지 않는다.

---

# 2026-10-01 일 단위 보고서 Backend 접수 회귀

- **통과:** 최신 main `e9ed87e` 기반 Python 3.11.16 전체 **286 passed, 0 skipped**, Ruff check/format 66개 파일. `RUN_AGENT_E2E=1`과 격리 로컬 PostgreSQL, 최신 Backend/JC/Incident 바이너리, 공식 Grafana MCP 1.4.2, Helm으로 두 Worker의 실제 프로세스·발행 경로를 실행했다. 데이터소스와 모델 응답은 HTTP fixture다.
- **변경:** Backend를 통한 Namespace 보고서 E2E만 1시간 요청에서 24시간 요청으로 바꿨다. fixture의 121개 표본 × 30초 hold를 기대 관측시간으로 명시해, 하루 요청을 하루 전체 관측으로 오해하지 않도록 검사한다. Worker 구현·공통 PERIOD·RCA 요청·수집 한도는 변경하지 않았다.
- 첫 검증은 오래된 Incident 실행 파일·잘못된 Helm 경로와 시간 기대값으로 실패했다. 최신 소스 빌드와 올바른 도구 경로·기대값으로 다시 실행해 전체 통과했다.
- **미검증:** 운영 배포·실제 Grafana/LLM 실행. 운영 DB는 사용하지 않았다.

---

## 2026-10-01 RCA synthesis 식별자 인용 허용

기준 main `7abc8d2`(#39·#40 포함), `fix/rca-synthesis-identifier-prose`. #39 배포 후 운영 작업 `ed730b4d`(Loki 합성 SXID 11001)에서 입력 536,621→15,570바이트 제한, `request_attempts=1`·`response_calls=1`을 확인했으나 응답이 `invalid_limitations`로 탈락했다. 같은 view를 읽기 전용으로 재구성하면 `D05`·`R01`·`cpc-2`·`vessl-k8s-worker-01` 등 숫자가 포함된 식별자가 47종이었고, 기존 `\d` 전면 금지가 이를 거부한다. 모델 원문은 저장하지 않으므로 실제 문장은 추정이다.

- **통과:** Windows/Python 3.12.14 agent tests **199 passed, 17 skipped**(E2E). 식별자 허용·대소문자·부분 일치(`D050`, `worker-02`) 거부, 숫자만/개수/기간/측정값·생산자 문장 속 `95C` 거부 회귀 추가. Ruff check/format 통과(무관한 로컬 미추적 파일 제외).
- **통과:** 운영 작업 `ed730b4d` view에서 추출한 식별자 47종에 공백 포함 문장·시각·숫자+단위 값이 없음을 확인했다.
- **미검증:** `RUN_AGENT_E2E=1` 전체 검사는 PR CI로 확인한다. 배포 후 새 RCA 실행에서 모델 응답이 검증을 통과하는지는 별도 확인이 필요하다.
- **해당 없음:** DB migration·결과 스키마·기존 결과 재작성.

# 2026-10-01 Ops 기간 수집·예산 분리

- **통과:** Python 3.11.16, Ruff check/format. 일반 검사 208 passed, 17 E2E skipped. 로컬 전용 PostgreSQL + 현재 소스의 Backend/JC/Incident + 두 Worker + 공식 Grafana MCP 1.4.2 전체 실행은 **225 passed, 0 skipped** (36.58초). 운영 DB는 사용하지 않았다.
- **통과:** 새 10개 고정 검사로 1일/7일/31일/73시간 원본 표본과 전체 요청 구간 보존, 큰 응답 자동 분할, 기존 1시간 수집과 동일한 Namespace 수치·0%, 첫 dense 조회가 다른 query/CPC를 고갈시키지 않는 예산 배분, 초과 계획의 외부 조회 0회, 비교 기간 분리, 오류/시간 만료/취소 전파, RCA profile 불변과 구 설정 fallback을 확인했다.
- **통과:** 기존 실제 프로세스 Namespace E2E에서 Backend 접수→Ops→JC 발행→HTML/CSV를 재검사하고 적용 한도 2048·계획 accepted·필수 D01/D02/D06/D08 전체 조회 구간 완료를 확인했다. RCA E2E도 통과했다. 데이터소스 응답은 HTTP fixture다.
- **통과:** Helm 3.17.3 chart 계약/패키징 및 workflow 계약 5개, 소스 설정과 Helm 미러 일치.
- **미검증:** 운영 배포, 실제 클러스터의 일간/주간/월간 데이터 밀도·표본 보존·부하/지연/최대 메모리. 기간 고정 검사는 운영 규모 성능 검증이 아니다. 보고서 전용 예산은 초기 예시이며 모든 범위의 성공을 보장하지 않는다. 재분할/에러/시간 소진 시 미완료를 명시한다. 원격 CI는 PR에 기록한다.

---

## 2026-10-01 RCA synthesis 입력 크기 제한·단계별 진단

기준 main `406f9fa`(#38 포함), `fix/rca-synthesis-context-budget`. 운영 작업 `22c1f69f`의 저장 evidence를 읽기 전용(`default_transaction_read_only=on`)으로 조회해 synthesis 입력 하한 530,150바이트가 작업 예산 32,768을 넘어 `LLM.complete()` 요청 전에 탈락함을 재현했다. 같은 GUI 결과의 `LLM 응답 사용 기록 1건`은 최종 보고서 편집 호출이었다.

- **통과:** Windows/Python 3.12.14 `python -m pytest -c agents/pytest.ini agents/tests -q`: **198 passed, 17 skipped**(E2E). 관계없는 로컬 미추적 `test_gpu_node_scope.py`는 제외했다. Ruff check/format 통과.
- **통과:** 같은 저장 evidence에 새 `bounded_context`를 적용하면 모델 입력 15,680바이트, 장비 관측 2건 전부 유지, metric 계열 138개 중 7개 선택·131개 생략이 `context_selection`에 기록된다. 원본 evidence는 변경하지 않는다.
- **통과:** README의 `rca_synthesis` 진단 SQL을 같은 DB에서 읽기 전용 실행. 구 결과의 `diagnostics`는 NULL이다.
- **미검증:** 로컬 Docker·Go가 없어 `RUN_AGENT_E2E=1` 전체 검사는 PR CI(Linux/Python 3.12, PostgreSQL 16)로 확인한다. 운영 배포와 새 RCA 실행에서의 실제 모델 응답 품질은 별도 검수 대상이다.
- **해당 없음:** DB migration·결과 스키마 버전·기존 결과 재작성·운영 설정 변경.

## 2026-10-01 Agent E2E Backend 중복 migration 교착 수정

기준 main `af9294e`(#34·#35 포함). [실패 CI 36793523231](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/36793523231)의 PostgreSQL 로그에서 Backend `ALTER TABLE jobs`와 JC의 만료 작업 `UPDATE jobs` 사이 `SQLSTATE 40P01` 교착을 확인했다. stack의 JC가 공통 schema를 준비한 뒤 모델 인증·런북 테스트의 Backend가 migration을 재실행하던 두 곳을 `DSX_MIGRATE=false`로 바꿨다. 기존 Namespace 테스트와 같은 설정이다.

- **통과:** macOS arm64/Python 3.11.16, Go 1.26.2의 현재 소스와 동일한 Backend/JC/Incident 바이너리, 실제 새 loopback PostgreSQL·Worker/NAT/공식 MCP로 전체 **206 passed**, 33.80초. 기존 MCP deprecation warning 3건. `DATABASE_URL`·`AGENT_E2E_DATABASE_URL`을 제거하고 `RUN_AGENT_E2E=1`로 실행했다. JUnit: `.local/e2e-migration-fix/results.xml`. Grafana/LLM 응답은 fixture다.
- **통과:** 모델 인증 두 Worker·고정 revision·런북 263개 등록/조회/hash/중복 방지 및 실제 RCA 소비·Namespace 보고서 검사. Ruff check/format·문서 링크·diff 검사.
- **유지:** Backend 자체 migration 및 재실행 검증은 별도 Backend DB E2E에 남아 있다. 테스트 재시도나 timeout 증가로 실패를 숨기지 않는다.
- **미검증:** 수정 커밋의 Linux/Python 3.12 전체 CI는 PR 생성 후 확인하고 PR 설명에 기록한다. 운영 migration 동시 실행 조정이나 배포 검증은 이번 변경 범위가 아니다.
- **해당 없음:** 제품 코드·SQL·운영 DB/설정·UI·API·배포 변경.

## 2026-09-30 보고서 단위 설명·수집 범위 개선

## RCA 접근·Ops 최종 보고서 — 2026-09-30

기준 main `40b68d3`(#31), `feat/final-report-access` 로컬 작업. 기존 GPU 시간·수집 재사용/범위 축소를 유지했다.

- **통과:** 루트 Python 3.12.14 `python -m pytest -c agents/pytest.ini agents/tests -q --basetemp=.local/pytest-final-access-2`: 189 passed, 17 skipped. Ops 수치 없음/실제 0, 모델 선택/무효 응답/미설정에서 다섯 섹션·부족 사유·원래 품질 보존, HTML escape 검사 포함. Ruff check/format 통과.
- **통과:** `.local/verify-final-report-access.py`, `RUN_AGENT_E2E=1`의 실제 Worker/NAT/공식 MCP·최신 로컬 Go 바이너리·격리 PostgreSQL: 관련 8 passed, 6 deselected. RCA native/Fleet webhook, 근거 없음 보고서 2건, 두 Worker 공개/참조·Worker HTML checksum/본문, fast path, Backend Namespace 보고서 HTML, Ops HTTP 실패 후 기존 수치 보존. 선택 외 6건은 이번에 미실행이다.
- **통과:** Backend/JC/Incident vet·race·build, `.local/verify-final-report-backend.py`의 격리 DB 전체 Backend E2E. Frontend 38 tests·format·build. 문서 링크/diff 검사.
- **미검증:** 운영 배포·실제 Grafana/LLM 의미와 품질, 실제 브라우저 클릭/화면 검수. Frontend는 컴포넌트 렌더 fixture이며 상위 Grafana/LLM도 fixture다. 운영 DB는 사용하지 않았고 새 임시 DB 종료를 확인했다. 새 schema/migration/API는 **해당 없음**. 커밋/push/PR/배포는 이번 작업에 포함하지 않았다.

기준: 원격 main `b80b8f7`(RCA PR #30 포함). 운영 보고서를 읽어 문제를 확인했으나 운영 데이터·설정은 변경하지 않았다. 과거 결과를 재계산하지 않는다.

- **통과:** 위 환경과 동일한 macOS/Python 3.11.16에서 `RUN_AGENT_E2E=1` 전체 검사 **199 passed**, 기존 MCP deprecation warning 3건. `DATABASE_URL`·`AGENT_E2E_DATABASE_URL`을 제거하고 `.local/namespace-tools`의 PostgreSQL/MCP/Helm, 최신 소스로 빌드한 Backend/JC/Incident를 사용했다. 명령은 아래 Namespace 전체 검사와 같고 JUnit은 `.local/agent-e2e/report-clarity-results.xml`이다. 실제 격리 DB·Worker·NAT·공식 MCP를 사용하며 Grafana/LLM 응답은 fixture다.
- **통과:** 이후 추가한 큰 Pod 집합 비교를 포함한 `agents/tests/test_report_observation.py` **12 passed**. GPU 8대/Pod 286개 고정 입력에서 기존/개선 namespace 수치와 품질이 같고 개선 조회는 3회였다. 운영 환경 호출 감소율·속도 검증은 아니다.
- **통과:** 8대×(1시간−6.113초) GPU-hours, 기간 중 고유 연결 대수, 기존 0/null·중복·공유/MIG·Pod UID·모델 충돌 회귀. 재사용 opt-in/기본 비활성, 기간/범위 격리, 불완전 응답 미재사용, namespace 단독 범위 축소와 혼합 보고서 전체 범위 보존을 확인했다.
- **통과:** Backend `go vet ./...`, `go test -race ./...`, 서버 build 및 새 loopback PostgreSQL의 `go test -tags=e2e ./tests -count=1 -timeout=10m`. 별도 schema와 임시 DB만 사용했다. Frontend 36 tests·format·build 및 로컬 브라우저 검수는 [Frontend QA](../frontend/QA.md)에 기록했다. Ruff·문서 링크·diff 검사 통과.
- **해당 없음:** RCA 제품 소스·설정 변경, JC 설정·DB migration·새 API·새 의존성. 공통 Observation에는 report opt-in 기능을 추가했으므로 두 Worker 회귀를 실행했다. 기존 Fleet 정밀도·usable_observation 처리는 보존했다.
- **미수행/미검증:** 운영 배포, 변경 코드의 실제 Grafana 조회 성능·LLM 품질, D08 할당 계약 확보. 원격 최신 커밋 CI 상태는 PR에서 확인한다.

# Agent 검증 기록

## 2026-09-30 Fleet RCA 파이프라인 후속 검증

최신 main `77fbfcf` 통합 후 **추가 통과**: 일반 175 passed/17 skipped, 관련 실제 프로세스 E2E 7 passed/7 deselected(webhook 2·근거 없음 2·두 Worker 공개·fast path·Backend namespace 보고서), Incident DB E2E 전체, Backend/JC/Incident vet·race·build, Frontend 33 tests·format·build, Ruff·Helm·문서 링크. 전체 263개 Runbook API import E2E는 병합 전 통과했고 병합 후에는 관련 7개만 재실행했다.

- **통과:** Python 3.12.14, 루트 `python -m pytest -c agents/pytest.ini agents/tests -q`: 175 passed, 17 skipped. skip은 E2E 별도 실행 대상이다. Ruff check/format, 문서 링크 검사, Helm chart 계약 및 CI unittest 3건 통과.
- **통과:** 최신 로컬 소스로 빌드한 Go 서비스와 새 격리 PostgreSQL, 실제 Worker/NAT/공식 MCP 1.4.2를 사용했다. 전체 실행 최초 187 passed/4 failed 중 Fleet timestamp 전달 결함, fast-path의 구형 LLM 0회 기대, Helm 경로 누락을 수정했다. 실패 관련 webhook(native/Fleet)·fast-path 3건 및 MCP Host 3건 재검사 통과. 나머지 전체 실행의 E2E는 통과했다. 전체 통과 단일 실행으로 표현하지 않는다.
- **통과:** 실제 공식 MCP의 `data[].timestamp/line`와 원시 Loki `values` 모두 ns 시각 보존. Fleet D05/D09 각 31건 → 62개 관측 → Synthesis 호출 → JC 공개. 원본 기간 partial 유지, degraded D02 실행, R02 D08/D06 계획, 대상 미확인 시 mapping 부족 유지, 5개 보고서 섹션, 기존 snapshot/hash 유지.
- **통과:** Incident DB E2E 전체, 공유/Backend/JC/Incident `go vet`, `go test -race`, `go build`. Go 임시 소스 복사본과 새 바이너리를 사용했다. Frontend 24 tests·format·build 통과.
- **미검증:** 운영 배포, 실제 Fleet producer 시각 의미/freshness/GPU binding, 실제 Grafana·LLM 분석 품질. 상위 Grafana와 LLM은 fixture다. DB migration은 **해당 없음**. 로컬 pytest 임시 디렉터리 정리 권한 경고와 기존 MCP deprecation 경고는 테스트 실패가 아니다.

로컬 실행 기록: `.local/verify-rca-pipeline-e2e.py`, `.local/verify-rca-pipeline-selected.py`, `.local/run-rca-pipeline-incident-e2e.py`. `AGENT_E2E_DATABASE_URL`을 제거하고 새 `C:/Users/Public/rca-pipeline-<uuid>` DB를 만들었으며 종료 후 프로세스를 정리했다. 아래 최종 보고서 단독 변경 기록은 이번 후속 수정 이전 시점이다.

## 2026-09-30 RCA 최종 보고서

로컬 파일 구현·검증 단계. 근거 없음·승인 Runbook 없음·결정적 fast path에서도 다섯 섹션을 만들고 모델 문장 ID 편집을 시도한다. 미설정/확정 실패/무효 응답은 코드 기본 보고서로 대체하며, 원인 분석 상태·권고 적격성·snapshot/hash는 유지한다. 원격 종료 불명은 기존 Worker fail/격리를 유지한다. DB migration·배포·과거 작업 재분석은 하지 않았다.

| 기준 | 결과와 범위 |
|---|---|
| 두 Worker 일반 회귀 | **통과**: 저장소 루트에서 `.local/rca-dev-venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests -q --basetemp=.local/pytest-rca-final`: 164 passed, 16 skipped. skip은 별도 E2E/환경 조건이며 통과로 계산하지 않음 |
| 실제 프로세스 연동 | **통과**: `RUN_AGENT_E2E=1`, `test_e2e.py -k 'rca_without_observations or real_workers_nat_grafana_mcp_and_publication'`: 3 passed, 10 deselected. 근거 없음+편집 성공/HTTP 503, RCA→JC 공개, 기존 관측 Synthesis와 Ops 공개 RCA 인용 검증 |
| 내용·경계 | **통과**: 다섯 섹션 비어 있지 않음, 원천 REBOOT_SYSTEM 미검증/미수행 보존, 무효 문장 ID·응답 오류·모델 미설정 기본 보고서, RemoteUncertain 전파, 결과 상태 불변 |
| 정적 검사 | **통과**: `ruff check`와 `ruff format --check`를 `shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`에 실행. 문서 링크·diff 공백 검사 |
| 화면 | **통과**: Frontend 24 tests, build, format:check. 공개/미공개·기본 보고서·HTML escape. [Frontend QA](../frontend/QA.md) 참고 |
| 운영 | **미검증**: 실제 Fleet/Grafana 데이터·실제 LLM 품질/연결, 운영 배포, 전체 E2E 재실행(이번에는 관련 3건 실행). 운영 로그 파서 불일치나 datasource 문제를 해결한 변경이 아님 |

환경: Windows / Python 3.12.14 / 실제 격리 PostgreSQL 16.9, 기존 로컬 JC·Incident 바이너리, 실제 Worker/NAT/공식 MCP 1.4.2. Grafana 응답·LLM은 fixture다. `AGENT_E2E_DATABASE_URL`을 제거해 운영 DB를 사용하지 않았다. PostgreSQL 실행 파일은 기존 검증된 영문 경로, DB·로그는 새 `C:/Users/Public/rca-final-report-<uuid>` 아래에 두고 종료 후 서버를 정리했다. Python `mkdtemp()`의 Windows 제한 ACL은 권한을 낮춘 initdb를 막아 일반 mkdir 방식으로 교체했다. 검증 wrapper는 `.local/verify-rca-final-report.py`, 결과는 `.local/rca-final-report-e2e.xml`에 보존했다.

기존 결과 스키마 1.1·입력 1.3 유지. Backend/JC/Incident/Ops 제품 코드와 SQL은 변경하지 않아 해당 Go 전체 빌드/DB migration 검사는 **해당 없음**이며, 실제 JC 저장·공개와 Ops 인용은 위 연동 검사로 확인했다. 운영 반영에는 새 RCA Worker·Frontend 배포와 새 incident 실행 검수가 필요하다.

## 2026-09-30 Namespace 보고서 실행·표시 개선

기준: main `434006a` 이후 `feat/report-namespace-usability`. [설계서 §0.3](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)의 후속 개선이다. 운영 배포는 하지 않았다.

- **통과:** macOS arm64/Python 3.11.16/Go 1.26.2/PostgreSQL 16.9/NAT 1.5.0/Grafana MCP 1.4.2/Helm 3.17.3에서 전체 Python **173 passed**, 기존 MCP deprecation warning 3건. 아래 이전 기록의 전체 명령을 동일하게 실행하되 JUnit 경로는 `.local/agent-e2e/report-usability-results.xml`이다.
- **통과:** 실제 Backend POST → JC의 보고서 전용 criteria 1.2 고정 → 실제 Ops Worker/NAT/MCP → 공개 결과·저장 HTML/CSV checksum·Backend HTML 다운로드. 전역 criteria를 바꾸는 테스트 override를 제거했다. 두 Worker·참조·실패 격리 회귀를 함께 확인했다.
- **통과:** LLM 실패 시 성공 응답 0건과 HTTP 시도 3건 구분, 토큰 부족 시 미요청 사유, 기존 수치 보존. 설명 입력의 중복 evidence 참조만 생략하며 저장된 사실/근거는 보존한다.
- **통과:** Backend·JC·Incident에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. Backend의 `go test -tags=e2e ./tests -count=1 -timeout=10m`을 새 임시 PostgreSQL/loopback/테스트 schema에서 실행했다. 정기 보고서의 criteria 1.2·멱등 재전송, RCA의 전용 프로필 거부와 기존 criteria 보존을 확인했다.
- **통과:** Frontend 26 tests·포맷·빌드, Ruff lint/format, chart 계약·배포 도구 검사, 문서 링크·CRLF·diff 검사. 화면 검증 범위는 [Frontend QA](../frontend/QA.md)에 기록했다.
- **해당 없음:** DB migration·새 API·새 의존성·자동 운영 조치·RCA 계산 변경. 공통 LLM 진단 필드 추가는 두 Worker에 적용된다.
- **미수행/미검증:** 이 변경의 운영 배포·실제 Grafana/LLM·정책 조언 품질. E2E 상위 Grafana/LLM은 fixture다. 수집 제한 자체를 없애거나 D08 할당 계약을 확보한 변경이 아니며, 기존 결과는 재계산하지 않는다. 원격 CI 결과는 해당 PR에서 별도 확인한다.

## 2026-09-30 Namespace 관측 보고서 초안

사용자 검토용 초안을 로컬에서 구현·검증했으며 운영 배포는 수행하지 않았다. [Ops README](../ops-agent/README.md)의 criteria 1.2 O08 namespace 초안 범위다. RCA·공통 Python·Backend·Frontend·JC/Helm 제품 코드/설정은 변경하지 않았다.

- **통과:** macOS arm64, Python 3.11.16(지원 범위), Go 1.26.2, PostgreSQL 16.9, NAT 1.5.0, 공식 Grafana MCP 1.4.2, Helm 3.17.3에서 전체 **173 passed**, 기존 MCP client deprecation warning 3건. PostgreSQL/Go/MCP/Helm은 `.local/namespace-tools`에 준비했으며 다운로드 SHA-256을 확인했다.
- **통과:** 고정 입력에서 시간 가중 평균(80%×1시간 + 20%×0.5시간 → 60%), 실제 활동 0%, 같은 GPU의 순차 namespace 사용, 동시 공유, 다른 표본 시각의 유효구간 충돌, 중복 container 관측, Pod UID 재사용/모호성, 활동 부재·부분 관측·단위/범위 오류, MIG instance UUID, 혼합 모델, 다중 클러스터·빈 namespace·미지원 그룹을 검사했다. 연결 시간과 평균에 사용한 GPU-seconds 분모를 구분한다.
- **통과:** 새 테스트 전용 criteria 1.2 JC → 실제 Ops Worker/NAT/MCP → candidate 저장·JC 공개·HTML/CSV checksum 검증. 새 테스트는 독립 DB/schema를 사용하며 기존 RCA·Ops 검사의 전역 criteria를 변경하지 않는다. 최초 검사에서 같은 DB를 쓰던 두 테스트용 JC의 configuration_mismatch를 발견해 fixture를 분리한 뒤 전체 재검사했다.
- **통과:** 기존 criteria 1.1/unconfigured의 조회·O08 계산 유지, 기존 두 Worker·Runbook·실패 격리 회귀, Ruff lint/format, 문서 링크, CRLF 및 `git diff --check`.
- **해당 없음:** 새 API·DB migration·런타임 의존성·제품 설정 변경. 기존 공유 `gpu_intervals()`는 변경하지 않았으며 namespace 계산은 Ops 안에서 기존 구간/신원 함수를 재사용한다.
- **미수행/미검증:** 실제 Grafana/할당 의미·운영 LLM·실제 화면/Backend 다운로드 확인, 보고서 전용 criteria 활성화, 운영 배포·원격 CI. 상위 Grafana 응답과 LLM 응답은 fixture이며 정책 조언·회수량·실제 namespace 소비량은 검증/산출하지 않는다. 기본 전역 criteria는 unconfigured이므로 이 초안이 자동 활성화되지 않는다.

저장소 루트에서 `.venv/bin/ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`, `.venv/bin/ruff format --check`에 같은 경로, `.venv/bin/python tools/check_links.py`, `git diff --check`를 실행했다. 전체 검사 명령은 다음과 같다. 새 임시 DB/data directory·무작위 localhost 포트만 사용하고 종료 후 테스트가 만든 서비스를 정리했다.

```bash
env -u DATABASE_URL -u AGENT_E2E_DATABASE_URL \
  RUN_AGENT_E2E=1 \
  PG_BIN="$PWD/.local/namespace-tools/postgres/bin" \
  JC_BINARY="$PWD/.local/job-controller" \
  INCIDENT_BINARY="$PWD/.local/incident" \
  BACKEND_BINARY="$PWD/.local/backend-e2e" \
  GRAFANA_MCP_BINARY="$PWD/.local/namespace-tools/mcp/mcp-grafana" \
  HELM_BINARY="$PWD/.local/namespace-tools/helm/darwin-arm64/helm" \
  .venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q \
  --junitxml=.local/agent-e2e/namespace-results.xml
```

## 2026-09-29 Fleet JSON 조회 범위·Loki 응답 분할

- **통과:** Python 전체 **149 passed**, 기존 MCP client deprecation warning 3건. 실제 격리 PostgreSQL 16.9·Backend/JC/Incident·RCA/Ops Worker·NAT 1.5.0·공식 Grafana MCP 1.4.2 프로세스로 수집부터 결과 저장·공개까지 검사했다. 이 E2E의 Grafana/Loki HTTP와 LLM 응답은 fixture다.
- **통과:** D05/D09가 Fleet JSON의 노드·컴포넌트를 필터링하며 cluster/namespace·값 escaping을 유지한다. 알림 component를 장비 식별이나 검증된 사실에 넣지 않고, 원본 claim·Incident snapshot을 보존한다. 기존 native label 조회·Prometheus·Ops 경로도 검사했다.
- **통과:** 큰 Loki 응답을 동일 조건의 짧은 시간 구간으로 재조회하여 로그와 연속된 기간을 보존했다. 재조회는 예산을 소모하며 최소 구간 초과 응답은 partial, 예산 소진 뒤 남은 전체 기간은 unavailable로 남긴다.
- **통과:** 별도 수동 검증에서 체크섬을 확인한 공식 Loki **3.7.8**(revision `09e6ce2f`, macOS arm64)을 임시 로컬 저장소·loopback에 실행했다. 실제 수집기가 만든 D05/D09 쿼리는 기존 stream label·structured metadata의 임시 별칭 및 `_extracted` 이름이 충돌해도 JSON 값이 맞는 로그만 반환했다. 잘못된 노드·누락 필드는 제외되고 JSON 조건 없는 native D09는 원래 9건을 유지했다. 이 검증도 입력 로그는 합성 자료이며 운영 로그가 아니다. 종료 후 Loki 프로세스를 정리했다.
- **통과:** Ruff lint/format, Helm chart 계약 검사, 배포 도구 단위 검사, 설정 원본·Helm 미러 일치, 문서 링크, CRLF 및 `git diff --check`.
- **해당 없음:** 새 런타임 의존성, DB migration, 건강 상태 의미 규칙 변경. 기본 프로필은 `builtin-grafana-v2`, D05/D09는 `builtin-v2`이며 명시적 프로필 override는 별도 반영이 필요하다.
- **미수행/미검증:** 운영 배포·실제 Grafana/Fleet 관측과 RCA 품질·이 커밋의 원격 CI. 운영 반영은 main CI 발행 이후 담당자가 새 차트로 업그레이드하고 새 알림의 query/evidence를 확인해야 한다. producer/binding/freshness 계약 부족과 잘못된 시각을 이번 변경이 해결했다고 간주하지 않는다.

전체 Python 검사는 저장소 루트에서 `DATABASE_URL`·`AGENT_E2E_DATABASE_URL`을 제거한 뒤 `RUN_AGENT_E2E=1`, 로컬 `PG_BIN`·`JC_BINARY`·`INCIDENT_BINARY`·`BACKEND_BINARY`·`GRAFANA_MCP_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/agent-e2e/fleet-results.xml`로 실행했다. 별도 Loki 수동 검증 명령은 같은 루트에서 `.venv/bin/python /tmp/gpu-loki-query-validation/validate.py`였으며, 해당 임시 검수 스크립트는 저장소나 CI 의존성에 추가하지 않았다.

## 2026-09-29 Loki 조회 한도·MCP 오류 보존

- **통과:** macOS arm64, Python 3.12.14, PostgreSQL 16.9, Go 1.26.2, 공식 Grafana MCP 1.4.2, NAT 1.5.0에서 전체 **134 passed**, 기존 MCP client deprecation warning 3건. RCA·Ops 공통 수집기와 두 Worker의 결과 저장·JC 공개 회귀를 포함한다.
- **수정 전 재현:** 실제 NAT와 공식 MCP에 `limit=5000`을 보내면 fixture Loki HTTP 서버에는 5001건 요청이 전달됐다. 서버가 기본 한도 5000건을 적용해 HTTP 400을 반환하면 NAT가 오류 문자열로 변환하고 기존 수집기에서 `JSONDecodeError`가 발생했다. 새 통합 테스트가 수정 전에 실패하는 것을 확인했다.
- **수정 후 통과:** MCP 요청을 최대 4999건으로 제한하여 추가 확인 한 건까지 5000건 이내로 유지한다. D05/D09 조회 및 기존 RCA·보고서 Worker 통합 경로가 통과했다. 더 큰 Agent 행 예산, 최소 요청, D13, Prometheus 오류 격리도 단위 검사했다.
- **통과:** 행 수 제한 또는 `metadata.resultsTruncated`가 있으면 `partial / complete=false`를 보존한다. MCP 오류·비JSON 응답은 `query_failed`와 고정된 안전 오류 코드로 기록하며, 수집기 증거·진단 로그에 원문 오류와 시험용 비밀 문자열이 남지 않는지 확인했다.
- **통과:** Ruff lint/format, 문서 링크 검사, `git diff --check`.
- **해당 없음:** 새 의존성, DB migration, 배포 설정 변경. 공통 Python 코드가 포함된 RCA·Ops 이미지 갱신이 필요하다.
- **미수행/미검증:** 운영 서버 재현·배포·실제 Grafana/Loki 쿼리·LLM 분석 품질·원격 CI. 운영 서버 SSH 연결은 시간 초과됐다. 이번 검증의 Grafana/Loki HTTP 응답과 LLM 응답은 fixture이며 운영 장애의 상위 원인이 동일하다는 확정 근거는 아니다.

저장소 루트에서 `DATABASE_URL`과 `AGENT_E2E_DATABASE_URL`을 제거하고 `RUN_AGENT_E2E=1`, 작업 폴더에 설치한 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`를 지정하여 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/agent-e2e/results.xml`을 실행했다. fixture가 새 로컬 PostgreSQL 데이터 디렉터리·무작위 포트를 만들고 종료 후 정리했다. 운영 DB에는 접근하지 않았다.

## 2026-09-28 전체 XID/SXID 콘텐츠·폴더 분리·일괄 등록

- **통과:** 전체 **106 passed(일반 97 + E2E 9)**, 기존 MCP client deprecation warning 3건. 아래 103건 이후 전체 코드 콘텐츠와 일괄 등록 검사를 추가했다.
- **통과:** XID 173건·SXID 93건·일반 1건의 구조/등록 쿼리 검증, 기존 Fleet 카탈로그 264개 코드 포함 여부, manifest/파일 일치, 코드별 정확한 검색, 문헌 충돌·미정의 코드 보존.
- **통과:** 격리 PostgreSQL과 실제 Backend에 신규 263건을 `python -m rcca_agent.runbook_import`로 draft 등록하고 코드별 조회/hash를 확인했다. 같은 입력·batch key·receipts로 재실행하면 263건 모두 건너뛰며 새로 등록하지 않는다. 기본 변경 요청 한도의 429 대기·재시도도 실제 실행했다.
- **통과:** 기존 대표 3건의 검토·발행·RCA 소비와 두 Worker의 회귀 E2E. 별도 일반 검사에서 변경된 입력/receipt 불일치, 잘못된 형식·revision ID와 HTTP 재시도 시 동일 요청 키 보존을 검사했다.
- **통과:** Ruff lint/format, 문서 링크, diff 공백 검사. 전체 사전 검사 명령은 `python -m rcca_agent.runbook_import rcca-agent/runbooks --profile agents/config.example.json --dry-run`이며 결과는 267건 유효·쓰기 0건이다.
- **해당 없음:** DB migration·배포 설정 변경. 기존 Knowledge API/DB 계약을 사용한다.
- **미수행/미검증:** 운영 DB 등록·발행·배포, 실제 Fleet parser/버전·Grafana 쿼리·LLM 분석 품질. 266개 오류의 운영 RCA 정확도를 검증한 결과가 아니다. 모든 JSON은 빈 compatibility의 조사용 초안이다.

저장소 루트의 Python 3.12 환경에서 `RUN_AGENT_E2E=1`과 실제 Backend/JC/Incident/MCP/Helm 바이너리를 지정해 `python -m pytest -c agents/pytest.ini agents/tests -q`를 실행했다. 새로운 격리 PostgreSQL과 Windows ASCII scratch 경로를 사용하고 종료했다. Grafana 데이터와 모델 응답은 fixture다. 다른 PC의 설치·실행 절차는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md), 전체 파일은 [CATALOG](../rcca-agent/runbooks/CATALOG.md)를 따른다.

## 2026-09-28 XID/SXID DB 등록·발행·RCA 소비

최신 전체 결과는 **103 passed(일반 94 + E2E 9)**, 기존 MCP client deprecation warning 3건이다. 아래 102건 검증 이후 등록 생명주기 E2E를 추가했다.

- **통과:** 실제 Backend API로 오류별 JSON 3건의 draft 등록, 같은 키 재전송, 빈 compatibility 승인 거부, fixture cluster 조건을 부여한 새 revision, 명시적 검토·발행, XID/SXID namespace 검색, 실제 RCA Worker/NAT/MCP·Synthesis 소비, 원인 supported 승격 방지, retire 후 신규 검색 제외.
- **통과:** 기존 Incident webhook·일반 조사·보고서 소비·실패 격리 회귀를 포함한 전체 검사. 위 신규 사례의 사건 입력은 fixture이고 실제 webhook 검사는 별도 사례다.
- **통과:** Ruff lint/format, 문서 링크(93개 문서·831개 링크/자산), diff 공백 검사, Helm chart 계약 및 CI 계약 unit test 3건. Windows chart 검사는 HELM_BINARY에 helm.exe 절대 경로를 지정했다.
- **미검증:** 실제 Fleet parser·대상/버전/freshness·토폴로지, 운영 Grafana 쿼리·LLM 품질, 운영 DB 발행·배포. 저장소 JSON은 빈 compatibility의 조사용 초안이며 원인 판정용이 아니다.

실행은 저장소 루트의 Python 3.12 환경에서 `RUN_AGENT_E2E=1`과 실제 Backend/JC/Incident/MCP 바이너리로 `python -m pytest -c agents/pytest.ini agents/tests -q`를 수행했다. 격리 PostgreSQL과 Windows ASCII scratch 경로를 사용했다. Grafana 데이터·모델 응답은 fixture다. Backend 바이너리 빌드를 CI와 Windows test.ps1에 추가했으며 별도 Backend 검사 결과는 [Backend QA](../backend/QA.md), 다른 PC의 등록 명령은 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다.

## 2026-09-28 Runbook 콘텐츠 연계 후속 검증 (DB 연계 이전)

일반 조사 `RB-GENERAL-GPU-NODE`와 `RB-SXID-11001`을 추가해 작성 초안이 4건이다. `investigation_only` 일반 계획을 원인 판정·fast path 근거에서 제외하고, 선택된 Runbook의 revision·적용 상태·analysis_guidance·limitations를 Synthesis에 전달했다.

PR 준비 최종 재검증: **전체 102 passed(일반 94 + E2E 8)**, 기존 MCP client deprecation warning 3건. 아래 101건 및 94건 분리 실행 이후 같은 격리 환경에서 전체를 다시 실행했다. 원격 CI 성공을 의미하지 않는다.

- **통과:** 전체 실행 101건(일반 검사 93 + 실제 프로세스 E2E 8). 일반 JSON에 격리 테스트 cluster 호환성만 부여해 DB에 발행한 뒤 실제 JC/Worker/NAT/MCP 수집·Synthesis 요청·저장·보고서 인용을 검증했다. Grafana 데이터와 LLM 응답은 fixture다.
- **통과:** 추가한 일반 Runbook 표시 누락 방어를 포함한 RCA 분석 검사 13건, 최종 일반 검사 재실행 94건. Xid/SXid JSON의 검색·수집 계획 소비 및 오류 코드 fact 미확인 시 candidate 유지, 잘못된 일반 판정 콘텐츠 거부를 확인했다. 운영 producer/parser 검증은 아니다.
- **통과:** Ruff lint/format, 문서 링크, diff 공백 검사. 실행 명령과 격리 환경은 아래 실행부 검증과 같으며 단위 검사에는 `--basetemp=.local/pytest-runbooks`를 사용했다.
- **미검증/미수행:** 실제 Fleet 로그 parser·대상/버전/freshness 계약, 당시 Backend 발행 단계의 v1 validator 연결(위 후속 검사에서 완료), 운영 발행·LLM 연결·배포. 네 초안의 빈 compatibility는 운영 실행을 차단한다. GPU reset·재부팅·진단 도구 실행은 하지 않았다.

세부 작성·실행 계약은 [Runbook README](../rcca-agent/runbooks/README.md)에 기록했다. 새 DB 구조나 운영 설정 변경은 없다.

## 2026-09-28 RCA 병렬 조사·Synthesis 구현 검증

로컬 파일 개발 단계다. [보완 계획](../docs/specs/rca-agent/implementation-plan-20260928.md)의 입력 1.3 실행부를 구현했다. 실제 LLM endpoint 연결, 운영 Runbook 발행, 배포는 수행하지 않았다.

| 검사 | 결과·검증 범위 |
|---|---|
| 단위/Worker + 실제 프로세스 E2E | **99 passed**: 일반 검사 91개 + E2E 8개. Python 3.12.14 / NAT 1.5.0 / 공식 Grafana MCP 1.4.2 / PostgreSQL 16.9 |
| 수집·분석 | 기존 근거 충분 시 MCP·LLM 0회, 승인 일반 Runbook 대체, 발행본 없음→조회 0회, 병렬 수집·예산 예약·실패 격리·취소 회수, 최대 1회 재조사, 도구 없는 최종 Synthesis |
| 모델 경계 | 없는 근거 참조·추가 query·인과 수준 필드·숫자 claim 거부. 잘못된 계획/분석 응답의 근거 보존, endpoint 미구성 표시, 원격 종료 불명의 Worker 격리 경로 |
| 입력·저장·보고서 | 실제 Incident webhook→JC→RCA Worker→NAT/MCP→DB candidate→JC 공개. 원문/hash와 provider action 미수행 보존. 공개 RCA ID/hash의 보고서 인용 및 기존 에너지 계산·실패 격리 회귀 |
| MCP 시간 정밀도 | 실제 webhook 마이크로초 시각으로 Loki parser 실패를 재현한 뒤 공통 시간 변환으로 해결. 조회창 확장 없이 밀리초 경계 사용, 줄어든 구간은 `time_precision_reduced`/partial 기록. 두 Worker 공통 경로 검사 |
| 정적/배포 검사 | Ruff lint·format, 문서 링크, `tools/ci/check_chart.py`(Helm 3.17.3), CI 계약 unit test 3개 통과 |
| 미검증 | 운영 Grafana/Mimir/Loki 쿼리 평가·인증·producer 의미, 실제 모델 품질, Fleet 오류 fact parser·binding·freshness, 입력 1.4 목적 자동 선택·이력 고정, 운영 배포 |

저장소 루트의 Python 3.12 venv에서 `python -m pytest -c agents/pytest.ini agents/tests -q`를 실행했다. `RUN_AGENT_E2E=1`, 실제 JC/Incident/MCP 바이너리, 검증한 Helm 3.17.3을 지정했다. Windows 한글 경로의 PostgreSQL 초기화 문제 때문에 테스트의 `LOCAL` scratch 경로만 ASCII 임시 폴더로 바꾼 로컬 runner를 사용했다. 매 실행 새로운 data directory와 무작위 localhost 포트를 사용하고 종료했다. 운영 DB 환경변수는 재사용하지 않았다.

Grafana datasource HTTP 응답과 모델 응답은 fixture다. 일반 Runbook은 격리 DB에만 넣은 계약 fixture이며 운영 콘텐츠가 아니다. MCP Host 보호 회귀 3건도 실제 바이너리로 통과했다. 기존 MCP Python client의 deprecation warning 3건은 남아 있으며 실행 실패는 아니다. Incident Go 검증은 [Incident QA](../incident/QA.md)를 따른다.

Ruff 명령은 `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`, `ruff format --check`에 같은 경로를 사용했다. 문서/차트/CI 검사 명령은 `python tools/check_links.py`, `python tools/ci/check_chart.py`, `python -m unittest discover -s tools/ci/tests -v`다. 최종 전체 실행 로그/XML은 로컬 `.local/rca-e2e-results.xml`에 보관한다.

## 2026-09-18 Incident → RCA 계약 회귀 검증

실제 Incident는 `snapshot.alert`를 저장하지만 RCA가 `snapshot.evidence`만 읽어 실패하던 문제를 수정했습니다. 새 회귀 테스트를 먼저 추가해 수정 전 실제 웹훅 경로의 RCA 작업이 `failed`가 되는 것을 재현했습니다. 수정 후에는 snapshot을 변경하지 않고 `alert`를 읽으며 legacy `evidence`도 지원합니다. 원본 알람 필드를 검증된 사실로 승격하지 않습니다.

- 단위/Worker 테스트 29개와 실제 프로세스 E2E 5개, 총 **34 passed**.
- 새 경로: Grafana 형식 HTTP webhook → 실제 Incident 저장/outbox → 실제 JC → 실제 RCA Worker/NAT/공식 Grafana MCP → 결과 저장/JC `succeeded`.
- 이 회귀 테스트는 Incident snapshot이나 RCA job을 DB에 직접 삽입하지 않습니다. Incident가 생성한 R01/R02 목적, 원본 alert, evidence snapshot과 hash 보존을 확인합니다.
- 별도 프로필 없이 datasource 자동 탐색, 기존 legacy snapshot·Runbook·보고서·실패 격리 경로도 통과했습니다.
- Ruff lint/format, actionlint, 문서 링크 검사를 통과했습니다. CI와 Windows 테스트 스크립트에 실제 Incident 바이너리 빌드를 추가했습니다.

Windows 로컬 PostgreSQL 초기화는 샌드박스의 restricted-token 오류 때문에 일반 사용자 권한에서 격리된 테스트 DB로 실행했습니다. Grafana/Mimir/Loki와 LLM 응답은 fixture이며 운영 연결이나 실제 모델 품질을 검증한 것은 아닙니다. 아래 2026-09-17 기록의 RCA snapshot 테스트는 DB에 직접 넣은 fixture였으며 실제 Incident 생산 형식을 검사하지 못했습니다.

## 이전 검증 기록

검증일: 2026-09-17, Windows, Python 3.12.14, NAT 1.5.0, 공식 Grafana MCP 1.4.2, PostgreSQL 16.9, 저장소의 실제 Go Job Controller.

## 실행 결과

| 검사 | 결과 |
| --- | --- |
| 최소 단위/Worker 테스트 | 8 passed |
| 실제 프로세스 E2E | 3 passed |
| Ruff 정적 검사 | 통과 |
| Python compile/모듈 import | 통과 |
| Docker Compose 구성 구문 검사 | 통과 (`config --no-env-resolution -q`) |
| 공식 MCP Windows 릴리스 SHA-256 | 검증 |
| 공식 Docker 이미지 `grafana/mcp-grafana:1.4.2` 태그 | 존재 확인 |
| Linux Docker build/up | NOT RUN — 사용자 안내에 따라 Windows 프로세스로 대체 |
| 운영 Grafana/Mimir/Loki·실제 LLM endpoint | NOT RUN — 해당 연결 정보/키가 제공되지 않음 |

## 최소 테스트

- 전용 할당 합집합 중복 제거, 공동 유효 구간 교집합.
- 58분 공동 관측/54분 저활동 고정 사례, 5분 할당·30분 Pod 교체 후보 보류.
- 시간 가중 평균/P95, 좌측 유지 전력 적분, 공백·중복 충돌 처리.
- 검사 불가+Healthy → unknown, Go JSON 호환 hash, reasoning tag 제거.
- 호환성 제한 후 최신 Runbook 선택.
- 주제별 ready/partial/blocked 집계, HTML escape·CSV 수식 방어.
- 실제 LLM 요청 형식 및 timeout 시 원격 종료 unknown.
- scope escaping·등록 query ID·조회 예산·기간 범위 제한.
- 비동기 heartbeat 중 취소, 미종료 LLM unknown 보고, 저장 실패 시 complete 미호출.

## E2E 경로와 단언

실제 구성: 테스트 전용 PostgreSQL → **실제 JC HTTP API** → **별도 Worker 프로세스** → **NAT workflow/MCP client** → **공식 Grafana MCP Windows 서버**.

Grafana datasource HTTP 응답과 OpenAI 호환 LLM endpoint만 고정 데이터 서버로 대체했습니다. 따라서 실제 Mimir/Loki 엔진의 쿼리 평가·운영 인증·실제 모델의 진단 품질을 검증했다는 의미는 아닙니다.

1. Incident snapshot → RCA claim → Loki 로그 조회 → LLM의 등록 D02 선택 → Mimir 호환 원본 표본 조회 → 상태 정규화·후보 저장 → JC complete. 이어 보고서가 공개된 RCA ID/hash를 인용하고 GPU 전력 250W×1시간=0.25kWh를 산출합니다. DB 저장 본문 hash, HTML/CSV 파일 checksum을 확인합니다.
2. LLM 503 + Loki 실패 시에도 O09 에너지 0.25kWh를 보존합니다. O10은 blocked, 설명은 failed이며 독립 주제를 지우지 않고 JC가 결과를 발행합니다.
3. O01~O11 전체 결과가 주제별 상태를 유지합니다. 호환 발행 Runbook의 필수 증거가 이미 충분한 R01은 추가 MCP 조회 없이 조건·권고를 평가하고 supported 후보를 발행합니다.

실행 명령: `./agents/scripts/test.ps1 -E2E -PgBin ./backend/.local/postgres/bin/bin`

테스트는 임시 포트와 새로운 DB data directory를 사용하며 기존 DB 데이터에 접근하지 않습니다. 이번 테스트의 로그와 보고서 파일은 `.local/agent-e2e/`에 있습니다. 초기 Windows PostgreSQL 관리자 직접 실행/파이프 상속 오류는 `pg_ctl`의 권한 처리와 DEVNULL 출력으로 수정했습니다. 실제 Grafana MCP가 Prometheus query를 form POST로 전송하는 동작도 fixture에 반영했습니다.

## 남은 운영 검수

배포 C02~C07의 실제 datasource UID/CPC 필터/metric 의미/원본 주기/조회 한도, Fleet parser 계약, 할당/작업 신원·완전성, 기대 대상 분모를 설정해야 합니다. 설정이 없는 판단은 null/partial/blocked입니다. 실제 도구 호출 모델 호환성, 실제 GPU 부하·공백·장기 이력과 C08 회복 정책은 운영 표본으로 별도 검수해야 합니다.

## 2026-10-01 Korean RCA prose / 한국어 문장·조회 표기 검증

기준 `origin/main` `529df747173e76a908ff2d56b1ac3688c4a3e648`, 브랜치 `fix/rca-report-korean-labels`. 로컬 파일 변경 단계이며 commit·push·PR·배포 없음.

- **통과:** Python 3.12.14 격리 환경에서 `python -m pytest -c agents/pytest.ini agents/tests -q -rs --ignore=agents/tests/test_gpu_node_scope.py -p no:cacheprovider --basetemp=.local/rca-korean/pytest-final`: **269 passed, 17 skipped**. 두 Worker의 추적 대상 단위·모의 lifecycle 검사와 새 한국어/숫자 단어/일반 단어 오탐/입력 식별자/정밀도 조건/단정/전체 D-query/사전 일치 회귀를 포함한다. `synthesize()`에 실제 전달되는 query_quality도 모의 모델로 검사했다.
- **실패(기존 사용자 파일):** 전체 `agents/tests` 실행에서 작업 시작 전부터 존재한 미추적 `test_gpu_node_scope.py`의 2건이 실패한다. `gpu-node-rca-v1` 및 `gpu_node`를 기대하지만 현재 기준 코드 값은 `gpu-alert-v1`·`gpu_access`다. 해당 파일과 정책·procedure를 수정하지 않았다. 전체 검사를 통과로 표시하지 않는다.
- **통과:** CI 범위 `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci` (ruff 0.14.0). **실패:** 같은 범위 `ruff format --check`는 기존 미추적 `test_gpu_node_scope.py` 1파일 때문에 실패. 이 파일을 제외한 66파일은 통과했다.
- **통과:** 운영 작업 `ed730b4d`, `1e48ed0f`, `e24b3f20`의 해당 발행 시도 evidence와 result body를 `default_transaction_read_only=on`, `SHOW transaction_read_only=on`으로 읽고 로컬 보고서를 재생성했다. D02/D05/D06/D08/D09를 모두 표시하고 D06은 5개 구간으로 묶으며 표본 합산이 없다. 구 작업의 D05/D09는 정밀도 partial, 새 두 작업은 ok, D08은 모두 empty다. DB 변경·모델 재호출은 없다.
- **통과:** 저장된 문장 재검증에서 `1e48ed0f`의 영어 후보 2개는 `non_korean_claim`, 영어 한계 6개는 `invalid_limitations`; `e24b3f20` 후보 2개는 숫자 단어 제한, 영어 한계 4개는 `invalid_limitations`로 거부했다. 원래 모델 응답/view는 저장되지 않아 저장 문자열 재현 범위이며 당시 모델 품질 전체 검증이 아니다. 운영 원문 비교표는 Git 제외 로컬 `.local/rca-korean/production-comparison.md`에만 보존한다.
- **미수행/미검증:** Go 실행 파일이 없으며 공식 MCP·격리 PostgreSQL/JC·Helm 준비가 없어 17개 실프로세스 E2E가 건너뛰어졌다. 실제 LLM/Grafana 새 실행, 운영 배포 후 표시·언어 품질, 원격 CI는 미검증이다. Docker는 사용하지 않았다. mock lifecycle와 읽기 전용 저장 결과 재현을 실환경 새 실행으로 해석하지 않는다.
- **해당 없음:** Go 코드·DB migration·Fleet 시각 계약·충분성 gate·R01/R02 `REQUIRED`·결과 스키마 변경. 기존 결과는 재작성하지 않는다.

- **문서 검사:** 전체 `python tools/check_links.py`는 기존 미추적 `_review_current/`·`_codex_dcgm_publish/` 안의 경로 7건으로 실패했다. 두 기존 검토용 폴더만 제외해 같은 `check()`를 실행하면 변경 문서를 포함한 링크 검사는 통과한다. 이 폴더들은 수정하지 않았다.

## 2026-10-01 ci.110 후속 수정 — 로컬 검증

- `ruff check` / `ruff format --check`: 통과. 일반 pytest 284 passed, 17 skipped. 이후 격리 PostgreSQL 16.9(127.0.0.1:55432) + 실제 Incident/JC/두 worker + 공식 Grafana MCP 1.4.2 프로세스로 전체 실행: 299 passed, Helm 경로 누락 2 failed. `HELM_BINARY` 설정 후 실패한 두 사례만 재실행: 2 passed. 서로 다른 301개 사례 모두 통과, 남은 skip 없음. Grafana·LLM 응답은 fixture이며 운영 모델 품질 검증이 아니다.
- `python tools/ci/check_chart.py`: 실제 Helm 3.17.3 lint/template/package 계약 통과. `python -m unittest discover -s tools/ci/tests -v`: Git Bash 경로 설정 후 5 passed.
- 저장된 9684a61e 증거의 로컬 재생: 62개 장비 관측 → 고유 31개, Loki 호출 1회, gpu_pod → gpu_access. 고정 모델 응답 fixture에서 synthesis complete; 실제 실패 원문은 미보관이라 원인 문장 재현/운영 모델 성공을 입증하지 않는다. `partial/missing_data`와 R01/R02 partial 유지.
- 실제 사건 구간 D02에는 GPU UUID/node는 있지만 Pod·namespace 라벨이 없다. D08을 DCGM으로 바꾸어도 해당 사건의 Pod를 확정할 수 없다. inventory 로그도 장비 사건 시각·freshness 계약이 없어 신원 후보로만 보존한다.
- `DCGM_FI_DEV_XID_ERRORS`의 해당 구간 가용성은 미검증. 기본 D05는 D09 파생 보기를 사용한다. 전역 metric 부재나 모든 GPUAlert의 R01/R02 충족 불가를 주장하지 않는다.
- 운영 배포·동일 incident의 운영 재실행·실제 모델 품질 검증은 미실행. 과거 evidence/result와 hash는 변경하지 않았다.

### 2026-10-06 후속 preflight 근거 대조

세 서버의 사용자 제공 preflight를 [환경 원장](../docs/evidence/d-binding-cpc-20261006.md)에 반영했다. KSM 버전·Exporter/HostEngine digest와 중앙 ConfigMap JSON의 LF 해시 일치를 확인했다. 90개 환경 항목은 모두 미선택 candidate이며 82개에 버전 근거가 있다. CPC-2 rulefiles ConfigMap 읽기 실패 4건과 중앙 보존·실제 CSV/전송 설정·Worker 로드 검수의 한계는 유지한다.

이 후속 변경은 원장/문서만 수정한다. 첨부 파싱·버전 및 해시 대조, 후보 상태·공통 JSON/Helm 불변, 문서 링크를 검증했다. 제품 코드·배포·DB는 변경하지 않아 기존 496개 회귀/E2E를 다시 실행하지 않았다. 새 서버 출력은 fixture E2E를 실환경 Worker/LLM 검수로 승격하지 않는다.

### 2026-10-07 수집 설정 후속 근거와 진단 도구

CPC-1의 두 Exporter CSV 동일성·25개 선언·D26/D27 미포함, 양쪽 Fleet 1m 설정, CPC-2 CSV 읽기 실패와 중앙 보존 미확인을 환경 원장에 추가했다. 실행 JSON과 Helm 사본은 변경하지 않았다. 새 `tools/ci/binding_details.py`는 부분 실패에도 성공 근거를 유지하고 오류 단계를 출력한다. 도구 회귀는 로컬 fixture이며 실제 서버에서 새 버전을 실행한 결과가 아니다. 두 Worker 런타임은 변경하지 않았고 실환경 활성화/LLM/Runbook 발행/배포는 미완료다.

검증: 저장소 루트에서 `python -m unittest discover -s tools/ci/tests -v` **12개 통과**(신규 진단 7개 포함), 변경 Python 두 파일 Ruff lint/format 통과. Windows 첫 시도의 Bash 경로 누락은 설치된 Git Bash를 PATH에 연결한 재실행으로 해결했다. 원장/원본 해시·90개 candidate/82개 버전·JSON/Helm 불변 검사를 통과했고, 추적 소스 사본의 링크 검사 **105개 문서 / 1,332개 링크 / 오류 0개**를 확인했다. 기존 제품 Worker 회귀는 런타임 불변이므로 재실행하지 않았다.


### 2026-10-07 정확한 이미지 CSV 및 실제 설정 조회 준비

CPC-2 보고 digest의 NVIDIA 공개 OCI index/두 architecture manifest/후속 레이어를 해시 대조하여 CSV 26개 선언(gauge 20/counter 5/label 1)을 확인했다. 두 architecture의 CSV 해시가 같고, CPC-1 대비 FB_RESERVED만 추가됐다. 이미지 근거이며 실행 중 컨테이너 파일 읽기나 표본 방출 검증을 대체하지 않는다.

중앙 `--effective-config` 모드는 실행 중 Mimir/Loki의 명시된 HTTP 포트를 통해 Kubernetes Pod proxy GET으로 `/config`와 `/runtime_config`를 읽는다. 발췌 결과는 tenant 부모 키를 익명화하며 YAML 의미 해석/운영 활성화를 수행하지 않는다. 회귀 4개를 추가하여 도구 전체 **16개 통과**, 변경 Python Ruff lint/format 통과. 서비스 실호출은 서버 접근이 없어 미수행이다. Worker·공통 실행 JSON·Helm은 변경하지 않았다.


### 2026-10-07 CPC 직접 수집 환경 profile

Alloy 원문 해시 일치와 직접 수집 8개 메트릭 allowlist를 확인했다. `config.cpc-direct.json`에 CPC별 7개씩 14개 binding을 선택했다. 두 Worker 공통 로더/미선택 로그 차단/미등록 cluster 차단/D20 gauge 소비의 신규 5개 fixture 검사를 통과했다. D20 gauge는 Node 상태 관측으로만 처리하며 GPU health로 해석하지 않는다.

저장된 실환경 원본을 공통 Observation과 Report/RCA 소비 함수에 재생하여 CPC별 7개 쿼리·원본 불변·D20 관측·health fact 미생성을 확인했다. Report는 미선택 입력 때문에 partial이다. 신규 환경 profile의 운영 적용·실제 LLM/JC 발행 검수는 미완료다.

검증: 저장소 루트의 Python 전체 suite에서 **501 passed, 0 skipped**(138.43s). `RUN_AGENT_E2E=1`, 외부 DB 환경변수 제거, 임시 로컬 PostgreSQL 16.15 및 실제 JC/Incident/두 Worker/공식 MCP 프로세스를 사용했다. Grafana·LLM은 fixture 응답이다. 최신 main `8f24bda`의 추가 변경은 UI이며 Python 검증 대상 파일은 동일하다.

최종 무효값 규칙 수정 후 관련 81개(환경 profile 7개 포함)와 실제 원본 재생을 재실행해 통과했다. Helm 전체 계약 및 환경 override의 JSON 의미 동일성 검증을 통과했다. 큰 sentinel float 재직렬화 차이는 안전한 정수 범위 상한으로 해결했다. 초기 chart 검사는 Windows cp949 오류였으며 `-X utf8` 재실행으로 통과했다.
# Fleet structured events — 2026-10-08

`fix/fleet-state-evidence`: D09의 등록된 Fleet kmsg event를 상태 요약과 분리해
RCA 모델 입력과 `quality.analysis.error_events`에 보존한다. 요청 대상 불일치,
시각 누락/범위 이탈, 코드 namespace/원문 충돌, 미등록 계약, 잘린 조회는 제외한다.
GPU inventory는 후보 연결이고 SXID를 GPU에 연결하지 않는다. 주입·실제 오류의
공통 kmsg 경로를 소스로 비교했으며 테스트 PCI 주소 불일치를 실제 장애로 일반화하지 않는다.

격리 로컬 검증: 전체 Agent 비-E2E 645 passed, 35 deselected,
Runbook API lifecycle·RCA 발행·전체 Report topic
선택 E2E 4 passed, 21 deselected. 공식 MCP/실제 Worker·Backend·JC 프로세스와
로컬 PostgreSQL을 사용했으며 Grafana/LLM은 fixture다. 운영 DB에 테스트하지 않았다.
후속 코드의 운영 배포·새 RCA 결과 검수·정상 발생 오류와 호스트 커널 기록 대조는 미완료다.
사용자 출력으로 #87의 계약/보고서 진단은 운영 RCA Pod 3개 모두 반영 확인했다.


### 2026-10-12 기본 보고서 수집·본문 최소화

기준은 원격 main `029fbed`이며 criteria 1.3 + 통합 binding의 기본 O01/O08/O11 구성을 대상으로 한다. O01에서 D15/D18/D19 추가 지표를 제거하고, D06 Namespace 한정을 안전한 기본 조합으로 확장했다. D02가 불완전하거나 다른 D06 소비 주제가 섞이면 넓은 조회를 유지한다. Node 상태 초 단위 요약과 원본 증거 참조는 남기되 전체 관측 구간의 결과 본문 복사는 제거했다. criteria 1.2, O03/O04의 D15, RCA 계산은 유지한다.

`agents/tests/benchmark_report_minimization.py`를 기준 코드와 변경 코드에서 각각 5회 실행했다. 합성 1시간 데이터, GPU 1개, 무관한 Namespace의 Pod 200개, Node condition 153계열/36,720구간이며 네트워크·실제 MCP·DB·LLM 지연은 없다. 유지한 모든 지표의 값·단위·대상·기간·계산 방식·상태·부족 사유는 동일함을 비교 assertion으로 확인했다. 제거한 6개 추가 지표 이름과 실행마다 변하는 ID/참조는 동등성 비교에서 제외한다.

| 측정 | 기준 | 변경 |
| --- | ---: | ---: |
| 조회 종류/호출 | 11 | 8 |
| 수집 응답 JSON | 1,524,067 B | 667,834 B |
| D06 응답 JSON | 839,195 B | 4,215 B |
| 저장할 원본 snapshot JSON | 1,524,153 B | 667,920 B |
| 결과 본문 JSON | 1,132,945 B | 147,491 B |
| 로컬 수집/계산 전체 중앙값 | 496.9 ms | 191.4 ms |
| 결과 직렬화 중앙값 | 107.5 ms | 5.65 ms |

운영 서버의 실제 호출 수/기간/데이터량과 다르므로 이 비율을 그대로 운영 성능 개선율로 보장하지 않는다. D06 절감폭은 제외할 Namespace가 얼마나 많은지에 따라 달라진다. 기존 보고서의 읽기 전송량/메모리 검증은 [Backend QA](../backend/QA.md)를 따른다. 운영 배포·기존 보고서의 실제 삭제·운영 환경 응답 시간 재측정은 수행하지 않았다.

---

## 2026-10-12 RCA general admission and bounded final editor

Isolated worktree verification (Python 3.11): `pytest -c agents/pytest.ini agents/tests -m "not e2e" -q`:
982 passed, 37 deselected. New tests use completed length-limited HTTP replies to verify
compact retry, token/deadline refusal and original statement retention; cancellation
and uncertain execution still propagate. General observation admission keeps old revision
requirements unchanged and never grants health, cause or action eligibility. Existing
power/PCIe evidence regressions confirm unknown/cause gaps without falsely requiring
current health merely to collect general observations.

`RUN_AGENT_E2E=1 ... pytest ... test_e2e.py -k "rca_without_published_runbook or rca_numeric_repair"`:
3 passed, 24 deselected with temporary local PostgreSQL, JC, Incident, real Worker/NAT
and official Grafana MCP; Grafana/LLM upstreams were fixtures. No production DB used.
Frontend 199 tests, formatting and build passed (existing >900 kB bundle warning).
Ruff check/format and documentation links passed. Production deployment, new general
revision publication and live LLM truncation recovery remain unverified.

2026-10-12 operator wording follow-up: stable headline under reversed LLM ordering,
separate target/time/raw alert/identity and preserved references covered by a new test.
Local publication E2E repeated: 3 passed, 24 deselected. Operational reports untouched;
new wording requires a new RCA after deployment, not a rewrite of old published results.


## 2026-10-14 Common repair invariants and offline Runbook transition review

Local Python 3.12 verification in the isolated recovery checkout:
`pytest -c agents/pytest.ini agents/tests/test_rca_analysis.py agents/tests/test_synthesis_context.py agents/tests/test_runbook_transition.py agents/tests/test_rca_rule_selection.py agents/tests/test_runbook_contract.py -q`: **339 passed**.
`RUN_AGENT_E2E=1 ... pytest -c agents/pytest.ini agents/tests/test_e2e.py -k rca_json_selection_and_safe_subset_survive_publication -q`: **2 passed, 32 deselected**.
The E2E uses temporary local PostgreSQL, JC/Incident, real RCA/NAT/official MCP and
fixture Grafana/LLM responses; it does not validate live model compliance.
The initial sandbox run could not use local HTTP; the completed run used the
same tests with local socket access. Initial E2E setup used incorrect binary
environment names; corrected fixture variables passed both cases.

The offline published snapshot review covers the remaining 265 keys: 196
contract-valid proposals, 69 held (64 unresolved definitions, 5 informational
codes). This is not semantic approval or publication. Original evidence requirements,
claims, applicability, source references and recommendations are unchanged.
Unknown gaps alone cannot select the proposed auxiliary queries; scoped report
facts (or general observations) are prerequisites. Query results cannot establish
hardware identity or cause. No Pod/workload investigation was added.

Real execution after these local edits, per-code source applicability review,
operator-guidance conversion and deployment-profile revalidation remain pending.
No production revisions were created, approved, published or retired in this change.
