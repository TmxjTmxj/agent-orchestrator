# VPS Security Investigation Checklist

Table of contents:
1. [Network and Exposure](#1-network-and-exposure)
2. [SSH Hardening](#2-ssh-hardening)
3. [Firewall and Filtering](#3-firewall-and-filtering)
4. [User Accounts and Auth](#4-user-accounts-and-auth)
5. [File System Security](#5-file-system-security)
6. [Service Hardening](#6-service-hardening)
7. [TLS and Certificates](#7-tls-and-certificates)
8. [Container Security](#8-container-security)
9. [Logging and Auditing](#9-logging-and-auditing)
10. [Kernel and OS](#10-kernel-and-os)
11. [Application Security](#11-application-security)

---

## 1. Network and Exposure

### Commands
```bash
ss -tlnp                    # List all TCP listening sockets with process
ss -ulnp                    # List all UDP listening sockets with process
ip addr show                # Show all network interfaces and IPs
ip route show               # Show routing table
cat /etc/hosts              # Check hosts file for suspicious entries
cat /etc/resolv.conf        # Check DNS configuration
iptables -L -n -v           # List iptables rules with counters
nft list ruleset 2>/dev/null  # List nftables rules
ufw status verbose 2>/dev/null # UFW status
```

### Checks
- [ ] Only expected services are listening on public interfaces
- [ ] No services bound to 0.0.0.0 that should be localhost only
- [ ] No unexpected high-numbered ports open
- [ ] IPv6 not leaking services if disabled
- [ ] No suspicious entries in /etc/hosts

---

## 2. SSH Hardening

### Commands
```bash
cat /etc/ssh/sshd_config                # Main SSH config
cat /etc/ssh/sshd_config.d/*.conf 2>/dev/null  # Drop-in configs
sshd -T                                 # Effective config (parsed)
cat /etc/ssh/ssh_host_*_key.pub         # Key types and fingerprints
awk '/^root:/ {print $1,$2}' /etc/shadow 2>/dev/null  # Root password status
last -n 20                               # Recent logins
lastb -n 20 2>/dev/null                  # Failed login attempts
journalctl -u sshd --since "7 days" --no-pager | tail -50  # Recent SSH logs
```

### Checks
- [ ] `PermitRootLogin` is `no` or `prohibit-password`
- [ ] `PasswordAuthentication` is `no`
- [ ] `PubkeyAuthentication` is `yes`
- [ ] `PermitEmptyPasswords` is `no`
- [ ] `X11Forwarding` is `no`
- [ ] `MaxAuthTries` is 4 or less
- [ ] `LoginGraceTime` is 30s or less
- [ ] `AllowUsers` or `AllowGroups` restricts access
- [ ] Host keys use modern algorithms (ed25519, rsa >= 3072)
- [ ] No weak ciphers or MACs enabled
- [ ] `Protocol 2` only (no Protocol 1)

---

## 3. Firewall and Filtering

### Commands
```bash
iptables -L -n -v                         # IPv4 rules with counters
iptables -t nat -L -n -v 2>/dev/null      # NAT rules
ip6tables -L -n -v 2>/dev/null            # IPv6 rules
nft list ruleset 2>/dev/null              # nftables
ufw status numbered 2>/dev/null           # UFW
firewall-cmd --list-all 2>/dev/null       # firewalld
cat /etc/iptables/*.rules 2>/dev/null     # Persisted rules
cat /etc/nftables.conf 2>/dev/null        # Persisted nftables
```

### Checks
- [ ] Default INPUT policy is DROP or REJECT
- [ ] Default FORWARD policy is DROP
- [ ] Only required ports are open
- [ ] Rate limiting on SSH (port 22)
- [ ] Output Filtering is considered (or documented why not)
- [ ] IPv6 rules match IPv4 intent
- [ ] Firewall rules are persisted (survive reboot)
- [ ] No overly permissive rules (e.g., ACCEPT any anywhere)

---

## 4. User Accounts and Auth

### Commands
```bash
cat /etc/passwd                            # All user accounts
awk -F: '($3 == 0) {print $1}' /etc/passwd  # UID 0 accounts (root equiv)
cat /etc/shadow 2>/dev/null | awk -F: '($2 == "" || $2 == "!") {print $1, "no-password"}'  # Passwordless accounts
passwd -S root 2>/dev/null                 # Root password status
awk -F: '($7 !~ /(\/bin\/false|\/usr\/sbin\/nologin|\/bin\/nologin)/ && $3 >= 1000) {print $1, $7}' /etc/passwd  # Login-capable users
last -n 50                                  # Recent logins
cat /etc/sudoers.d/* 2>/dev/null           # Sudoers drop-in configs
grep -r 'NOPASSWD' /etc/sudoers /etc/sudoers.d/ 2>/dev/null  # Passwordless sudo
cat /etc/security/limits.conf 2>/dev/null   # Resource limits
```

### Checks
- [ ] Only expected UID-0 accounts exist
- [ ] No passwordless login accounts (unless intentional)
- [ ] NOPASSWD sudo entries are justified and minimal
- [ ] No stale or orphaned accounts
- [ ] Password policy enforces complexity and aging
- [ ] PAM configuration is reasonable
- [ ] `umask` is 027 or more restrictive

---

## 5. File System Security

### Commands
```bash
find / -perm -4000 -type f 2>/dev/null                     # SUID binaries
find / -perm -2000 -type f 2>/dev/null                     # SGID binaries
find / -writable -type d 2>/dev/null | head -30            # World-writable dirs
ls -la /etc/shadow /etc/gshadow 2>/dev/null                # Shadow file perms
stat -c '%a %U %G %n' /etc/ssh/sshd_config 2>/dev/null    # SSH config perms
df -h                                                        # Disk usage
ls -la /tmp /var/tmp /dev/shm 2>/dev/null                  # Sticky bit on tmp dirs
cat /etc/fstab 2>/dev/null                                  # Mount options
```

### Checks
- [ ] No unexpected SUID binaries (compare against known baseline)
- [ ] Shadow files are mode 640 or more restrictive
- [ ] SSH config owned by root, not world-writable
- [ ] /tmp, /var/tmp, /dev/shm have sticky bit
- [ ] Critical mounts use nodev, nosuid, noexec where applicable
- [ ] No world-writable directories in PATH entries
- [ ] Logs are not world-readable

---

## 6. Service Hardening

### Commands
```bash
systemctl list-units --type=service --state=running          # Running services
systemctl list-unit-files --state=enabled                     # Enabled services
ls -la /etc/systemd/system/*.service 2>/dev/null               # Custom units
cat /etc/systemd/system/*.service 2>/dev/null                  # Custom unit configs
ps aux --sort=-%mem | head -20                                # Top processes by memory
ls -la /etc/cron* 2>/dev/null                                  # Cron jobs
cat /etc/crontab 2>/dev/null                                   # System crontab
for user in $(cut -d: -f1 /etc/passwd); do crontab -u "$user" -l 2>/dev/null; done  # User crontabs
```

### Checks
- [ ] Only necessary services are running
- [ ] No development/debug services in production (e.g., xdebug, dev servers)
- [ ] Services run as non-root where possible
- [ ] Cron jobs reviewed for suspicious entries
- [ ] No custom systemd units with security issues

---

## 7. TLS and Certificates

### Commands
```bash
openssl s_client -connect localhost:443 -servername <host> </dev/null 2>/dev/null | openssl x509 -noout -dates -subject  # Cert expiry
openssl s_client -connect localhost:443 -servername <host> </dev/null 2>/dev/null | openssl x509 -noout -text  # Full cert info
find /etc/letsencrypt/live/ -name '*.pem' 2>/dev/null         # Let's Encrypt certs
find /etc/ssl/certs/ -name '*.pem' 2>/dev/null | head -10     # System certs
nginx -T 2>/dev/null | grep -E 'ssl_protocols|ssl_ciphers'    # Nginx TLS config
cat /etc/haproxy/haproxy.cfg 2>/dev/null | grep -E 'ssl|bind' # HAProxy TLS
```

### Checks
- [ ] Certificates are not expired or near expiry (< 30 days)
- [ ] TLS 1.0 and 1.1 are disabled
- [ ] TLS 1.2 or 1.3 is the minimum
- [ ] Weak ciphers (RC4, DES, MD5) are disabled
- [ ] HSTS header is set (if web server)
- [ ] Certificate keys are >= 2048-bit RSA or ed25519
- [ ] Private keys are not world-readable

---

## 8. Container Security

### Commands
```bash
docker ps -a 2>/dev/null                    # All containers
docker images 2>/dev/null                    # Images
docker network ls 2>/dev/null                # Networks
docker inspect <container> 2>/dev/null       # Container details
podman ps -a 2>/dev/null                     # Podman containers
cat /etc/docker/daemon.json 2>/dev/null      # Docker daemon config
cat /etc/subuid /etc/subgid 2>/dev/null      # User namespace mappings
```

### Checks
- [ ] Containers don't run as root (user namespaces or --user)
- [ ] Read-only root filesystem where possible
- [ ] No privileged containers unless justified
- [ ] Container images are pinned to specific tags (not :latest)
- [ ] Docker socket not world-accessible
- [ ] Resource limits are set (memory, CPU)
- [ ] Health checks defined
- [ ] Secrets not in environment variables or image layers

---

## 9. Logging and Auditing

### Commands
```bash
systemctl status rsyslog 2>/dev/null          # Syslog status
systemctl status systemd-journald 2>/dev/null # Journald status
cat /etc/rsyslog.conf 2>/dev/null              # Rsyslog config
cat /etc/logrotate.conf /etc/logrotate.d/* 2>/dev/null | head -50  # Log rotation
ls -la /var/log/                                # Log files and perms
journalctl --disk-usage 2>/dev/null             # Journal size
cat /etc/audit/auditd.conf 2>/dev/null          # Auditd config
auditctl -l 2>/dev/null                         # Audit rules
```

### Checks
- [ ] Logging is enabled and working
- [ ] Log rotation is configured
- [ ] Logs are not world-readable
- [ ] Auditd is running (if required by compliance)
- [ ] Remote logging configured for critical systems
- [ ] Sufficient log retention

---

## 10. Kernel and OS

### Commands
```bash
uname -a                                      # Kernel version
cat /etc/os-release                            # OS details
lsb_release -a 2>/dev/null                      # LSB release
cat /proc/sys/kernel/randomize_va_space         # ASLR status
sysctl -a 2>/dev/null | grep -E 'randomize_va|exec_shield|net.ipv4.ip_forward|net.ipv4.conf.all.send_redirects|net.ipv4.conf.all.accept_redirects|net.ipv6.conf.all.accept_redirects'  # Security sysctls
apt list --upgradable 2>/dev/null | head -20    # Pending updates (Debian/Ubuntu)
yum check-update 2>/dev/null | head -20         # Pending updates (RHEL/CentOS)
```

### Checks
- [ ] Kernel is up-to-date (no known privilege escalation CVEs)
- [ ] ASLR is enabled (randomize_va_space = 2)
- [ ] IP forwarding disabled if not a router
- [ ] ICMP redirects disabled
- [ ] Security updates are applied promptly
- [ ] No end-of-life OS

---

## 11. Application Security

### Commands
```bash
find /var/www -name '.env' -o -name '*.env' -o -name 'config.php' -o -name 'database.yml' -o -name 'config.json' 2>/dev/null | head -20  # Sensitive config files
ls -la /var/www/ 2>/dev/null                                     # Web root
find / -name 'docker-compose*.yml' -o -name 'Dockerfile*' 2>/dev/null | head -10  # Container configs
cat /etc/nginx/sites-enabled/* 2>/dev/null | grep -E 'server_name|listen|ssl|proxy_pass'  # Reverse proxy config
```

### Checks
- [ ] No secrets in version-controlled files
- [ ] No `.env` files world-readable
- [ ] Application runs with minimal privileges
- [ ] Debug mode is off in production
- [ ] No default credentials
- [ ] Input validation is in place