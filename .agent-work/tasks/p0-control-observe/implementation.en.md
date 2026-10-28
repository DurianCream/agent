# P0 control contracts and observe policy implementation

Task: p0-control-observe.
Scope: multi / agent-framework / development / p0-control-contracts-observe.
Baseline: 3b557bef3d5ba1029e1cddf95e80dd0cd1b22889.
This is the implementation contract for the two requested P0 components. The submitted task result records actual verification and completion.

## 1. Scope and authority boundary

Implement strict contract validation and deterministic observe-only policy assessment. Preserve the existing role IDs, source instructions, common result1.0 and historical design/task snapshots.
Governance recommendations and evaluator assessments remain advisory; neither is parsed as an execution grant.
No executor, enrollment ledger, approval service, credential broker, signature authority, production adapter or monitoring scheduler is installed.
The observer accepts declared simulation inputs. Local context and policy files do not establish trusted host identity or authorization.
Every observation is explicitly non-executable and authority-unverified, even when its decision is allow.

## 2. Contract component

runtime/control_contracts.py provides bounded strict JSON loading, local schema validation, RFC8785 canonical digests and envelope checks.
The promoted envelope schema retains the0.1.0 structure from the prior reviewed design; metadata distinguishes implemented validation from future authentication.
Reject duplicate keys, invalid UTF-8, lone surrogates, non-finite numbers, unsupported P0 number forms, excessive input/depth, unknown schema fields/types/versions, wrong envelope digests and supported semantic contradictions.
The P0 profile uses safe integers; full RFC8785 string ordering is supplied by a pinned library rather than a sorted-JSON substitute.
Limits are 128 KiB, 32 nesting levels and 10000 nodes. UTC timestamps use uppercase Z and at most 6 fractional digits; excess precision is rejected rather than silently truncated. Required date-time/URI/UUID checks are registered explicitly with pinned offline dependencies; unsupported schema formats fail closed.
Envelope digest binds exactly record_type, schema_version and payload. It does not include the digest or signature field recursively.
Schema and hash validation are distinct from signature authentication, evidence truth, freshness in a real trusted system and policy authorization.
Local schema references are resolved offline. Input files cannot select an arbitrary remote schema or trigger URL retrieval.
Every resolved local subschema is meta-validated, including references into extension properties. Schema runtime failures are normalized without exposing data through exception chains.
Validation failures expose stable reason codes and safe messages, not raw untrusted values or file contents.

## 3. Policy component

runtime/control_policy.py evaluates a validated action_request against a strict declared context and an observe policy.
The context defines the simulated task/principal/scope, known targets and bounded authorization conditions. The engine never infers a missing project/service/environment/issue.
The policy includes allowed operation classes and risk treatment; caller-provided prose cannot override it.
Bind observations to input/context/policy digests and compare request policy references to the supplied policy.
Check supported scope/target/authority constraints, expiry and policy limits before assigning allow, deny or require_review.
Unknown, malformed or mismatched inputs fail closed as an invalid assessment or deny observation; they never imply permission.
An exact previously declared standing Git authorization may yield an allow observation without asking for new approval. It cannot expand to another remote, branch or manifest.
Otherwise-permitted high-risk effects remain require_review; credential export, prohibited operations and insufficient known authority cannot become allow through a governance recommendation.
Data classifications are declared inputs. No actual content scanning, artifact dereferencing, target inspection or secret-detection guarantee is provided.

## 4. CLI and data handling

runtime/controlctl.py exposes validate --input and observe --input --context [--policy]. No enforce or execute command exists.
It reads only the explicitly selected request/context/policy and fixed local schemas, emits bounded JSON and does not write audit files or execute request actions.
Output observations contain stable codes, enums, digests and limitation flags. Never print the complete request/context or supplied secret-bearing values in errors.
Synthetic fixtures are not credentials. Fixed-time fixtures can produce expiry denial under the current clock; deterministic tests inject their clock through the API.
Input references are not followed to artifact bytes, local credentials, URLs or external systems.

## 5. Dependency and compatibility contract

runtime/control-requirements.txt pins direct and transitive dependency versions. The task tests them in an isolated temporary dependency directory with Python3.12; the documented minimum is Python3.11.
Dependencies are not installed automatically by runtime imports or the CLI. Missing dependencies must produce actionable safe diagnostics.
The common limited-keyword agentctl schema validator is unchanged. New contract schemas use their own full draft2020-12 path.
Adding an observe policy file does not make it a trusted active execution policy, and current agentctl initialization does not automatically enroll it in a control authority store.
Existing result submissions, exact Git publication and task memory continue through their prior implementations.

## 6. Required verification

- Normal contract and request types plus unknown keys/types/versions and adapter mismatch.
- Known canonical Unicode ordering vector, duplicate keys, malformed encoding, unsafe numbers, nesting and input bounds.
- Tampered envelope data/digest and supported timestamp/result semantic contradictions.
- Each scope field mismatch, missing/unknown context or policy, policy digest mismatch and stale requests.
- Exact declared standing authorization and otherwise-permitted high-risk review paths.
- External instruction-like strings cannot add fields or turn a recommendation into authority.
- CLI error redaction, absence of enforce/execute, no request effects/network/artifact dereference, and observation schema compliance.
- Existing runtime regression suite and independent review of real code and test evidence.

Tests demonstrate the implemented parser/observer behavior. They do not establish authenticated approvals, OS isolation, production protection or legal compliance.
Prior design tests for signed authority, replay consumption, execution stop/recovery and protected publishing remain future work; partial overlap is not reported as completion of those full tests.

## 7. Follow-up and recovery

Persist exact source hashes, actual test results, dependency versions and reviewer findings in the task record.
Before extending behavior, start a new bound task and reconcile the current sources with this submitted record.
Follow-up work needs immutable enrollment, trusted policy/identity/grants and isolated execution; observations must not be relabelled as authoritative decisions.
P1/P2/P3 promotion still requires the separately designed acceptance criteria, including trusted mandatory test oracles and a non-bypassable publication boundary.
