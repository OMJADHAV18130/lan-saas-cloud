#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Start a single-node (pseudo-distributed) HDFS cluster in one container.
#
#   * formats the NameNode ONCE (the VERSION file on the volume is the marker)
#   * starts the DataNode and the NameNode
#   * creates the least-privilege service identity directories under
#     /saas-cloud and applies 0750 permissions
#   * waits for the WebHDFS endpoint to answer before returning
#
# This is a DEVELOPMENT cluster: ONE DataNode => ONE physical replica.
# ---------------------------------------------------------------------------
set -euo pipefail

NN_DIR=/hadoop/dfs/name
DN_DIR=/hadoop/dfs/data
ROOT_DIR=/saas-cloud
SERVICE_USER="${HDFS_SERVICE_USER:-saascloud}"

echo "[hdfs] preparing directories"
# /hadoop/tmp is on the tmp volume; dfs name/data dirs are on their own volumes.
mkdir -p "$NN_DIR" "$DN_DIR" /hadoop/tmp

# --- format the NameNode only if it has never been formatted ----------------
if [ ! -f "$NN_DIR/current/VERSION" ]; then
  echo "[hdfs] formatting NameNode (first run only)"
  hdfs namenode -format -force -nonInteractive >/dev/null
else
  echo "[hdfs] existing NameNode metadata found - skipping format"
fi

# --- start the DataNode first so it can register immediately ----------------
echo "[hdfs] starting DataNode"
hdfs --daemon start datanode

echo "[hdfs] starting NameNode"
hdfs --daemon start namenode

# --- wait for the NameNode HTTP (WebHDFS) endpoint --------------------------
echo "[hdfs] waiting for WebHDFS on :9870"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:9870/webhdfs/v1/?op=LISTSTATUS&user.name=hadoop" \
       >/dev/null 2>&1; then
    echo "[hdfs] NameNode is answering WebHDFS"
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    echo "[hdfs] ERROR: NameNode did not become ready in time" >&2
    exit 1
  fi
done

# --- leave safe mode and create the application root ------------------------
hdfs dfsadmin -safemode wait || true

echo "[hdfs] creating ${ROOT_DIR} for service identity '${SERVICE_USER}'"
hdfs dfs -mkdir -p "$ROOT_DIR"
# The service user does not exist as a Linux account in this image, so the
# owner is set by name through the CLI; HDFS stores owners as strings.
hdfs dfs -chown "${SERVICE_USER}:supergroup" "$ROOT_DIR" || true
hdfs dfs -chmod 0750 "$ROOT_DIR"
hdfs dfs -ls -ld "$ROOT_DIR" || true

echo "[hdfs] ready. DataNodes:"
hdfs dfsadmin -report 2>/dev/null | grep -E "Live datanode|Name:" || true

# --- keep the container alive and forward signals ---------------------------
trap 'echo "[hdfs] stopping"; hdfs --daemon stop namenode || true; hdfs --daemon stop datanode || true; exit 0' TERM INT
while true; do sleep 5; done
