# Docker Deployment Guide

This guide containerises the **entire** stack:

| Container | Contents | Purpose |
|---|---|---|
| `volume-init` | Alpine | One-shot job that fixes ownership on the named volumes, then exits |
| `namenode` | Apache Hadoop 3.4.1 | NameNode + DataNode + WebHDFS (single node) |
| `controller` | FastAPI + built React SPA | Cloud Controller API **and** the web UI on one port |

Two advantages over the manual setup in `docs/lan-deployment.md`:

1. **No Java version problem.** Hadoop 3.4.1 needs Java 8/11. The container ships
   its own JDK 11, so a host with Java 25 (like a typical student laptop) works.
2. **One command.** HDFS is formatted, started, and wired to the controller
   automatically.

> **Honesty note.** Even in Docker this remains a **single-DataNode,
> pseudo-distributed** cluster. `dfs.replication=1` means every block exists
> **once**. Losing the `hdfs-datanode-data` volume loses the data. This is a
> development/lab configuration, not a resilient production cluster.

---

## 1. Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose`, **not**
  `docker-compose`), or Docker Desktop.
- ~4 GB free RAM and ~3 GB free disk.
- Ports: **8080** (published to the LAN) plus **8020/9870/9864** bound to
  `127.0.0.1` only.

Check:

```bash
docker version
docker compose version
```

### Why 8080 and not 8000?

`CONTROLLER_PORT` defaults to **8080** because port 8000 is very often already
taken on a development machine (another project, another container). If 8080 is
also busy, change `CONTROLLER_PORT` in `.env`. Only this one port is exposed to
the lab LAN.

---

## 2. First start

```bash
# 1. create your compose environment file
cp .env.example .env

# 2. generate a strong secret and put it in .env as JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 3. build and start everything
docker compose up -d --build
```

Compose **refuses to start without `JWT_SECRET`** - that is deliberate, so a
default secret can never end up in a submission or on a lab network.

Watch it come up (first run formats the NameNode, which takes a few seconds):

```bash
docker compose ps
docker compose logs -f namenode
```

Expected steady state:

```
NAME                   STATUS                    PORTS
lan-saas-controller    Up (healthy)              0.0.0.0:8080->8000/tcp
lan-saas-namenode      Up (healthy)              127.0.0.1:8020->8020/tcp, 127.0.0.1:9870->9870/tcp, ...
lan-saas-volume-init   Exited (0)
```

Then open **<http://localhost:8080>**. The health badge should read
**"Apache Hadoop HDFS (WebHDFS)"** and `/api/health` should report
`"healthy": true`.

---

## 3. Create the first administrator

There is **no default admin password** anywhere in this project. Create one:

```bash
docker compose exec controller python -m app.bootstrap_admin
```

You will be prompted for a username, e-mail, and password. The command refuses
to run when an admin already exists.

Non-interactive alternative - set these in `.env` **before the first start**
(they are ignored once the users table is non-empty):

```
ADMIN_BOOTSTRAP_USERNAME=admin
ADMIN_BOOTSTRAP_PASSWORD=<a real password>
```

Then `docker compose up -d` and check `docker compose logs controller`.

---

## 4. Proving the storage is really HDFS

Upload a file through the web UI, then verify it **with the HDFS CLI**, not with
the application:

```bash
# list everything the controller has stored
docker compose exec namenode hdfs dfs -ls -R /saas-cloud

# read a file straight out of HDFS (bypasses the API entirely)
docker compose exec namenode hdfs dfs -cat /saas-cloud/users/<user_uuid>/<file_uuid>

# block-level integrity + placement
docker compose exec namenode hdfs fsck /saas-cloud -files -blocks -locations

# live DataNodes, capacity, replication
docker compose exec namenode hdfs dfsadmin -report
```

If `hdfs dfs -cat` prints your file's exact contents, the bytes really are in
HDFS. If `dfsadmin -report` shows **1 live DataNode**, that is the honest state
of this lab cluster - one replica, no fault tolerance.

You can also see the block files on the DataNode's virtual disk:

```bash
docker compose exec namenode find /hadoop/dfs/data -name 'blk_*' -printf '%s %p\n'
```

The size of each `blk_*` file matches the size of an uploaded object.

---

## 5. Everyday commands

```bash
docker compose ps                      # status
docker compose logs -f controller      # API + SPA logs
docker compose logs -f namenode        # HDFS logs
docker compose restart controller      # restart the API only
docker compose stop                    # stop, keep all data
docker compose down                    # remove containers, KEEP volumes
docker compose up -d                   # start again
```

### Verifying HDFS is genuinely available

```bash
curl -s http://localhost:8080/api/health
```

- `"adapter": "webhdfs"` + `"healthy": true` -> talking to real HDFS.
- `"adapter": "webhdfs"` + `"healthy": false` -> HDFS is down; check
  `docker compose logs namenode`.
- `"adapter": "mock"` -> **local disk, not HDFS**. Only possible if someone set
  `HDFS_ADAPTER=mock`; compose does not do this.

---

## 6. Accessing it from other computers on the LAN

1. Find the host's LAN IP: `ipconfig` (Windows) / `ip addr` (Linux).
2. Open `http://<LAN-IP>:8080` from another machine.

