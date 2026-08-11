---
name: security-investigation
description: Investigate the security posture of a VPS, remote server, or infrastructure. Orchestrates specialized subagents for comprehensive assessment. Use when the user asks to audit, check, harden, scan, or investigate server security, vulnerabilities, compliance, exposed services, SSH hardening, firewall rules, or infrastructure posture. Triggers on VPS, server, security, audit, hardening, pentest, vulnerability, compliance, CIS benchmark, infrastructure security.
---

# Security Investigation Skill

Orchestrate comprehensive security investigations of VPS/remote servers using specialized subagents.

## When to Use

Use this skill when the user requests any of these:
- VPS or server security audit
- Infrastructure hardening review
- Vulnerability assessment
- Compliance check (CIS, PCI-DSS, etc.)
- Firewall and network exposure review
- SSH hardening verification
- Container security review
- Exposed services audit

## Investigation Workflow

### Step 1: Clarify Scope

Before delegating, confirm with the user:

```
1. Target host(s) — IP or hostname
2. SSH access — user, key path, port
3. Scope — full | network | auth | services | containers | compliance
4. Depth — quick scan | deep investigation
5. Production? — affects caution level and approach
```

### Step 2: Local Workspace Pre-Check

Before delegating to subagents, check the local workspace for infrastructure-as-code:

- Read `docker-compose*.yml`, `Dockerfile*`, `terraform/**/*.tf`, `ansible/**/*.yml`
- Read `.env*`, `nginx.conf`, `Caddyfile`, `haproxy.cfg` — but **never print secrets**
- Read `systemd` unit files if present in the repo
- Note all misconfigurations for the final report

### Step 3: Delegate to Subagents

#### Target: Remote server — use `host-security-investigator`

Provide a tight prompt via the **Task** tool:

```
Investigate the security posture of <host>.
SSH: ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i <key> -p <port> <user>@<host>
Scope: <scope>
Depth: <depth>

Focus on:
1. Network exposure (listening ports, unnecessary services)
2. SSH hardening (root login, password auth, key types)
3. Firewall (iptables/nftables/ufw rules, default policies)
4. User accounts (sudo users, empty passwords, UID 0 accounts)
5. File permissions (world-writable sensitive dirs, SUID binaries)
6. Service versions and known CVEs
7. TLS configuration (certs, protocols, cipher suites)
8. Container security (if Docker/Podman present)
9. Logging and audit (journald, rsyslog, log rotation)
10. Kernel and OS patch level

For VPS checklist details, read references/vps-checklist.md in this skill.
Cite every command you ran. Classify findings: CRITICAL / HIGH / MEDIUM / LOW / INFO.
```

#### Target: Application code — use `security-reviewer`

If the workspace contains application code:

```
Review code in <paths> for security risks:
- Auth/authz bypasses
- Secret leakage (env vars, logs, error messages)
- SQL/NoSQL/Command/Template injection
- SSRF, path traversal, unsafe deserialization
- Missing input validation
- Data exposure (verbose errors, debug endpoints)
- Tenant isolation gaps

Return: critical vulnerabilities, medium risks, hardening recommendations, safe-to-merge verdict.
```

#### Target: Dependency vulnerabilities — use `api-docs-researcher`

If CVE research is needed:

```
Research known CVEs for these software versions found on the target:
<list of software with versions>

For each: severity, CVSS score, exploitation status, and remediation guidance.
Use official CVE databases, vendor advisories, and NVD.
```

### Step 4: Compile Report

Combine all subagent findings into this structure:

```markdown
# Security Investigation Report

**Target:** <host(s)>
**Date:** <date>
**Scope:** <scope>
**Depth:** <depth>

---

## Executive Summary

<2-3 sentences on overall posture and top-risk items>

## Findings

| # | Finding | Severity | Category | Location | Recommendation |
|---|---------|----------|----------|----------|----------------|
| C1 | ... | CRITICAL | ... | ... | ... |

## Hardening Roadmap

### Immediate (0-24h)
1. ...

### Short-term (1-7d)
1. ...

### Long-term (1-30d)
1. ...

## Residual Risks and Unknowns
- Areas not tested and why
- Assumptions made
- Items requiring manual verification
```

### Step 5: Verify Fixes

After the user addresses findings, offer to re-run targeted checks to verify remediation.

## Subagent Orchestration Rules

- **Always** delegate to `host-security-investigator` for remote infrastructure checks
- **Always** delegate to `security-reviewer` for application code review
- **Optionally** delegate to `api-docs-researcher` for CVE/advisory research
- **Never** run destructive commands on the target — subagents are configured read-only
- **Never** print secrets, keys, or tokens in the report — mark them as `[REDACTED]`

## Remote Access Best Practices

- Use `ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new` for non-interactive SSH
- Prefer read-only commands: `cat /etc/...`, `ss -tlnp`, `iptables -L -n`, etc.
- If `sudo` is needed, note the command and ask the user to run it manually
- Quote paths with spaces: `"/path/with spaces"`
- Check if `ssh` connectivity works before running a full scan

## Severity Classification

| Level | Criteria |
|-------|----------|
| CRITICAL | Actively exploitable, data loss or full compromise possible |
| HIGH | Exploitable with moderate effort, significant impact |
| MEDIUM | Requires specific conditions, limited impact |
| LOW | Defense-in-depth improvement, low exploitation probability |
| INFO | Best practices, observations, no direct risk |