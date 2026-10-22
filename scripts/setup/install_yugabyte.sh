#!/usr/bin/env bash
set -euo pipefail

VERSION="2025.2.7.0"
BUILD="b107"
ARCH="linux-x86_64"

ARCHIVE="yugabyte-${VERSION}-${BUILD}-${ARCH}.tar.gz"
DOWNLOAD_URL="https://software.yugabyte.com/releases/${VERSION}/${ARCHIVE}"
CHECKSUM_URL="${DOWNLOAD_URL%.tar.gz}-tar.gz.sha"

INSTALL_DIR="/opt/yugabyte/yugabyte-${VERSION}"
CURRENT_LINK="/opt/yugabyte/current"
DATA_DIR="/var/lib/yugabyte/cluster"
SERVICE_USER="yugabyte"


die() {
    echo "Error: $*" >&2
    exit 2
}

(( EUID == 0 )) || die "Run this script with sudo."
[[ "$(uname -m)" == "x86_64" ]] || die "Only x86_64 is supported."

source /etc/os-release
if [[ "$ID" != "ubuntu" || "$VERSION_ID" != "24.04" ]]; then
    echo "Warning: Ubuntu 24.04 is recommended." >&2
fi

for command in curl tar sha256sum runuser useradd; do
    command -v "$command" >/dev/null || die "Missing dependency: $command"
done

if [[ -e "$INSTALL_DIR" || -e "$CURRENT_LINK" ||
      -L "$INSTALL_DIR" || -L "$CURRENT_LINK" ]]; then
    die "YugabyteDB is already installed. Refusing to overwrite."
fi

if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --create-home \
        --home-dir "/home/$SERVICE_USER" \
        --shell /usr/sbin/nologin \
        "$SERVICE_USER"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 /opt/yugabyte

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

ARCHIVE_PATH="$WORK_DIR/$ARCHIVE"

curl -fL --retry 3 -o "$ARCHIVE_PATH" "$DOWNLOAD_URL"

checksum="$(curl -fsSL "$CHECKSUM_URL")"
[[ "$checksum" =~ ^[a-fA-F0-9]{64}$ ]] || die "Invalid publisher checksum."

printf '%s  %s\n' "$checksum" "$ARCHIVE_PATH" | sha256sum -c -

tar -xzf "$ARCHIVE_PATH" -C /opt/yugabyte

[[ -x "$INSTALL_DIR/bin/yugabyted" ]] ||
    die "Unexpected archive layout: $INSTALL_DIR"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

runuser -u "$SERVICE_USER" -- bash -c \
    'cd "$1" && ./bin/post_install.sh' \
    _ "$INSTALL_DIR"

ln -s "$INSTALL_DIR" "$CURRENT_LINK"

echo "YugabyteDB $VERSION installed successfully."
echo "Next: configure the node and start its systemd service."
