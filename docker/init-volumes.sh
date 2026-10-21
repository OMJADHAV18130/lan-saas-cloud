#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# OPTIONAL legacy helper - ownership is now handled automatically by the
# one-shot `volume-init` service in docker-compose.yml.
#
# You only need this script if you run the images WITHOUT compose (plain
# `docker run`), where nothing prepares volume ownership. In that case run it
# once before the first start:
#
#     bash docker/init-volumes.sh
#
# Volumes created by compose are prefixed with the project name (by default the
# directory name, e.g. "lan-saas-cloud_"), while this script manages the
# unprefixed names for standalone docker run usage.
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-lan-saas-cloud}"

echo "[init] ensuring volumes exist (project prefix: ${PROJECT})"
for name in hdfs-namenode-data hdfs-datanode-data hdfs-tmp controller-data; do
  docker volume inspect "${PROJECT}_${name}" >/dev/null 2>&1 || docker volume create "${PROJECT}_${name}" >/dev/null
done

echo "[init] preparing ownership in place (mount points only)"
docker run --rm \
  -v "${PROJECT}_hdfs-namenode-data:/nn" \
  -v "${PROJECT}_hdfs-datanode-data:/dn" \
  -v "${PROJECT}_hdfs-tmp:/tmp" \
  -v "${PROJECT}_controller-data:/data" \
  alpine:3.20 sh -c '
    mkdir -p /nn /dn /tmp /data
    chown 1000:1000 /nn /dn;  chmod 750  /nn /dn
    chown 1000:1000 /tmp;     chmod 1777 /tmp
    chown 10001:10001 /data;  chmod 750  /data
    echo "[init] ownership prepared"
  '

echo "[init] done"
