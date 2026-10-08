# Network boundary checks

This table guides evidence selection. It is not a fixed causal mapping: similar symptoms can originate at different boundaries. Use official documentation for protocol behavior, tool syntax, and product-specific error meanings.

| Boundary | Evidence to select | Comparison or next decision | Avoid this conclusion |
| --- | --- | --- | --- |
| Name resolution | Queried name/type, actual resolver, returned addresses/aliases, DNS result and timestamp; distinguish an explicit DNS query from application name resolution | Does the affected client obtain an applicable address, and is the resolver/path the intended one? Compare A/AAAA only when relevant | Different answers alone prove failure; changing every client to a public resolver is a safe fix |
| Interface and route | Selected source/interface, destination address family, relevant route, VPN/proxy context | Is traffic taking the intended path? Compare the affected source with a comparable working source | Every probe uses the same path; a route-table entry proves end-to-end delivery |
| Transport and listener | Specific TCP connection or protocol-appropriate exchange; listener binding when target access is authorized | Where is there positive evidence of a successful or failed exchange? Does the service listen on the expected interface/port? | TCP success proves UDP, TLS, login, or application health; timeout proves a firewall dropped it |
| TLS, where used | Original hostname, actual endpoint, presented chain, validation result, relevant clock/trust-store context | Is the failure connection setup, protocol negotiation, trust validation, or hostname validation? | Connecting by bare IP is equivalent to the hostname operation; suppressing validation resolves trust correctly |
| Application and identity | The real operation and sanitized response; relevant service/authentication log; request/session context if available | Does the operation fail after transport/TLS succeeds? Is it application readiness, authentication, authorization, or a dependency? | Open SSH/RDP/HTTPS port proves the user can perform the intended operation |
| Capacity or intermittent failure | Suitable latency/error/transfer measurements with duration, size, direction, and comparable load; retransmission/loss evidence if available | Is delay in resolution, connection, TLS, server processing, or data transfer? Are observations from the incident window? | A small health check proves adequate throughput; one later success excludes intermittent failure |

## Tool selection

Tool names below are candidates, not assumptions that a tool is installed or a module is available. Do not install a tool automatically just to follow the table. Do not produce executable examples before checking applicability.

- Windows DNS: inspect `Resolve-DnsName` documentation for the actual Windows module version. Choose explicit resolver/type behavior deliberately; a DNS-only query may not match every application resolver path.
- Windows transport: `Test-NetConnection` provides documented ping, TCP, and routing diagnostics. Explicitly identify the target instead of relying on its default destination. It does not certify a UDP application exchange.
- Linux DNS: use the installed resolver tools when appropriate. ISC BIND's `dig` permits explicit server and query selection; a direct DNS query is different from testing application resolution through the OS.
- HTTP/TLS: inspect the installed implementation and version. The curl manual documents per-host/port address overrides with `--resolve`; assess proxy behavior and hostname preservation before using them. On Windows, verify command resolution so a shell alias is not mistaken for the curl executable.
- For route, listener, packet-capture, SSH, RDP, and vendor-device diagnostics, retrieve applicable OS/vendor documentation at use time. This skill does not certify options for unnamed implementations.

## Official reference starting points

Inspected during authoring on 2026-10-07; recheck during actual investigations. Latest/development documentation is not proof of compatibility with an older installation.

- [Microsoft Resolve-DnsName, Windows Server 2025 module view](https://learn.microsoft.com/en-us/powershell/module/dnsclient/resolve-dnsname?view=windowsserver2025-ps)
- [Microsoft Test-NetConnection, Windows Server 2025 module view](https://learn.microsoft.com/en-us/powershell/module/nettcpip/test-netconnection?view=windowsserver2025-ps)
- [ISC BIND manual pages](https://bind9.readthedocs.io/en/latest/manpages.html): includes the `dig` manual; the inspected `latest` view was development documentation.
- [curl manual](https://curl.se/docs/manpage.html): verify installed version, enabled features, and the relevant option's documented behavior.

## Workflow provenance

[daymade/claude-code-skills debugging-network-issues](https://github.com/daymade/claude-code-skills/blob/main/debugging-network-issues/SKILL.md) informed the high-level ideas of comparing network boundaries and looking for evidence that would contradict a diagnosis. This custom workflow is newly written for Linux/Windows infrastructure advice. It does not adopt mandatory additional reviewers, assume instrumentation permissions, or require raw credentials. The upstream repository uses the [MIT license](https://github.com/daymade/claude-code-skills/blob/main/LICENSE).
