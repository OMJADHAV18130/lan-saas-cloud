# LAN-Based SaaS Cloud Storage System Using an HDFS Cloud Controller

A private, multi-user, browser-based cloud storage service for a college
laboratory LAN. Our own **Cloud Controller** (FastAPI) handles identity,
ownership, quotas and auditing; **Apache Hadoop HDFS** stores the file contents
through the **WebHDFS REST API**; **SQLite** stores only metadata.

> **Status of the code in this repository.** The backend test suite, the
> frontend production build, an end-to-end HTTP smoke test and — via Docker — a
> **live HDFS round trip against a genuine Apache Hadoop cluster** were actually
> executed while building this project. The exact commands and observed output
> are in [Verified results](#verified-results).
>
> Two things are stated plainly so the report and viva stay accurate:
>
> 1. The Docker cluster is **single-DataNode** (`dfs.replication=1`): every block
>    exists **once**. It is a pseudo-distributed lab configuration, and it is
>    **not** fault-tolerant. Real replication was not tested.
> 2. When the machine used to write this code turned out to have **no Java
>    suitable for Hadoop** (Java 25; Hadoop 3.4 needs Java 8/11), the cluster was
>    run in a container that ships its own JDK 11. The WebHDFS adapter is
>    *additionally* exercised against an in-process fake NameNode/DataNode that
>    reproduces the 307 redirect protocol, so the API contract is verified
>    independently of the storage backend. The mock adapter remains a clearly
>    labelled development fallback, **disabled by default**.

---

## Table of contents

1. [Architecture](#architecture)
2. [Directory structure](#directory-structure)
3. [Prerequisites](#prerequisites)
4. [Quick start (Docker, recommended)](#quick-start-docker-recommended)
5. [Quick start (Linux/Ubuntu)](#quick-start-linuxubuntu)
6. [Quick start (Windows, development only)](#quick-start-windows-development-only)
7. [Running against real HDFS](#running-against-real-hdfs)
8. [API documentation](#api-documentation)
9. [HDFS integration notes](#hdfs-integration-notes)
10. [Security model and honest limitations](#security-model-and-honest-limitations)
11. [Testing](#testing)
12. [Verifying files with `hdfs dfs`](#verifying-files-with-hdfs-dfs)
13. [LAN deployment](#lan-deployment)
14. [Troubleshooting](#troubleshooting)
15. [Demo script](#demo-script)
16. [Verified results](#verified-results)
17. [Documentation index](#documentation-index)

---

## Architecture

```
+-------------------+        +-------------------------------------------+
|  Client PC        |        |  Ubuntu lab server                        |
|  (browser)        |  HTTP  |                                           |
|                   | -----> |  React SPA (Vite build, served by FastAPI |
|  React frontend   |        |  or Vite dev server on :5173)             |
+-------------------+        |                                           |
                             |      | REST + JWT  (:8000)               |
                             |      v                                   |
                             |  FastAPI Cloud Controller                |
                             |   - auth (Argon2id + JWT)                |
                             |   - ownership / quota / validation       |
                             |   - audit trail                          |
                             |      |                    |              |
                             |      | SQLAlchemy         | WebHDFS       |
                             |      v                    v              |
                             |  SQLite (metadata)   NameNode :9870      |
                             |                       |                  |
                             |                       | 307 redirect     |
                             |                       v                  |
                             |                    DataNode :9864        |
                             |                    (block storage)       |
                             +-------------------------------------------+
```

**Trust boundaries**

| Layer | May see | Must never see |
|---|---|---|
| Browser | file ids, original filenames, sizes, timestamps, SHA-256, own stats | HDFS paths, WebHDFS credentials, other users' data, admin internals |
| Cloud Controller | everything except passwords (only hashes) | — |
| HDFS | service identity `saascloud`, object paths | end-user credentials, tokens |

**Request lifecycle — upload**

```
POST /api/files/upload
  -> JWT verified, user loaded from SQLite            (auth)
  -> multipart streamed to spooled temp file, size cap enforced while reading
  -> SHA-256 computed, file count + quota checked      (file_service)
  -> filename sanitised (metadata only), object path = /saas-cloud/users/<uid>/<fileuuid>
  -> WebHDFS PUT op=CREATE  -> NameNode :9870   => 307 Location: http://<dn>:9864/...
  -> PUT bytes              -> DataNode         => 201 Created
  -> file_records row committed                        (SQLite)
  -> audit event 'file_upload'                         (SQLite)
  -> 201 {file: {...}}
  (any failure after the HDFS write rolls the object back)
```

---

## Directory structure

```
lan-saas-cloud/
├── README.md
├── docker-compose.yml                 # namenode + controller (+ volume-init)
├── .env.example                       # compose env; copy to .env
├── .dockerignore
├── docker/
│   ├── init-volumes.sh                # ownership helper for plain `docker run`
│   └── validate_compose.py            # static consistency checks (no daemon needed)
├── frontend/                          # React 18 + Vite + Tailwind + Router + Axios
│   ├── index.html  package.json  vite.config.js
│   ├── tailwind.config.js  postcss.config.js  .env.example
│   └── src/
│       ├── main.jsx  App.jsx  index.css
│       ├── api/client.js              # axios instance, error normalisation
│       ├── auth/AuthContext.jsx       # token + user state, login/register/logout
│       ├── components/                # Layout, StorageStatusBadge, ui.jsx
│       ├── pages/                     # Login, Register, Dashboard, MyFiles,
│       │                              # UploadFile, Profile, Admin
│       └── utils/format.js
├── cloud-controller/                  # Python 3.11+ FastAPI service
│   ├── Dockerfile                     # multi-stage: builds SPA, then serves it
│   ├── requirements.txt  pytest.ini  .env.example
│   ├── base-image/                    # Apache Hadoop 3.4.1 (NameNode + DataNode)
│   │   ├── Dockerfile                 # derives the official image, JDK 11 included
│   │   ├── start-hdfs.sh              # formats (once) and starts the cluster
│   │   ├── core-site.xml   hdfs-site.xml
│   └── app/
│       ├── main.py                    # app factory, middleware, SPA hosting
│       ├── bootstrap_admin.py         # create the FIRST admin (no default password)
│       ├── core/       config.py security.py errors.py rate_limit.py
│       ├── db/         base.py session.py init_db.py
│       ├── models/     user.py file.py audit.py
│       ├── schemas/    auth.py file.py admin.py common.py
│       ├── auth/       dependencies.py router.py
│       ├── api/        files.py dashboard.py admin.py health.py
│       ├── services/   hdfs_service.py file_service.py audit_service.py
│       ├── tools/      inspect_state.py    # SQLite <-> HDFS consistency report
│       └── tests/      conftest.py fake_webhdfs.py test_auth.py test_files.py
│                       test_admin.py test_hdfs_protocol.py test_file_service.py
│                       test_hdfs_live.py   # skipped unless RUN_HDFS_INTEGRATION=1
├── hadoop-config/
│   ├── README.md                      # why each property matters, replication honesty
│   ├── core-site.xml.example
│   └── hdfs-site.xml.example
├── scripts/
│   └── smoke_test.ps1                 # end-to-end HTTP test (24 checks)
└── docs/
    ├── api.md                         # full API reference with curl examples
    ├── docker-deployment.md           # containerised stack, LAN, volumes, upgrades
    ├── lan-deployment.md              # Ubuntu single/multi-machine LAN guide
    ├── testing.md                     # automated + manual test plan
    ├── troubleshooting.md
    ├── project-report-outline.md
    └── viva-qa.md
```

### Deviations from the requested tree (and why)

| Change | Reason |
|---|---|
| `app/db/init_db.py` added | Keeps schema creation out of `main.py` so tests can rebuild the schema. |
| `app/bootstrap_admin.py` added | Requirement 9 asks for a *safe* way to create the first admin. Two paths: interactive CLI (recommended) and an env-driven bootstrap that only runs on an empty users table. |
| `app/services/audit_service.py` added | Requirement 11: auditing is cross-cutting; a separate module enforces the "no secrets in details" rule in one place. |
| `app/tools/inspect_state.py` added | Makes the documented SQLite/HDFS consistency limitation *checkable* rather than theoretical. |
| `app/api/health.py` contains both `/api/health` and `/api/storage/status` | The UI badge needs a storage indicator; exposing the NameNode URL and internal root to unauthenticated callers is unnecessary, so the public endpoint returns a reduced payload and admin gets the full one at `/api/admin/hdfs-status`. |
| `docs/` split into 7 files | A single README carrying API reference, deployment, tests, report outline and viva answers becomes unusable in a lab demo. |
| `scripts/smoke_test.ps1` added | Gives a real-HTTP end-to-end check that can run against either the direct server or the Docker stack. |
| `docker-compose.yml`, `cloud-controller/Dockerfile`, `cloud-controller/base-image/` added | The host machine had Java 25, which no Hadoop release supports (3.3/3.4 need Java 8/11). Running the cluster in a container that ships JDK 11 removed a host dependency *and* made the whole stack start with one command. |
| `docker/validate_compose.py` added | The compose stack failed twice for structural reasons (a service on the wrong network; HDFS dirs on a root-owned filesystem). A static checker turns both into failures you see *before* starting Docker. |
| `CONTROLLER_PORT` defaults to 8080, not 8000 | Port 8000 is very often already taken on a development machine; 8080 keeps `docker compose up` working out of the box. |
| No `/api/profile` route | Profile data *is* the authenticated user resource; it is served by `GET /api/auth/me`. Adding an alias would expose one resource at two URLs. |
| `GET /api/files` uses `q`, `sort_by`, `order`, `limit`, `offset` | Explicit, validated parameters with `Literal` patterns instead of free-form strings. |

---

## Prerequisites

| Component | Version | Notes |
|---|---|---|
| Docker + Compose v2 | 24+ | **Recommended path** — runs HDFS *and* the controller in containers |
| Python | 3.11+ (3.12 tested) | Cloud Controller (manual install) |
| Node.js / npm | 20+ / 10+ | Frontend build (not needed for Docker — the image builds it) |
| Java | **8 or 11** | Required by Hadoop. *Not* 17/21/25. Not needed for Docker. |
| Apache Hadoop | 3.3.x / 3.4.x | HDFS + WebHDFS (bundled in the Docker image) |
| OS | Ubuntu 22.04/24.04 (server), Windows/macOS (development) | |

### Windows differences and limitations

* Hadoop 3.x does **not** run properly as a Windows server: the shipped
  `winutils.exe`/`hadoop.dll` shims are unmaintained, `start-dfs.sh` is a shell
  script, and the recommended Java (8/11) is not what Windows ships. Use
  **WSL2 Ubuntu**, a **Docker/Linux VM**, or a Linux server for HDFS.
* The Cloud Controller itself runs fine on Windows (it is pure HTTP via
  `httpx`); only the cluster needs Linux.
* Paths differ: `\` vs `/`, and `python -m venv .venv` then
  `.venv\Scripts\activate` instead of `source .venv/bin/activate`.
* The one-liner used on the Windows host for this project (development only):
  ```powershell
  $env:HDFS_ADAPTER="mock"; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
* Firewall prompts appear the first time Uvicorn binds a port; allow private
  networks only.

---

## Quick start (Docker, recommended)

The container route is the least painful one: **no Java version dependency** (the
image brings JDK 11, so a host with Java 25 is fine), HDFS is formatted and
wired automatically, and the API + UI are served from a single port.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> JWT_SECRET in .env

docker compose up -d --build
docker compose exec controller python -m app.bootstrap_admin   # create the first admin
```

Open **<http://localhost:8080>**. `/api/health` should report
`"adapter": "webhdfs"` and `"healthy": true` — real HDFS, not the mock.

Verify the bytes are genuinely in HDFS (not on the app's local disk):

```bash
docker compose exec namenode hdfs dfs -ls -R /saas-cloud
docker compose exec namenode hdfs dfsadmin -report      # expect 1 live DataNode
```

**Full guide: [docs/docker-deployment.md](docs/docker-deployment.md)** — LAN
access, firewall rules, volumes/backup, upgrades and troubleshooting.

> This remains a **single-DataNode** cluster: `dfs.replication=1` means one
> physical copy of every block. It is a lab configuration, not a resilient one.

---

## Quick start (Linux/Ubuntu)

```bash
# ---------- 1. Cloud Controller ----------
cd lan-saas-cloud/cloud-controller
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # put this in JWT_SECRET
nano .env      # set JWT_SECRET, HDFS_BASE_URL, CORS_ORIGINS (or STATIC_DIR)

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m app.bootstrap_admin        # create the first administrator (prompts)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
# ---------- 2. Frontend ----------
cd ../frontend
npm ci
npm run build        # -> frontend/dist   (then set STATIC_DIR in .env)
# or, for development:
npm run dev          # -> http://<server-ip>:5173
```

```bash
# ---------- 3. Real HDFS ----------
# see docs/lan-deployment.md sections 2 (single machine) and 3 (cluster)
```

Open `http://<server-ip>:8000` (single-origin) or `http://<server-ip>:5173`
(dev server) from any lab PC.

---

## Quick start (Windows, development only)

```powershell
cd lan-saas-cloud\cloud-controller
copy .env.example .env        # set JWT_SECRET; leave HDFS_ADAPTER=webhdfs only if a cluster exists
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.bootstrap_admin
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Without a Hadoop cluster, run the UI with the clearly labelled local-disk
adapter (`HDFS_ADAPTER=mock` in `.env`). The controller logs a loud warning and
the UI permanently shows "Mock storage (no HDFS)".

---

## Running against real HDFS

```bash
# single machine (pseudo-distributed), from docs/lan-deployment.md §2
hdfs namenode -format
start-dfs.sh
hdfs dfsadmin -report                     # Live datanode(s): 1

hdfs dfs -mkdir -p /saas-cloud
hdfs dfs -chown saascloud:supergroup /saas-cloud
hdfs dfs -chmod 0750 /saas-cloud
```

`cloud-controller/.env`

```ini
HDFS_ADAPTER=webhdfs
HDFS_BASE_URL=http://nn.lab.local:9870      # HTTP port, not the RPC port
HDFS_SERVICE_USER=saascloud
HDFS_ROOT=/saas-cloud
HDFS_JMX_URL=http://nn.lab.local:9870/jmx   # optional: enables DataNode liveness
```

Verify from the controller host:

```bash
curl -s "http://nn.lab.local:9870/webhdfs/v1/?op=LISTSTATUS&user.name=saascloud"
curl -s http://localhost:8000/api/health       # storage.healthy must be true
```

### Switching adapters

| `HDFS_ADAPTER` | Behaviour | When to use |
|---|---|---|
| `webhdfs` (default) | real Hadoop over WebHDFS; bytes go to HDFS | lab demonstration, production-like |
| `mock` | local disk under `HDFS_MOCK_DIR`; UI and health endpoint say "mock", startup logs a warning | frontend development on a machine without Hadoop |

The mock adapter never reports healthy HDFS (`healthy: null`), never claims
DataNodes, and is **off unless explicitly enabled**.

---

## API documentation

Full reference with request/response bodies and curl examples:
**[docs/api.md](docs/api.md)**. Interactive Swagger UI at `/docs`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | — | create account (rate limited) |
| POST | `/api/auth/login` | — | obtain JWT (rate limited) |
| GET | `/api/auth/me` | user | profile |
| GET | `/api/files` | user | list own files (`q`, `sort_by`, `order`, `limit`, `offset`) |
| POST | `/api/files/upload` | user | multipart upload → HDFS |
| GET | `/api/files/{id}/download` | user (owner) | streamed download |
| DELETE | `/api/files/{id}` | user (owner) | delete object + metadata |
| GET | `/api/dashboard/stats` | user | own file count, usage, quota, recent files |
| GET | `/api/admin/stats` | admin | user/file counts, total bytes, HDFS summary |
| GET | `/api/admin/users` | admin | per-user usage |
| GET | `/api/admin/hdfs-status` | admin | NameNode URL, health, latency, DataNodes |
| GET | `/api/admin/audit` | admin | audit events |
| PATCH | `/api/admin/users/{id}/role` | admin | promote/demote (not self) |
| GET | `/api/health` | — | component health |
| GET | `/api/storage/status` | — | reduced storage indicator for the UI badge |

### API design changes from the brief

* Added `GET /api/storage/status` so the sidebar indicator does not require
  admin rights, while keeping the detailed status admin-only.
* Added `GET /api/admin/audit` — requirement 11 asks for audit events, and
  admins need to read them.
* Added `PATCH /api/admin/users/{id}/role` for role management with a
  self-demotion guard.
* `GET /api/files` gained `limit`/`offset` and validated `sort_by`/`order`
  enumerations (the brief asked for search and sort; paging prevents unbounded
  responses).
* `POST /api/auth/register` returns a token immediately (201) so the user does
  not have to log in twice.
* Consistent error envelope `{"error": {"code","message","details"}}` for every
  failure mode, including 422 validation errors.

---

## HDFS integration notes

* **Two-step write protocol.** `op=CREATE` on the NameNode returns
  `307 Temporary Redirect`; the client must PUT the body to the `Location`
  (a DataNode) and expect `201`. The controller disables automatic redirect
  following for writes so the body is sent exactly once, and handles redirect
  chains up to 4 hops.
* **Reads are streamed.** `op=OPEN` also redirects to a DataNode; the controller
  yields 1 MiB chunks straight into the HTTP response.
* **Errors are translated.** Hadoop's JSON `RemoteException` is logged
  server-side; clients get safe messages (`storage_unavailable`, `not_found`)
  without stack traces, credentials or internal paths.
* **Timeouts and outages** become `503 storage_unavailable` with an actionable
  message; the controller reconnects automatically once the NameNode answers.
* **Configurable, nothing hardcoded.** `HDFS_BASE_URL`, `HDFS_SERVICE_USER`,
  `HDFS_AUTH`, `HDFS_ROOT`, `HDFS_TIMEOUT_SECONDS`, `HDFS_JMX_URL` are all
  environment variables (see `.env.example`).
* **Safe paths.** Objects live at `/saas-cloud/users/<user_uuid>/<file_uuid>`;
  both components are validated against `^[a-f0-9]{32}$`. Original filenames are
  metadata only.
* **Least privilege.** Directories are created 0750 and files 0640, owned by the
  service identity `saascloud`, not by `root` or `hdfs`.

Required Hadoop configuration, hostname resolution and port details:
[hadoop-config/README.md](hadoop-config/README.md) and
[docs/lan-deployment.md](docs/lan-deployment.md).

---

## Security model and honest limitations

**Implemented**

* Argon2id password hashing (bcrypt fallback); no plaintext anywhere.
* JWT with configurable expiry; the user is re-loaded from the database on every
  request, so deleted/deactivated accounts are rejected and the role always comes
  from the database, never from the token or request body.
* Ownership enforced server-side for view/download/delete; foreign ids return
  404 so existence is not leaked.
* Path-traversal defence: server-generated UUID paths, sanitised display names,
  content-type hardening, filename length caps.
* Upload limits (bytes and file count) and per-user quota enforced while
  streaming.
* Per-IP rate limiting on the authentication routes (429).
* CORS restricted to configured origins; security headers set on every response.
* Secrets only in `.env` (server-side); `.env.example` has placeholders only.
* Audit trail without passwords, hashes, tokens or file contents.
* Safe error messages: internal details go to the log with a reference id.

**Not implemented — do not claim otherwise**

* **No TLS.** The lab build is plain HTTP. Use nginx/caddy in front for HTTPS
  (steps in `docs/lan-deployment.md` §6).
* **No Kerberos / per-user HDFS identity.** All WebHDFS calls use one
  least-privilege service identity; the isolation between *users* comes from the
  controller, not from HDFS ACLs.
* **No horizontal scaling guarantees.** SQLite serialises writes, and the rate
  limiter is per-process and memory-only (resets on restart), which is why a
  reverse-proxy limiter is recommended.
* **No production security audit.** Firewall rules, HTTPS, systemd hardening and
  cookie-based tokens are documented but not applied in the lab configuration.
* **Consistency window:** a crash between the HDFS write and the SQLite commit
  can leave an orphaned object. Deletion prefers keeping metadata when HDFS is
  unreachable; the reverse case is reported and detectable with
  `python -m app.tools.inspect_state`.
* Intended for a **trusted educational LAN** only.

---

## Testing

Automated (details and expected results in [docs/testing.md](docs/testing.md)):

```bash
cd cloud-controller
python -m pytest                    # unit + API + WebHDFS protocol tests
python -m pytest -v

# real cluster (opt-in)
export RUN_HDFS_INTEGRATION=1 HDFS_BASE_URL=http://nn.lab.local:9870
python -m pytest app/tests/test_hdfs_live.py -v -s

cd ../frontend && npm run build     # frontend build check
```

End-to-end over real HTTP against a running controller:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8000
```

The suite covers: registration/login/me, generic auth errors, upload with
SHA-256 integrity, bytes stored outside SQLite, cross-user access denial
(download and delete), admin 401/403, role self-assignment attempts, search and
sorting, quota/file-count/oversized/empty-file rejection, filename sanitisation,
WebHDFS redirect handling, missing objects, unreachable NameNode, and audit
records containing no secrets.

---

## Verifying files with `hdfs dfs`

```bash
# what the database says
sqlite3 lan_saas.db "select id, owner_id, original_name, size_bytes, hdfs_path from file_records;"

# what HDFS actually contains
hdfs dfs -ls    /saas-cloud/users/<user_id>/
hdfs dfs -ls -R /saas-cloud/
hdfs dfs -stat  "%n %b bytes  owner=%u group=%g perm=%a" \
        /saas-cloud/users/<user_id>/<file_id>

# byte-for-byte comparison with the file you uploaded
hdfs dfs -cat /saas-cloud/users/<user_id>/<file_id> > /tmp/from_hdfs.bin
sha256sum /tmp/from_hdfs.bin ~/original.bin

# block placement and real replication (the honest evidence)
hdfs fsck /saas-cloud/users/<user_id>/<file_id> -files -blocks -locations
hdfs dfsadmin -report | head -20
```

---

## LAN deployment

Two options:

- **Docker (recommended):** [docs/docker-deployment.md](docs/docker-deployment.md).
  One port (8080 by default) serves both the UI and the API, so no CORS setup is
  needed for remote browsers.
- **Manual (Ubuntu, no containers):** [docs/lan-deployment.md](docs/lan-deployment.md) —
  prerequisites, Java compatibility, single-machine and multi-machine cluster,
  hostnames, firewall, HTTPS, systemd, startup order.

Summary of the ports (Docker deployment):

| Port | Service | Reachable from |
|---|---|---|
| 8080 | Cloud Controller **+ SPA** | lab clients |
| 9870 | NameNode WebHDFS/UI | `127.0.0.1` only (compose binds it to loopback) |
| 9864 | DataNode HTTP | `127.0.0.1` only (WebHDFS redirect target) |
| 9866 | DataNode transfer | cluster network only |
| 8020 | NameNode RPC | `127.0.0.1` only |

Manual (non-Docker) setups additionally expose 8000 for the controller and 5173
for the Vite dev server.

Remote clients must use the server's real address, never `localhost`:

```bash
# single-origin (recommended): controller serves the SPA
STATIC_DIR=/opt/lan-saas-cloud/frontend/dist
CORS_ORIGINS=http://192.168.1.20:8000

# split deployment
VITE_API_BASE_URL=http://192.168.1.20:8000/api npm run build
```

**Replication honesty:** a multi-computer cluster does not by itself
demonstrate fault tolerance. With one DataNode there is exactly one physical
copy. Show real block placement with `hdfs fsck ... -files -blocks -locations`
and live/dead DataNodes with `hdfs dfsadmin -report`; discuss replication only
in terms of what those commands actually print for your cluster.

---

## Troubleshooting

Quick pointers (full list: [docs/troubleshooting.md](docs/troubleshooting.md)):

| Symptom | Likely cause |
|---|---|
| 403 on every WebHDFS call | `dfs.webhdfs.enabled` not `true`, or NameNode not restarted |
| 404 for `/saas-cloud` in HDFS status | app root not created / not owned by `saascloud` |
| "DataNode could not be reached for the upload" | redirect hostname unresolvable or port 9864 blocked |
| `healthy: false`, "NameNode is unreachable" | wrong port (8020 vs 9870) or firewall |
| 503 on upload | HDFS down — the UI shows the real message |
| Browser CORS error | origin missing from `CORS_ORIGINS`, or use single-origin mode |
| Blank page with `STATIC_DIR` | path must contain `index.html` |
| `UnsupportedClassVersionError` | Hadoop on Java 17+; install JDK 11 |

---

## Demo script

1. Server: `start-dfs.sh`, then `hdfs dfsadmin -report` (show live DataNodes).
2. Server: start the controller; `curl http://localhost:8000/api/health` →
   `storage.adapter: webhdfs`, `healthy: true`.
3. Client PC 1: open `http://<server-ip>:8000` → register → Dashboard shows the
   green **HDFS connected** badge.
4. Upload a file (drag and drop) → it appears with size, timestamp and SHA-256.
5. Download it → verify with `sha256sum` on the client.
6. Server: `hdfs dfs -ls /saas-cloud/users/<uid>/` and
   `hdfs fsck <path> -files -blocks -locations` → show the bytes and the blocks.
7. Client PC 2: register another user, change the file id in the URL → **404**.
   Try `/api/admin/stats` → **403**.
8. Promote user 2 to admin from `/admin`; the audit trail shows
   `admin_role_change`.
9. Stop Hadoop → the badge turns red and upload returns a readable 503
   ("The HDFS NameNode is unreachable…"). Restart Hadoop → it recovers without a
   controller restart.

---

## Verified results

These were executed while building the project, on the machine described below.
Reproduce them with the commands shown.

**Environment where the following was run**

```
Windows 11 build 26100 (PowerShell 5.1)
Python 3.12.10 · Node v24.18.0 · npm 11.16.0 · Java 25 (host, unsuitable for Hadoop)
No Hadoop installed on the host
Docker Desktop 29.7.2 (Linux engine) -> used to run the real Hadoop cluster
```

### 1. Backend test suite — 66 passed, 2 skipped

```
$ python -m pytest
..................................................................       [100%]
66 passed, 2 skipped in 18.82s
exit code: 0
```

The 2 skipped tests are `app/tests/test_hdfs_live.py`, which requires a real
cluster (`RUN_HDFS_INTEGRATION=1`). They were verified to skip correctly, not to
pass.

### 2. Frontend production build — succeeded

```
$ npm run build
vite v6.4.4 building for production...
✓ 99 modules transformed.
dist/index.html                 0.41 kB │ gzip:  0.28 kB
dist/assets/index-*.css        20.92 kB │ gzip:  4.27 kB
dist/assets/index-*.js        262.30 kB │ gzip: 85.06 kB
✓ built in 2.70s
```

### 3. End-to-end HTTP smoke test — 24/24 checks passed

Controller started with `HDFS_ADAPTER=mock` and `STATIC_DIR=../frontend/dist`
(the mock adapter is used because no cluster existed here):

```
$ powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8000
== 1. Health ==                        [PASS] health responds (status=degraded storage=mock db=ok)
== 2. Registration + login ==          [PASS] register / login / me / wrong password rejected (401)
== 3. Upload ==                        [PASS] 201 / size recorded / sha256 recorded / path not exposed
== 4. List / stats ==                  [PASS] listed / storage_used_bytes / dashboard stats
== 5. Download + integrity ==          [PASS] 200 / content identical / sha256 matches
== 6. Ownership isolation ==           [PASS] other user cannot download (404) / cannot delete (404)
== 7. Admin protection ==              [PASS] regular user 403 / anonymous 401
== 8. Delete own file ==               [PASS] deleted / no longer listed
== 9. Validation / limits ==           [PASS] oversized 413 / filename sanitised / cleaned up

ALL SMOKE TESTS PASSED
```

### 4. Live HDFS round trip in Docker — real blocks on a real DataNode

This is the result that matters most. The full stack was run with
`docker compose up -d`: Apache Hadoop 3.4.1 (NameNode + DataNode + WebHDFS) in
one container, the FastAPI controller + built SPA in another.

Health, with **no** mock adapter:

```
$ curl -s http://localhost:8080/api/health
{
  "status": "ok",
  "database": "ok",
  "storage": {
    "adapter": "webhdfs",
    "mode_label": "Apache Hadoop HDFS (WebHDFS)",
    "healthy": true,
    "message": "NameNode reachable; configured root exists."
  }
}
```

A file was uploaded **through the API**, then read back **directly from HDFS**:

```
$ docker compose exec namenode hdfs dfs -ls -R /saas-cloud
drwxr-x---  - saascloud supergroup   0 2026-10-20 08:46 /saas-cloud/users
drwxr-x---  - saascloud supergroup   0 2026-10-20 08:46 /saas-cloud/users/a11d0225c20c42f8bc159062e26d60b6
-rw-r-----  1 saascloud supergroup  55 2026-10-20 08:46 /saas-cloud/users/a11d0225c20c42f8bc159062e26d60b6/0e86aaf68d744a7fb177e6101d15ed9e

$ docker compose exec namenode hdfs dfs -cat /saas-cloud/users/a11d0225.../0e86aaf6...
HDFS round-trip proof 2026-10-20T14:16:19.9900859+05:30
```

The byte count (55) matches what the API reported, and `hdfs dfs -cat` returns
the exact original content — read from HDFS, not through the application.

The block is physically on the DataNode's disk:

```
$ docker compose exec namenode find /hadoop/dfs/data -name 'blk_*' -printf '%s %p\n'
55 /hadoop/dfs/data/current/BP-1762578734-.../finalized/subdir0/subdir0/blk_1073741827
11 /hadoop/dfs/data/current/BP-1762578734-.../finalized/subdir0/subdir0/blk_1073741827_1003.meta

$ docker compose exec namenode hdfs fsck /saas-cloud -files -blocks -locations
The filesystem under path '/saas-cloud' is HEALTHY
Missing block groups: 0 · Corrupt block groups: 0 · Missing internal blocks: 0

$ docker compose exec namenode hdfs dfsadmin -report | grep -E "Live datanodes|Under replicated|Missing blocks"
Under replicated blocks: 0
Missing blocks: 0
Live datanodes (1):
Name: 172.22.0.2:9866 (namenode)   Hostname: namenode
```

**Read the "Live datanodes (1)" line as the honest evidence of the limitation:**
one DataNode means exactly one replica of every block. This is a
pseudo-distributed lab cluster. It is *not* fault-tolerant, and the report
should not claim that it is.

### 5. Persistence across a full container restart — verified

A file uploaded before `docker compose down` / `up -d` was still present in HDFS
afterwards, proving the named volumes hold both NameNode metadata and DataNode
blocks:

```
$ docker compose exec namenode hdfs dfs -ls -R /saas-cloud 2>/dev/null | grep -v '^d'
-rw-r-----  1 saascloud supergroup  55 2026-10-20 08:46 /saas-cloud/users/a11d0225.../0e86aaf6...
```

### 6. End-to-end HTTP smoke test — 24/24 checks passed

Run against the **containerised stack with real HDFS** (not the mock):

```
$ powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8080
== 1. Health ==                        [PASS] health responds (status=ok storage=webhdfs db=ok)
== 2. Registration + login ==          [PASS] register / login / me / wrong password rejected (401)
== 3. Upload ==                        [PASS] 201 / size recorded / sha256 recorded / path not exposed
== 4. List / stats ==                  [PASS] listed / storage_used_bytes / dashboard stats
== 5. Download + integrity ==          [PASS] 200 / content identical / sha256 matches
== 6. Ownership isolation ==           [PASS] other user cannot download (404) / cannot delete (404)
== 7. Admin protection ==              [PASS] regular user 403 / anonymous 401
== 8. Delete own file ==               [PASS] deleted / no longer listed
== 9. Validation / limits ==           [PASS] oversized 413 / filename sanitised / cleaned up

ALL SMOKE TESTS PASSED
```

The same 24 checks were also passed against a direct (non-Docker) uvicorn server
using the `mock` adapter, which is what confirmed the API contract independently
of the storage backend.

The backend suite was also run **inside the controller container** against real
HDFS, with an identical result:

```
$ docker compose exec controller python -m pytest -q
66 passed, 2 skipped in 12.25s
```

### 4b. Docker compose consistency checks — all passed

A static check (no daemon needed) that the compose file, Dockerfiles and Hadoop
configuration agree with each other. It caught two real bugs during development:
the controller being left on a different Docker network than the NameNode (which
caused `Temporary failure in name resolution`), and the NameNode directories
being on a root-owned filesystem.

```
$ python docker/validate_compose.py
ALL COMPOSE CONSISTENCY CHECKS PASSED
```

### 7. UI served from the controller container — verified

```
GET /                      -> 200   (React root element present)
GET /files                 -> 200   (SPA deep link falls back to index.html)
GET /assets/index-*.js     -> 200   262,296 bytes
GET /assets/index-*.css    -> 200    20,923 bytes
```

Because the SPA and the API share one origin, remote browsers need **no** CORS
configuration in this deployment.

### 8. Metadata vs storage consistency — no orphans, no leaks

```
$ python -m app.tools.inspect_state
Users (4) · File rows: 1 · Audit events: 17
Audit event types: ['file_delete','file_download','file_upload','login','login_failed','user_register']
Audit details that look like secrets: none
Objects missing in storage : none
Size mismatches            : none
```

### 9. What was *not* verified here

* **Multi-DataNode replication.** The cluster has one DataNode, so `hdfs fsck`
  can only ever show a single replica. Genuine replication (and the fail-over it
  would enable) was **not** tested and must not be claimed. `docs/lan-deployment.md`
  describes how to add DataNodes if you have spare machines.
* **NameNode high availability** (standby NameNode / automatic fail-over): not
  configured, not tested.
* **HTTPS and Kerberos.** Documented in `docs/docker-deployment.md` §11 as
  deliberately out of scope for a lab LAN; plain HTTP + simple auth were used.
* **Access from a second physical PC.** Reachability was confirmed only from the
  host itself. On this machine the *host's own* LAN IP was blocked by a
  machine-wide firewall/VPN condition (Antivirus VPN adapter present, Wi-Fi
  classified "Public") — an unrelated project on port 8000 was blocked the same
  way, so it is a host policy issue, not a defect in this stack. The fix is
  documented in `docs/docker-deployment.md` §6 and needs Administrator rights.
* **Sustained load / concurrency.** No load testing was performed.

---

## Documentation index

| Document | Contents |
|---|---|
| [docs/api.md](docs/api.md) | every endpoint, error envelope, curl examples, status semantics |
| [docs/docker-deployment.md](docs/docker-deployment.md) | containerised stack: one-command start, LAN access, firewall, volumes/backup, upgrades, troubleshooting |
| [docs/lan-deployment.md](docs/lan-deployment.md) | Ubuntu single/multi-machine HDFS, hostnames, ports, firewall, HTTPS, systemd, startup order |
| [docs/testing.md](docs/testing.md) | automated suites, smoke test, 16-step manual checklist, `hdfs dfs` verification |
| [docs/troubleshooting.md](docs/troubleshooting.md) | HDFS, controller, frontend and deployment problems |
| [docs/project-report-outline.md](docs/project-report-outline.md) | report structure with places for your measured results |
| [docs/viva-qa.md](docs/viva-qa.md) | 37 viva questions with answers |
| [hadoop-config/README.md](hadoop-config/README.md) | required Hadoop properties, hostname resolution, replication honesty |
