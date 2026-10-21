# Viva questions and answers

## SaaS and cloud concepts

**1. What is SaaS, and how is this project SaaS?**
Software as a Service delivers a centrally hosted application to many users
over a network through a browser or thin client, with no per-user installation
and usage-based or role-based access. Here, one Cloud Controller instance serves
all lab users; each user gets an isolated account and private storage area, uses
it through a browser, and never installs or administers the storage backend.

**2. What exactly is the "Cloud Controller" in this project?**
It is our own FastAPI service that owns all business logic: authentication,
authorization, file ownership, quotas, metadata persistence, auditing, and the
translation of user requests into HDFS operations over WebHDFS. Clients talk
only to it; HDFS is never exposed to browsers.

**3. Difference between a cloud *service* and distributed *storage*?**
Distributed storage (HDFS) is an infrastructure layer that spreads data across
machines, replicates blocks and recovers from failures. A cloud service is the
multi-tenant product layer on top: identity, permissions, quotas, APIs, audit,
billing-like accounting and user experience. This project is a
**cloud service** built on top of **distributed storage**. One is the product,
the other is the substrate.

**4. Why is this a "private" cloud?**
It runs on the institution's own hardware inside the LAN, with no third-party
provider, no external network dependency and full administrative control over
data location and access.

**5. Why separate metadata from data?**
Metadata queries (listing, searching, sorting, quota checks, ownership) are
small, frequent and relational — a bad fit for HDFS, which is optimized for
large sequential files and gives no efficient search. SQLite answers those
queries quickly; HDFS stores the bulky bytes. It also keeps the controller
responsive and lets us enforce authorization cheaply before touching storage.

## HDFS internals

**6. What is HDFS and what problem does it solve?**
The Hadoop Distributed File System is a write-once, streaming-read, fault-
tolerant filesystem that stores very large files across many commodity machines
by splitting them into blocks and replicating those blocks.

**7. NameNode vs DataNode?**
The NameNode is the single metadata authority: it holds the namespace
(directories, filenames, permissions) and the mapping of files to blocks to
DataNodes. DataNodes store the actual block replicas and serve read/write
requests for them. DataNodes send periodic heartbeats/block reports; the
NameNode never streams file data itself.

**8. What is block replication, and does this project demonstrate fault tolerance?**
Each block is written to `dfs.replication` DataNodes. Fault tolerance is only
real when the number of live DataNodes is at least the replication factor and
the replicas are on separate machines. In this lab, a single-DataNode cluster
stores **one** physical copy, so **we do not claim fault tolerance**. We verify
actual placement with
`hdfs fsck /saas-cloud/users/<uid>/<file> -files -blocks -locations` and
`hdfs dfsadmin -report` (live DataNodes, under-replicated blocks).

**9. Default block size and why it is large?**
128 MB in Hadoop 3.x. Large blocks reduce NameNode metadata size and enable
long sequential reads, which is what HDFS is designed for. Our small lab files
therefore occupy one block each.

**10. What happens if a DataNode dies?**
The NameNode detects missing heartbeats, marks the node dead, and re-replicates
under-replicated blocks onto other live DataNodes. Reads fall back to another
replica. With only one DataNode there is no other replica to fall back to.

**11. Is HDFS good for many small files?**
No. Every file/directory/block consumes NameNode heap. Our design keeps user
files as single HDFS objects, but a workload of tens of millions of small files
would need a different layout (e.g. batching or an object store).

**12. Why not store files directly in SQLite or on local disk?**
Local disk is not shared, not replicated and not centrally managed; SQLite
blobs of multi-GB videos would bloat the database, destroy backup times and
serialise writes. HDFS provides centralized, scalable, block-replicated storage.

## WebHDFS and integration

**13. What is WebHDFS?**
A REST/HTTP interface to HDFS (`/webhdfs/v1/<path>?op=...`) that lets non-Java
clients read and write HDFS without the Hadoop RPC stack. We use it from Python
via `httpx`.

**14. Explain the WebHDFS write protocol — why can't you just PUT the file?**
`PUT ...?op=CREATE` goes to the **NameNode**, which decides which DataNode
should receive the data and answers `307 Temporary Redirect` with a `Location`
header naming that DataNode. The client must then send the actual bytes to that
Location and expects `201 Created`. Our client therefore disables automatic
redirect following, reads `Location` explicitly, and sends the body exactly
once — this is the part most naive implementations get wrong.

**15. And for reads?**
`GET ...?op=OPEN` also returns `307` to a DataNode, which then streams the
bytes. We stream them in 1 MiB chunks directly to the HTTP response, so a
multi-GB file is never held in the controller's memory.

**16. What configuration is required for WebHDFS?**
`dfs.webhdfs.enabled=true` in `hdfs-site.xml`; the NameNode HTTP address
(9870 in Hadoop 3.x) reachable from the controller; DataNode HTTP ports
(9864) reachable from the controller, because the redirect points there; and
consistent hostname resolution on every machine.

**17. Which HDFS ports must be open, and which must not?**
The controller needs 9870 (NameNode HTTP/WebHDFS) and 9864 (DataNode HTTP).
Cluster nodes need 8020/9866/9867 among themselves. Ports 9870/9864 must
**never** be reachable from client PCs: they bypass authentication, ownership
checks and auditing.

**18. How does the cluster know which user is calling?**
With `HDFS_AUTH=simple` the controller sends `user.name=<service user>`
(`saascloud`) on every request; HDFS enforces Unix-style permissions on the
target path. This is a single least-privilege service identity shared by the
controller — real deployments use Kerberos or proxy users so that per-end-user
identities reach HDFS. We keep the hook isolated (`HDFS_AUTH`) and document the
limitation rather than pretending it is per-user authentication.

