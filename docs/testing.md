# Testing guide

## What is automated

| Test file | What it proves |
|---|---|
| `app/tests/test_auth.py` | registration rules, duplicate names, weak passwords, generic login errors, `/me`, forged/deleted-user tokens |
| `app/tests/test_files.py` | upload→list→download→delete, SHA-256 integrity, bytes stored outside SQLite, ownership isolation (404 not 403), search + sort, quota/limit/empty-file rejections, filename sanitisation |
| `app/tests/test_admin.py` | every admin route rejects anonymous (401) and ordinary users (403), roles cannot be self-assigned, real aggregate numbers, honest mock status, audit written without secrets |
| `app/tests/test_hdfs_protocol.py` | **WebHDFS protocol**: NameNode `CREATE` → 307 → DataNode write → 201, redirect-chain handling, streamed reads, `LISTSTATUS`/`GETFILESTATUS`/`DELETE`, 404 mapping, unreachable NameNode → `StorageUnavailable`, unsafe ids rejected |
| `app/tests/test_file_service.py` | filename sanitisation (traversal, Windows separators, control chars, truncation) and content-type hardening |
| `app/tests/test_hdfs_live.py` | **skipped by default** — real-cluster round trip, enabled with `RUN_HDFS_INTEGRATION=1` |

## Running the tests

```bash
cd cloud-controller
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pytest                     # all unit/API tests
python -m pytest -v                  # verbose
python -m pytest app/tests/test_hdfs_protocol.py -v      # protocol only
```

Tests use a temporary SQLite file and the **mock storage adapter**
(`HDFS_ADAPTER=mock`) so they never touch a real cluster. The mock adapter is
test infrastructure, not a replacement for HDFS — the WebHDFS adapter is
exercised separately against an in-process fake NameNode/DataNode
(`app/tests/fake_webhdfs.py`) that implements the redirect protocol.

### Running the tests inside the Docker stack

If you started the stack with `docker compose up -d`, you can run the suite in
the controller container. This exercises the real HDFS-backed configuration:

```bash
docker compose exec controller python -m pytest -q
# -> 66 passed, 2 skipped
```

Verify the deployment wiring itself (no Docker daemon required):

```bash
python docker/validate_compose.py
# -> ALL COMPOSE CONSISTENCY CHECKS PASSED
```

That check verifies the compose file, Dockerfiles and Hadoop XML agree — for
example that every service which talks to another by DNS name shares a network,
and that `dfs.webhdfs.enabled=true` is set.

### Running against a real cluster

```bash
export RUN_HDFS_INTEGRATION=1
export HDFS_BASE_URL=http://nn.lab.local:9870
export HDFS_SERVICE_USER=saascloud
export HDFS_ROOT=/saas-cloud
python -m pytest app/tests/test_hdfs_live.py -v -s
```

The test prints the **actual** replication factor the cluster reports; it does
not assume one.

## End-to-end smoke test (real HTTP)

With the controller running:

```powershell
# Windows PowerShell 5.1 or 7
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8000
```

```bash
# Linux/macOS equivalent (curl + jq)
BASE=http://127.0.0.1:8000
curl -s $BASE/api/health | jq .status
TOKEN=$(curl -s -X POST $BASE/api/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"smoke1","password":"SmokeTest1"}' | jq -r .access_token)
echo "hello hdfs" > /tmp/smoke.txt
FILE=$(curl -s -X POST $BASE/api/files/upload -H "Authorization: Bearer $TOKEN" \
  -F file=@/tmp/smoke.txt | jq -r .file.id)
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/files/$FILE/download"
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE/api/files/$FILE"
```

The script checks: health, register/login/me, wrong-password 401, upload,
listing, stats, download byte-for-byte with SHA-256 comparison, cross-user
download/delete denial, admin 401/403, delete, 413 on an oversized upload and
filename sanitisation.

## Manual end-to-end checklist (for the lab demonstration)

Work through this on the server, then repeat steps 9–12 from a **second PC**.

| # | Step | Expected |
|---|---|---|
| 1 | `start-dfs.sh`; `jps` | NameNode + DataNode running |
| 2 | `hdfs dfsadmin -report` | Live DataNode(s) listed |
| 3 | `curl http://<server>:8000/api/health` | `status: ok`, `storage.healthy: true` |
| 4 | Open `http://<server>:8000` from a client PC | Login page loads; sidebar shows green "HDFS connected" |
| 5 | Register `demo1` | Redirect to Dashboard, 0 files, quota shown |
| 6 | Upload a small text file | Progress bar completes, file appears, size/timestamp/SHA shown |
| 7 | Upload a second file (drag & drop) | Both files listed |
| 8 | Download the first file | Content identical (`sha256sum` / `certutil -hashfile SHA256`) |
| 9 | Search by part of a filename | Only matching rows |
| 10 | Sort by size descending, then by name ascending | Order changes correctly |
| 11 | Register `demo2` in a private window; request `demo1`'s file id with demo2's token | **404** not found |
| 12 | Try `GET /api/admin/stats` as demo2 | **403 forbidden** |
| 13 | As demo1, delete a file (confirm dialog) | Row disappears; `hdfs dfs -ls` shows the object gone |
| 14 | Stop Hadoop (`stop-dfs.sh`) and refresh the Dashboard | Sidebar badge turns red with a real error; uploads return 503 with a readable message |
| 15 | Start Hadoop again, retry the upload | Succeeds without restarting the controller |
| 16 | Promote demo2 to admin from `/admin`, log in as demo2 | Admin Dashboard accessible; audit trail shows `admin_role_change` |

## Verifying the bytes really are in HDFS

```bash
# 1. find the user id and object id in SQLite
sqlite3 cloud-controller/lan_saas.db \
  "select id, owner_id, original_name, size_bytes, hdfs_path from file_records;"

# 2. list the object as the service identity
hdfs dfs -ls    /saas-cloud/users/<user_id>/
hdfs dfs -ls -R /saas-cloud/users/

# 3. read it back through HDFS and compare with the original
hdfs dfs -cat   /saas-cloud/users/<user_id>/<file_id> > /tmp/from_hdfs.bin
sha256sum /tmp/from_hdfs.bin /path/to/original.bin      # must match

# 4. prove block placement and replication honestly
hdfs fsck /saas-cloud/users/<user_id>/<file_id> -files -blocks -locations

# 5. permissions actually applied by the controller
hdfs dfs -ls -ld /saas-cloud /saas-cloud/users/<user_id>
```

## Consistency check helper

```bash
cd cloud-controller
python -m app.tools.inspect_state
```

Prints row counts, audit event types, scans audit details for anything
secret-shaped, and cross-checks every metadata row against the storage backend
(missing objects, size mismatches).

## Frontend build check

```bash
cd frontend
npm ci
npm run build      # fails on syntax/import errors; emits frontend/dist
```
