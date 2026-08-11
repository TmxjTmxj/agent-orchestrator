#!/usr/bin/env bash
# vps-security-scan.sh — Read-only security information gatherer for Linux VPS
# Usage: bash vps-security-scan.sh [OUTPUT_DIR]
# Safe: This script only reads system state and never modifies anything.
set -euo pipefail

OUT="${1:-/tmp/vps-scan-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"

separator() { printf '\n=== %s ===\n' "$1"; }

run() {
  local label="$1"; shift
  local outfile="$OUT/${label}.txt"
  printf '[*] Collecting: %s\n' "$label"
  { separator "$label"; "$@" 2>&1 || true; } > "$outfile"
}

header() { printf '%s\n' "Collected at $(date -u '+%Y-%m-%dT%H:%M:%SZ') on $(hostname 2>/dev/null || echo unknown)"; }

# ---- System Info ----
run system-info bash -c 'uname -a; echo; cat /etc/os-release 2>/dev/null || cat /etc/redhat-release 2>/dev/null; echo; uptime'

# ---- Network ----
run listening-ports bash -c 'ss -tlnp 2>/dev/null; echo; ss -ulnp 2>/dev/null'
run network-interfaces bash -c 'ip addr show 2>/dev/null; echo; ip route show 2>/dev/null'
run hosts-file bash -c 'cat /etc/hosts 2>/dev/null'
run dns-config bash -c 'cat /etc/resolv.conf 2>/dev/null'

# ---- Firewall ----
run iptables bash -c 'iptables -L -n -v 2>/dev/null; echo; iptables -t nat -L -n -v 2>/dev/null'
run nftables bash -c 'nft list ruleset 2>/dev/null'
run ufw bash -c 'ufw status verbose 2>/dev/null'
run firewalld bash -c 'firewall-cmd --list-all 2>/dev/null'

# ---- SSH ----
run sshd-config bash -c 'cat /etc/ssh/sshd_config 2>/dev/null; echo; cat /etc/ssh/sshd_config.d/*.conf 2>/dev/null'
run sshd-effective bash -c 'sshd -T 2>/dev/null'
run ssh-keys bash -c 'for f in /etc/ssh/ssh_host_*_key.pub; do [ -f "$f" ] && echo "$f: $(cat "$f")"; done 2>/dev/null'
run recent-logins bash -c 'last -n 30 2>/dev/null; echo; lastb -n 30 2>/dev/null'
run ssh-journal bash -c 'journalctl -u sshd --since "7 days" --no-pager 2>/dev/null | tail -100'

# ---- Users and Auth ----
run passwd-file bash -c 'cat /etc/passwd'
run uid-zero bash -c "awk -F: '(\$3 == 0) {print \$1}' /etc/passwd"
run shadow-perms bash -c 'ls -la /etc/shadow /etc/gshadow 2>/dev/null'
run sudoers bash -c 'cat /etc/sudoers 2>/dev/null; echo; cat /etc/sudoers.d/* 2>/dev/null'
run nopasswd-sudo bash -c "grep -r 'NOPASSWD' /etc/sudoers /etc/sudoers.d/ 2>/dev/null || echo none"
run login-users bash -c "awk -F: '(\$7 !~ /(\\/bin\\/false|\\/usr\\/sbin\\/nologin|\\/bin\\/nologin)/ && \$3 >= 1000) {print \$1, \$7}' /etc/passwd"

# ---- File System Security ----
run suid-binaries bash -c 'find / -perm -4000 -type f 2>/dev/null | head -50'
run sgid-binaries bash -c 'find / -perm -2000 -type f 2>/dev/null | head -50'
run world-writable-dirs bash -c 'find / -writable -type d 2>/dev/null | head -30'
run fstab bash -c 'cat /etc/fstab 2>/dev/null'
run tmp-perms bash -c 'ls -la /tmp /var/tmp /dev/shm 2>/dev/null'

# ---- Services ----
run running-services bash -c 'systemctl list-units --type=service --state=running 2>/dev/null | head -40'
run enabled-services bash -c 'systemctl list-unit-files --state=enabled 2>/dev/null | head -40'
run top-processes bash -c 'ps aux --sort=-%mem | head -20'