**19. Why not let the browser talk to WebHDFS directly?**
It would expose the cluster to every client, require distributing credentials,
bypass ownership checks and auditing, and let users address arbitrary paths.
The controller is the single trust boundary.

## REST API and backend design

**20. What makes an API RESTful?**
Resource-oriented URLs, correct use of HTTP methods and status codes,
statelessness (each request carries its own credentials), a uniform
representation (JSON) and client/server separation.

**21. Why does `DELETE /api/files/{id}` sometimes return 404 for a file that exists?**
Because the id belongs to another user. We deliberately return the same 404 as
for a missing file so an attacker cannot probe which ids exist — authorization
failures should not leak existence.

**22. How are errors made consistent?**
A single exception hierarchy (`AppError` subclasses) plus handlers produce
`{"error": {"code", "message", "details"}}` for every failure, with meaningful
status codes (401/403/404/409/413/422/429/503/500). Validation errors from
Pydantic are reformatted into the same shape.

**23. How is ownership enforced?**
Never from the request. The JWT subject identifies the user, `get_current_user`
loads that user from the database, and `get_owned_file()` compares
`file_records.owner_id` with the authenticated user's id. A user id supplied by
the client is never used for authorization.

**24. How do you protect admin endpoints?**
`Depends(require_admin)` performs a server-side role check against the database
on every admin request. Ordinary users get 403, anonymous callers 401, and
registration never accepts a client-supplied role.

**25. Why is the WebHDFS path not returned in file listings?**
It is unnecessary for the client and would reveal internal layout. Storage paths
are server-generated UUID paths; the client only ever sees the numeric file id
and the original filename.

**26. What about path traversal?**
Filenames never become paths. The object path is
`/saas-cloud/users/<user_uuid>/<file_uuid>`, both UUIDs validated against
`^[a-f0-9]{32}$`. The display filename is sanitised (directory components from
both `/` and `\`, control characters and leading dots removed) and stored as
metadata only. Tests upload `../../../etc/passwd.txt` and assert nothing named
`passwd.txt` appears in storage.

**27. How are large uploads handled without exhausting memory?**
The multipart stream is spooled to a temporary file (`SpooledTemporaryFile`,
8 MiB in memory then disk) while the byte count is checked against
`MAX_UPLOAD_BYTES`, so the limit is enforced before HDFS is touched. Download
and HDFS read paths are chunked generators.

## Authentication and security

**28. How are passwords stored?**
Argon2id hashes (memory-hard, salted per password) via `argon2-cffi`, with a
bcrypt fallback. Plaintext passwords are never persisted, logged, or returned.

**29. Why JWT, and what are its risks?**
JWTs are self-contained and stateless: the controller can verify identity
without a session store. Risks: they cannot be revoked before expiry, the
payload is only base64 (never put secrets in it), and storing them in
`localStorage` exposes them to XSS. Mitigations: short expiry
(`JWT_EXPIRES_MINUTES`) and a server-side user lookup on every request — so a
deleted or deactivated account is rejected even with a valid token, and role is
read from the database rather than trusted from the token.

**30. How is brute force mitigated?**
A per-IP sliding-window limiter on `/api/auth/register` and `/api/auth/login`
returning 429, generic "Invalid username or password" messages that do not
reveal whether an account exists, and audit records for failed logins. The
limiter is per-process and memory-only — documented as a lab-level control that
should be complemented by `limit_req` at a reverse proxy.

**31. What secrets does the system hold, and where?**
Only two: the JWT signing secret and (optionally) HDFS credentials. Both live in
`cloud-controller/.env` (server-side), never in the frontend bundle and never in
the repository. `.env.example` contains placeholders only.

**32. What is stored in the audit trail, and what is deliberately excluded?**
Event type, actor id/username, source IP, UTC timestamp, outcome and a short
detail (`file_id=... size=...`). Excluded: passwords, password hashes, tokens
and file contents — asserted by an automated test that scans audit responses
for `$argon2`, `Bearer`, `eyJ…`-style strings and password-like text.

**33. What is the security posture of this lab build, honestly?**
It is intended for a trusted educational LAN. Transport is plain HTTP, so
credentials are sniffable; there is no 2FA, no CSRF token scheme (the API is
bearer-token based, which limits CSRF), no Kerberos, and no external security
audit. We do not claim production security. `docs/lan-deployment.md` describes
the TLS, firewall, systemd and cookie-hardening steps required to go further.

## Reliability and consistency

**34. SQLite and HDFS can disagree — how is that handled?**
Upload writes HDFS first, then commits metadata; if the commit fails the HDFS
object is deleted (rollback). Delete removes the HDFS object first and keeps
metadata if HDFS is unreachable (safe retry); if the metadata delete then fails,
the row remains and is reported as an administrator-visible inconsistency. The
remaining window (a crash between the two steps) can leave an orphan object;
`python -m app.tools.inspect_state` detects orphans and size mismatches. This is
a documented limitation, not hidden behaviour.

**35. Why does deleting a file return 503 rather than 500 sometimes?**
Because HDFS being unavailable is an expected operational condition, not a bug.
503 tells the client the operation can be retried, and the message explains that
nothing was changed.

**36. Does the UI ever fake data?**
No. Every displayed value comes from an API response — including HDFS status,
which reports `healthy: null` and "mock" when Hadoop is not in use. When the
cluster is down the UI shows the real error text produced by the controller.

**37. How would you scale the controller?**
Move metadata to PostgreSQL, run multiple Uvicorn workers/containers behind a
load balancer, use object storage or an HDFS-aware client pool, and move rate
limiting to Redis. The controller is stateless apart from `.env`, so it scales
horizontally; SQLite and the in-process limiter are the two current bottlenecks.
