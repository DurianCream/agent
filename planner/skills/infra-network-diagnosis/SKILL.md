---
name: infra-network-diagnosis
description: Diagnose Linux or Windows connectivity, DNS, port, TLS, SSH/RDP, and network slowness symptoms by comparing the actual client-to-service path. Use for network incident investigation, not device provisioning, broad scanning, or a simple concept definition.
---

# Network path diagnosis

Find the first unsupported or failing boundary on the user's actual path, then choose a small check that distinguishes likely causes.

## Operating contract

Follow the infrastructure assistant's project instructions, including Korean communication and Markdown report delivery, official sources, confidentiality, and authorization. If unavailable, use Korean, no emojis, advisory mode, official references first, and `확인 불가` for material unknowns. This skill does not provide connectivity, packet-capture permissions, or new tools.

## Workflow

1. **State the user operation.** Record who is affected, an exact sanitized error, destination service/protocol/port, first occurrence and time zone, intermittent or consistent behavior, and a comparable working case if available. Distinguish a reported symptom from an independently observed failure.
2. **Map the path that matters.** Identify client, resolver, address family, interface/source address, route, VPN/proxy, NAT/firewall, load balancer, service, and dependency only where relevant. Mark unknown hops `확인 불가`. Do not invent topology. A probe from another machine, namespace, account, or route has a different scope.
3. **Choose the earliest unresolved boundary.** Read [boundary checks](references/boundary-checks.md). Use DNS, route/interface, transport/listener, TLS, application, and capacity as an investigation order, adapting it to the known error and protocol. Skip irrelevant layers; a non-TLS service does not need a TLS checklist.
4. **Design a comparison.** Use the same logical operation with a known working case or change one test variable: resolver, address family, source, route, or endpoint. Preserve destination hostname, authentication context, protocol, and request semantics where they affect comparability. Record changes that cannot be controlled. Testing an origin directly must be authorized and must not bypass access controls or silently change production routing.
5. **Prepare a bounded check.** Prefer existing observations and narrowly scoped permitted probes. Specify target, source host, shell, tool availability/version, timeout or duration, protocol, and expected traffic. Verify syntax and result meaning using applicable official documentation or installed help. A probe emits traffic even if it changes no configuration; do not describe it as having no impact.
6. **Record actual versus expected.** Classify actual evidence, user observations, hypotheses, and unverified applicability. Report refused, timed out, resolution failed, TLS failed, authenticated operation failed, and slow completion as distinct observations. Do not turn a client's error label into a proven firewall, DNS, or server diagnosis.
7. **Challenge the leading explanation.** State the evidence for it, a plausible alternative, and an observation that would contradict it. Use only as many hypotheses as the evidence supports. When a check disagrees, revise the explanation instead of stacking more changes.
8. **Deliver the next decision.** Give one to three prioritized checks or the supported diagnosis. Explain what each result would establish and what it would leave unresolved. If changing infrastructure is explicitly authorized, keep the parent's target verification, plan, impact, recovery, and outcome verification requirements.

## Guardrails specific to network diagnosis

- Scope a result to its source, destination, port, protocol, address family, and observation time. Ping success does not establish application health; ping failure does not by itself establish that the service is unreachable.
- Do not use a TCP port test as proof of UDP service health, TLS validation, or successful authentication.
- Do not query public resolvers for internal names. Do not upload packet captures, private addresses, certificate inventories, headers, cookies, or topology to external services without appropriate authorization.
- Do not begin with subnet sweeps, port-range scans, flood probes, or throughput benchmarks. A single relevant endpoint usually resolves the first decision.
- Packet capture or new tracing requires suitable authorization, a narrow filter, duration/size bounds, approved local storage, and a plan for sensitive payloads. If unavailable, complete the supported investigation using other evidence.
- Preserve TLS hostname and certificate validation when separating DNS from connectivity. Do not prescribe disabling certificate validation, host firewalls, VPNs, IPv6, or security policy as a default remedy.
- Do not conclude that a VPN/proxy works from a health check of a different path. Do not infer capacity from a fast small response. Bounded throughput testing is a separate action whose load and destination require consideration.
- For an active outage, an already authorized incident runbook may provide mitigation before cause is confirmed. Record mitigation separately from diagnosis.

## Deliverable

Use the parent's Korean Markdown report and actual `.md` delivery procedure. Include a compact path description, environment and test scope, evidence per relevant boundary, supported hypotheses, prioritized next checks, and precise `확인 불가` items. Cite inspected references near relevant claims. Explain DNS, TCP/UDP, TLS, and other unfamiliar terms only when needed.

If tools or target access are missing, provide the supported explanation and a user-run investigation procedure. Never report successful probes, packet evidence, or file delivery that did not occur.
