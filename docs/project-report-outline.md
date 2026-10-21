# Project report outline

**Title:** LAN-Based SaaS Cloud Storage System Using an HDFS Cloud Controller

Fill in the bracketed values with your own measurements from
`docs/testing.md` — do **not** copy numbers from anywhere else.

---

## 1. Abstract

A private, browser-accessible cloud storage service for a laboratory LAN. A
purpose-built **Cloud Controller** (FastAPI) authenticates users, enforces file
ownership, keeps metadata in SQLite and stores file contents in **Apache Hadoop
HDFS** through the **WebHDFS REST API**. Users register, log in, upload,
search, download and delete their own files; administrators see aggregate usage,
cluster status and an audit trail. The report should state the measured results
(users tested, files uploaded, throughput observed on the lab LAN) and the
honest limitations (single-DataNode development cluster, HTTP-only transport).

## 2. Objectives

1. Provide multi-user, browser-based private cloud storage over an existing LAN.
2. Separate **metadata** (SQLite) from **bulk data** (HDFS).
3. Implement our own Cloud Controller instead of exposing HDFS to clients.
4. Integrate HDFS correctly via WebHDFS, including the NameNode→DataNode redirect.
5. Enforce authentication, authorization and file ownership server-side.
6. Demonstrate a SaaS delivery model: one service instance, many tenants, no
   client-side installation.
7. Produce an audit trail for security-relevant events.
8. Provide a reproducible lab deployment and test procedure.

## 3. Existing system

Describe what a typical college lab uses today: shared Windows folders / SMB
shares, pendrives, Google Drive or OneDrive (external dependency, data leaves
the campus, no administrative control), or a plain FTP server with shared
accounts. Note the problems: no per-user ownership, no audit trail, no
centralized storage management, no separation of metadata and data, quota and
search unavailability.

## 4. Proposed system

* Single Cloud Controller with a documented REST API; the browser never talks
  to HDFS.
* JWT-authenticated multi-tenant accounts with Argon2 password hashing.
* Contents in HDFS under `/saas-cloud/users/<user_uuid>/<file_uuid>` with
  least-privilege permissions; original filenames kept as metadata only.
* Metadata: ownership, size, content type, SHA-256, timestamps, audit events.
* Admin dashboards with real cluster status (never faked) and audit review.
* Single-origin LAN deployment: React SPA served by the controller.

Add a comparison table (existing vs proposed) covering ownership, audit,
centralized storage, search, scaling and administrative visibility.

## 5. Architecture

```
Client PC browser
      |  HTTP (LAN)
      v
React SPA (Vite, Tailwind, Router, Axios)
      |  REST + JWT
      v
FastAPI Cloud Controller ---- SQLite (metadata, users, audit)
      |  HTTP/WebHDFS
      v
HDFS NameNode (9870) --307 redirect--> DataNode (9864) --> local block storage
```

Include: component responsibility table, request lifecycle diagram for an
upload (auth → validation → spool → WebHDFS CREATE → redirect → DataNode write
→ metadata commit → audit), and the trust boundary explanation (what each
layer is allowed to see).

## 6. Modules

| Module | Responsibility |
|---|---|
| `app/core` | configuration, error model, password/JWT security, rate limiting |
| `app/db` | SQLAlchemy engine/session, schema creation |
| `app/models` | `users`, `file_records`, `audit_events` |
| `app/schemas` | request/response validation contracts |
| `app/auth` | registration, login, `/me`, token→user dependency, admin guard |
| `app/api` | files, dashboard, admin, health routers |
| `app/services/hdfs_service` | WebHDFS adapter + opt-in mock adapter |
| `app/services/file_service` | validation, ownership, SQLite↔HDFS consistency |
| `app/services/audit_service` | append-only audit events |
| `frontend/src` | pages, layout, API client, auth context, UI primitives |

## 7. Technologies

React 18 + Vite 6, Tailwind CSS 3, React Router 6, Axios · Python 3.11+,
FastAPI, Pydantic v2, Uvicorn · SQLAlchemy 2 + SQLite · Argon2id (`argon2-cffi`)
+ PyJWT · httpx WebHDFS client · Apache Hadoop 3.4.x (HDFS) with WebHDFS ·
pytest + FastAPI TestClient · Ubuntu 22.04/24.04 server, JDK 11.

## 8. Implementation

Describe, with code excerpts and screenshots:

1. Password hashing and JWT issuance; why roles are read from the DB, not the token.
2. The upload pipeline and the size cap enforced while streaming.
3. **WebHDFS protocol handling** (the key technical contribution): why
   automatic redirect following is disabled for writes, how `Location` is
   followed to the DataNode, how the body is sent exactly once, how reads are
   streamed in 1 MiB chunks, and how Hadoop `RemoteException` JSON is mapped to
   safe errors.
4. Server-generated object paths and filename sanitisation (traversal defence).
5. Ownership enforcement: `get_owned_file()` returns 404 for foreign ids.
6. Delete ordering and partial-failure behaviour.
7. Audit records and the rule that secrets are never logged.
8. Frontend: protected routes, loading/empty/error states, drag-and-drop with
   progress, delete confirmation, real values only.

## 9. Testing

Summarise the automated suites (`docs/testing.md`) with the **actual** output of
`python -m pytest` on your machine, the frontend build result, the smoke-test
output, and the manual checklist results. Include the real-HDFS round trip with
the replication factor your cluster reported.

## 10. Results

Report measured values:

* files uploaded/downloaded and byte-for-byte verification via `sha256sum`
* `hdfs fsck ... -files -blocks -locations` output showing real block placement
* `hdfs dfsadmin -report` DataNode count and under-replicated blocks
* download/upload time for a large file on the LAN (state file size and link speed)
* response codes observed for the negative tests (401/403/404/413/503/429)
* HDFS status endpoint output when the cluster is stopped

## 11. Limitations

* Single-DataNode / single-machine setup is a **development configuration**;
  several computers alone do not demonstrate fault tolerance. Replication is
  only meaningful with `dfs.replication` ≤ number of live DataNodes, and must be
  verified with `fsck -locations`.
* Plain HTTP: no transport encryption; acceptable only on a trusted lab LAN.
* SQLite serialises writes; no horizontal controller scaling; in-process rate
  limiting is per-worker and per-process.
* No resumable uploads, versioning, sharing, garbage collection, or
  deduplication.
* Admin DataNode counts require JMX; WebHDFS alone does not expose them.
* SQLite/HDFS consistency is handled with best-effort rollback; a crash between
  the two steps can leave an orphan object (cleanup documented).
* No antivirus scanning or content-type enforcement of stored files.

## 12. Future scope

Real (non-lab) security: TLS, refresh tokens, HttpOnly cookies, 2FA, Kerberos
for HDFS (`HDFS_AUTH` extension point is already isolated), Hadoop proxy users
instead of shared identities, nginx/Redis rate limiting, PostgreSQL metadata
store, object storage tiering, resumable/chunked uploads, file sharing with
expiring links, quotas per user, virus scanning, containerised deployment,
metrics (Prometheus) and centralized logging.

## 13. References

Apache Hadoop documentation (HDFS Architecture, WebHDFS REST API), FastAPI and
Pydantic documentation, OWASP Authentication and Password Storage Cheat Sheets,
RFC 7519 (JWT), Argon2 specification.