Because the SPA and the API share one origin, **no CORS configuration is needed**
for remote browsers. Just add the URL you actually type to `CORS_ORIGINS` in
`.env` if you also use a separate dev server:

```
CORS_ORIGINS=http://localhost:8080,http://192.168.1.38:8080
```

Then `docker compose up -d` to apply.

### Allow the port through the host firewall

The container port is published, but the **host** firewall still has to allow it.

**Windows** (run PowerShell *as Administrator*):

```powershell
New-NetFirewallRule -DisplayName "LAN SaaS Cloud Storage 8080" `
  -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

**Ubuntu / UFW:**

```bash
sudo ufw allow 8080/tcp
```

> **A note specific to this machine.** During testing, `http://127.0.0.1:8080`
> worked but `http://192.168.1.38:8080` did **not**, even from the same computer.
> A second, unrelated project on port 8000 was unreachable the same way, which
> shows the cause is machine-wide (the Wi-Fi network is classified "Public" and
> a McAfee VPN adapter is present), **not** a fault in this container setup.
> The firewall rule above is the fix; it needs Administrator rights.

---

## 7. Data, persistence and reset

All state lives in **named volumes**, never in the image:

| Volume | Holds |
|---|---|
| `hdfs-namenode-data` | NameNode metadata (the filesystem's "table of contents") |
| `hdfs-datanode-data` | **the actual file blocks** |
| `hdfs-tmp` | Hadoop temp space |
| `controller-data` | SQLite metadata DB (users, file records, audit log) |

So `docker compose down` followed by `docker compose up -d` keeps every file.
This was verified: a file uploaded before a restart was still present in HDFS
afterwards.

### Full reset (DESTROYS ALL DATA)

```bash
docker compose down -v      # -v removes the named volumes too
docker compose up -d --build
```

You will get a freshly formatted NameNode and an empty database.

### Backup

```bash
# metadata + blocks, as a file you can move to another machine
docker run --rm \
  -v lan-saas-cloud_hdfs-namenode-data:/nn:ro \
  -v lan-saas-cloud_hdfs-datanode-data:/dn:ro \
  -v lan-saas-cloud_controller-data:/db:ro \
  -v "${PWD}":/backup alpine:3.20 \
  tar czf /backup/lan-saas-backup.tgz -C / nn dn db
```

Back up the NameNode and DataNode volumes **together** - one without the other
is not a usable HDFS.

---

## 8. Upgrading and rebuilding

```bash
# rebuild after changing backend or frontend source
docker compose build --build-arg CACHEBUST=$(date +%s) controller
docker compose up -d controller
```

The `controller` image builds the React SPA in a first stage and copies the
result into the Python image, so **there is no Node.js requirement on the host**.

---

## 9. Running the tests against the container

```bash
# the in-container test suite
docker compose exec controller python -m pytest -q
```

The 24-check HTTP smoke test also runs against the containerised stack:

```powershell
# Windows PowerShell 5.1
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8080
```

```bash
# Linux / macOS / WSL
pwsh -File scripts/smoke_test.ps1 -BaseUrl http://127.0.0.1:8080
```

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `required variable JWT_SECRET is missing` | No `.env`, or it lacks `JWT_SECRET` | `cp .env.example .env` and set `JWT_SECRET` |
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | Another service owns that port | Set `CONTROLLER_PORT` in `.env` to a free port |
| `Temporary failure in name resolution` | `controller` and `namenode` are on different Docker networks | Keep both on `cloudnet` (see `docker/validate_compose.py`) |
| NameNode restarts with `Cannot create directory /hadoop/dfs/name/current` | Volume owned by `root`, container runs as `hadoop` | Run `docker compose up -d` so `volume-init` prepares ownership first |
| Container healthy but browser cannot reach it | Host firewall | Add the inbound rule in section 6 |
| `storage.healthy: false` | NameNode still starting, or crashed | `docker compose logs namenode`; first run needs a few seconds to format |
| Health shows `"adapter": "mock"` | `HDFS_ADAPTER=mock` was set | Remove it; compose sets `webhdfs` |

### Consistency check between SQLite and HDFS

Detects orphaned objects (written to HDFS but not recorded in the DB) and size
mismatches:

```bash
docker compose exec controller python -m app.tools.inspect_state
```

Run this after any abrupt shutdown, since a crash between the HDFS write and the
metadata commit can leave an orphan block.

---

## 11. What this deployment does NOT do

Stated plainly so the report and viva are accurate:

- **Not highly available.** One NameNode, one DataNode. Both are single points
  of failure. There is no standby NameNode and no second replica.
- **No fault tolerance.** `dfs.replication=1`; losing the DataNode volume loses
  the data.
- **Not HTTPS.** Traffic is plain HTTP. Add a TLS-terminating reverse proxy
  (Caddy/nginx) in front for anything beyond a lab LAN.
- **No Kerberos.** WebHDFS uses `user.name=simple` pseudonymous auth, appropriate
  only for a trusted lab network.
- **SQLite, single process.** The controller runs one Uvicorn worker on purpose:
  SQLite and the in-process rate limiter are per-process. Moving to PostgreSQL
  is the prerequisite for scaling out.
