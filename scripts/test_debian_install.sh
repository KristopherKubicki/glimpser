#!/usr/bin/env bash
# Run only on a disposable CI runner; never install the package on the host.
set -euo pipefail
package=$(realpath "${1:?Debian package path required}")
container="glimpser-package-test-${GITHUB_RUN_ID:-$$}"
image="glimpser-package-test:${GITHUB_RUN_ID:-local}"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker build -t "$image" -f tests/packaging/Dockerfile tests/packaging
docker run -d --name "$container" --privileged --cgroupns=private \
    --tmpfs /run --tmpfs /run/lock "$image"
docker cp "$package" "$container:/package.deb"
docker exec "$container" bash -eu -c '
for attempt in $(seq 1 30); do
    [ -d /run/systemd/system ] && break
    sleep 1
done
test -d /run/systemd/system
dpkg -i /package.deb
for attempt in $(seq 1 90); do
    if systemctl is-active --quiet glimpser &&
        python3 -c "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8082/login\", timeout=2)" 2>/dev/null; then
        break
    fi
    sleep 2
done
systemctl is-active --quiet glimpser
python3 -c "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8082/login\", timeout=5)"
test "$(systemctl show glimpser -p User --value)" = glimpser
test "$(stat -c %U /opt/glimpser/main.py)" = root
test "$(stat -c %U /opt/glimpser/data)" = glimpser
printf preserve-me > /opt/glimpser/data/install-sentinel
chmod 600 /opt/glimpser/data/install-sentinel
systemctl disable glimpser
dpkg -i /package.deb
test "$(systemctl is-enabled glimpser || true)" = disabled
test "$(cat /opt/glimpser/data/install-sentinel)" = preserve-me
test "$(stat -c %a /opt/glimpser/data/install-sentinel)" = 600
dpkg --remove glimpser
test "$(cat /opt/glimpser/data/install-sentinel)" = preserve-me
! systemctl is-active --quiet glimpser
'