# ---- Cron ----
run cron-jobs bash -c 'cat /etc/crontab 2>/dev/null; echo; ls -la /etc/cron* 2>/dev/null; echo; for u in $(cut -d: -f1 /etc/passwd); do crontab -u "$u" -l 2>/dev/null && echo "user=$u"; done'

# ---- TLS/Certs ----
run letsencrypt-certs bash -c 'find /etc/letsencrypt/live/ -name "*.pem" 2>/dev/null; find /etc/letsencrypt/archive/ -name "*.pem" 2>/dev/null | head -20'
run ssl-certs bash -c 'find /etc/ssl/certs/ -name "*.pem" -newer /etc/ssl/certs/ca-certificates.crt 2>/dev/null | head -20; echo; ls -la /etc/ssl/private/ 2>/dev/null'

# ---- Containers ----
run docker-containers bash -c 'docker ps -a 2>/dev/null || echo "docker not available"'
run docker-images bash -c 'docker images 2>/dev/null || echo "docker not available"'
run docker-daemon bash -c 'cat /etc/docker/daemon.json 2>/dev/null || echo "no daemon.json"'
run podman-containers bash -c 'podman ps -a 2>/dev/null || echo "podman not available"'

# ---- Logging ----
run syslog-status bash -c 'systemctl status rsyslog 2>/dev/null; echo; systemctl status systemd-journald 2>/dev/null'
run journal-size bash -c 'journalctl --disk-usage 2>/dev/null'
run logrotate bash -c 'cat /etc/logrotate.conf 2>/dev/null; echo; cat /etc/logrotate.d/* 2>/dev/null | head -80'
run log-perms bash -c 'ls -la /var/log/ 2>/dev/null | head -30'

# ---- Audit ----
run auditd bash -c 'cat /etc/audit/auditd.conf 2>/dev/null; echo; auditctl -l 2>/dev/null'

# ---- Kernel/OS ----
run sysctl-security bash -c 'sysctl net.ipv4.ip_forward net.ipv4.conf.all.send_redirects net.ipv4.conf.all.accept_redirects net.ipv6.conf.all.accept_redirects kernel.randomize_va_space 2>/dev/null'
run pending-updates bash -c 'apt list --upgradable 2>/dev/null | head -30; yum check-update 2>/dev/null | head -30'

# ---- Application Configs ----
run nginx-config bash -c 'nginx -T 2>/dev/null | grep -E "server_name|listen|ssl_protocols|ssl_ciphers|proxy_pass" | head -50; echo; ls -la /etc/nginx/sites-enabled/ 2>/dev/null'
run sensitive-files bash -c 'find /var/www /opt /srv -name ".env" -o -name "*.env" -o -name "config.php" -o -name "database.yml" -o -name "config.json" 2>/dev/null | head -20'

# ---- Summary ----
SUMMARY="$OUT/summary.txt"
{
  header
  echo
  echo "=== Scan Summary ==="
  echo "Output directory: $OUT"
  echo
  echo "Files collected:"
  ls -1 "$OUT" | grep -v summary.txt | sed 's/^/  - /'
  echo
  echo "Quick findings:"
  echo "  - UID-0 accounts: $(awk -F: '($3 == 0) {print $1}' /etc/passwd | tr '\n' ' ')"
  echo "  - Login-capable users: $(awk -F: '($7 !~ /(\/bin\/false|\/usr\/sbin\/nologin)/ && $3 >= 1000) {print $1}' /etc/passwd | tr '\n' ' ')"
  echo "  - Listening TCP ports: $(ss -tlnp 2>/dev/null | tail -n +2 | wc -l)"
  echo "  - SUID binaries: $(find / -perm -4000 -type f 2>/dev/null | wc -l)"
  echo "  - World-writable dirs: $(find / -writable -type d 2>/dev/null | wc -l)"
  echo "  - Nopasswd sudo: $(grep -c 'NOPASSWD' /etc/sudoers /etc/sudoers.d/* 2>/dev/null || echo 0)"
  echo "  - Docker available: $(command -v docker >/dev/null 2>&1 && echo yes || echo no)"
  echo "  - Podman available: $(command -v podman >/dev/null 2>&1 && echo yes || echo no)"
  echo
  echo 'Review individual files for detailed findings.'
} > "$SUMMARY"

echo
echo "[+] Scan complete. Results in: $OUT"
echo "[+] Quick summary: cat $OUT/summary.txt"