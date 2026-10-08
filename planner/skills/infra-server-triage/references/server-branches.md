# Server investigation branches

Read only the rows relevant to the reported symptom. These are investigation prompts, not fixed diagnoses or runnable commands. Verify product behavior and syntax for the actual environment before turning them into operational instructions.

| Symptom | Linux evidence to consider | Windows evidence to consider | Interpretation question |
| --- | --- | --- | --- |
| Service does not start or repeatedly exits | Relevant service manager state; bounded service log; exit reason; configured identity; recent configuration changes | Service state and exit details; bounded System/Application or service-specific events; configured identity; recent changes | Is the failure in process startup, a dependency, permissions, configuration, or the user operation after startup? |
| Service runs but users cannot use it | Exact user operation, local service response, listener scope, dependency error, application log | Same user operation, local response, listener scope, service/application events | Does failure begin inside the host or across a network boundary? A running state alone does not answer this. |
| CPU pressure or slow responses | Workload volume; time series for CPU and runnable work; process-level attribution; relevant VM/container limits | Workload volume; sampled CPU and queue metrics with defined units; process attribution; VM limits | Do resource pressure and degraded operations overlap, and is demand or capacity different from the baseline? |
| Suspected memory pressure | Time series; available-memory definition; swap/reclaim evidence where applicable; process and container limits; relevant termination events | Available/committed memory measures; applicable limits; paging trend; process memory trend; relevant events | Is there evidence of pressure, a growing trend, a configured limit, or termination? Which remains a hypothesis? |
| Disk full or storage slowness | Affected filesystem, space and inode accounting where applicable; storage latency/errors; quota and mount context | Affected volume, space/quota context; storage latency/errors; volume/service events | Is the issue capacity, a quota, permissions, storage I/O, or a dependency? Do not recommend deletion from space usage alone. |
| Unexpected reboot or crash | Boot/session boundaries; prior-boot evidence if retained; OS/hypervisor/hardware events; maintenance history | Boot/session boundaries; relevant event provider and event payload; crash evidence if available; maintenance/hypervisor history | Does an event identify a causal mechanism, or only record that shutdown was abnormal? Check the event's provider and official meaning. |
| Only remote access fails | User operation and source context; service/listener evidence; relevant access logs | User operation and source context; service/listener evidence; relevant access/security events if authorized | Distinguish transport reachability from authentication, authorization, session limits, and application readiness. Use the network workflow when relevant. |

## Bound collection

- Correlate service logs, metrics, and changes using timestamps with time zones. If clocks or timestamp semantics are uncertain, record that limitation.
- Use a short relevant time range and service/provider filters. Widen only when the first range is insufficient.
- In systemd environments, inspect applicable `journalctl` documentation for service, boot, and time filters. Do not assume previous-boot logs were retained.
- On Windows, prefer documented event filters rather than reading every event and filtering afterward. Record the selected provider, event ID, time window, and query outcome. Do not silently enable a log or change retention.
- Avoid unbounded filesystem walks, process dumps, trace sessions, or benchmarks during a routine first pass. Their load and data exposure need separate consideration.
- Match observations to the actual target. A command run on the engineer's workstation is not evidence of a remote server's resource state.

## Official reference starting points

These links were inspected when this skill was authored on 2026-10-07. They are lookup starting points, not verification of the user's installation. Recheck the relevant content during each investigation and select documentation for the installed version.

- [systemd journalctl manual source](https://github.com/systemd/systemd/blob/main/man/journalctl.xml): maintainer-controlled manual source, including time and boot filtering. `main` is moving development content; prefer an installed manual or matching release for executable details.
- [Microsoft Get-WinEvent, Windows PowerShell 5.1](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.diagnostics/get-winevent?view=powershell-5.1): event retrieval and supported filtering parameters for that PowerShell version.
- [Microsoft Get-WinEvent, PowerShell 7.5](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.diagnostics/get-winevent?view=powershell-7.5): compare with the actual PowerShell version before using version-dependent examples.

For metrics, storage, permissions, and product-specific events, retrieve the relevant OS/vendor or application documentation at investigation time. This reference does not certify every metric name or event ID.

## Workflow provenance

[obra/superpowers systematic-debugging](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) informed the high-level ideas of observing failures before selecting a remedy and testing explanations individually. The custom skill is newly written for infrastructure advisory work. It does not import the upstream requirements to reproduce production failures, create a failing code test, or postpone every mitigation until root cause is known. The upstream repository uses the [MIT license](https://github.com/obra/superpowers/blob/main/LICENSE).
