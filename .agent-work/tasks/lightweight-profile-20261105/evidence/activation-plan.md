# Publication and activation readback plan

Task: lightweight-profile-20261105. Scope: repo multi / project multi / service agent-framework / environment development / issue lightweight-submission-profile.

## Target and authority

Activate only in the authoritative checkout used to produce and publish this candidate: `work/p2-reviewed-release-20261103` relative to the preserved outer workspace. The parent performs the existing authorized non-force finish to the configured remote and branch. This plan does not authorize another destination or a new task. No primary/outer Git reconciliation, resets, policy copies, VM operations or service actions are included.

The outer workspace retains its older HEAD and unrelated control changes. It is not an activated light workspace. Copying runtime/configuration there would not make its uncommitted policy eligible; leave it unchanged. A guide/task-record mirror for discoverability is a separate parent action and must not be described as activation.

## Preconditions

- Independent final review binds the exact candidate and final result/evidence.
- Existing implementation enrollment stays schema 0.1.0 with original full p1-regression policy; mandatory proof passes on the frozen digest.
- Parent validate/submit/finish completes and independently reports the actual verified configured remote commit.
- The committed `.agent-work/submission-profiles.json` and useful prose seed are present. Their new-task capability is never retroactively attached to this implementation task or earlier tasks.

## Read-only post-publication probe

Run from the authoritative published checkout, passing the actual finish commit as EXPECTED_COMMIT in a controlled inline Python invocation. No init, bind, track, checkpoint, selection or automatic record creation is used. Import only the already-reviewed local runtime. The probe may write a bounded evidence receipt under this task's ignored runs/evidence directory; it does not mutate product files, task scope, enrollment, shared indexes or Git.

```python
from pathlib import Path
import hashlib, json, sys
sys.path.insert(0, 'runtime')
import control_gate as g
import submission_profile as p
root = Path.cwd()
expected_commit = EXPECTED_COMMIT
assert g._git(root, 'rev-parse', 'HEAD') == expected_commit
capability = p.capture(root, expected_commit)
assert capability is not None
assert capability['config']['profile'] == p.PROFILE
assert capability['config']['paths'] == ['docs/prose/project-overview.txt']
assert g._blob(root, p.CONFIG) == capability['baseline_blob']
assert json.loads((root / p.CONFIG).read_text(encoding='utf-8-sig')) == capability['config']
p.prose((root / 'docs/prose/project-overview.txt').read_bytes())
controls = root / 'runs/lightweight-profile-20261105/controls.json'
assert json.loads(controls.read_text(encoding='utf-8'))['schema_version'] == '0.1.0'
assert hashlib.sha256(controls.read_bytes()).hexdigest() == 'dfeaadca9e67cd7f1135d8fa271b0909cdb0c08f24affe411c0bea5ef8a9c755'
print(json.dumps({'commit': expected_commit, 'profile': p.PROFILE,
                  'baseline_profile_sha256': capability['baseline_sha256'],
                  'allowlisted_paths': capability['config']['paths'],
                  'read_only_capture': True, 'implementation_enrollment_unchanged': True,
                  'actual_new_task_created': False}))
```

An observed matching committed capability plus prior real isolated CLI lifecycle proof establishes availability for future tasks in this checkout. It does not claim an actual new task was enrolled. Independent candidate-specific semantic approval, unchanged protected sources, actual fixed checks and final review remain required for every future light change.

## Failure and recovery

If finish fails, use its existing pending-commit retry behavior; do not duplicate commits or force-push. If readback disagrees with reviewed sources, stop the activation claim and return the exact discrepancy to the same owner. Do not repair enrollment/seals or overwrite the old outer workspace. Any required source repair creates a reviewed follow-up change under the applicable full gates.
