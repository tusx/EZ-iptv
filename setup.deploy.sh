#!/bin/sh
set -eu

IMAGE_NAME="ez-iptv"
CONTAINER_NAME="ez-iptv"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

mkdir -p "$SCRIPT_DIR/instance"

podman build -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"
podman rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

exec podman run \
  --name "$CONTAINER_NAME" \
  -d \
  -p 8091:8091 \
  -v "$SCRIPT_DIR/instance:/app/instance:Z" \
  "$IMAGE_NAME"
