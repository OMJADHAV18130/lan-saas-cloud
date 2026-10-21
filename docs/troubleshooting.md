# Troubleshooting

## HDFS / WebHDFS

### `HTTP 403` on every WebHDFS call
`dfs.webhdfs.enabled` is not `true` in `hdfs-site.xml`, or the NameNode was not
restarted after editing it.

```bash
grep -A2 webhdfs $HADOOP_HOME/etc/hadoop/hdfs-site.xml
curl -s "http://<namenode>:9870/webhdfs/v1/?op=LISTSTATUS&user.name=$(whoami)"
```

### `HTTP 404 FileNotFoundException` for `/saas-cloud`
The application root does not exist yet.

```bash
hdfs dfs -mkdir -p /saas-cloud
hdfs dfs -chown saascloud:supergroup /saas-cloud
hdfs dfs -chmod 0750 /saas-cloud
```

### Upload fails with "The HDFS DataNode could not be reached for the upload."
The `CREATE` redirected to a DataNode address the controller cannot reach or
resolve. Inspect the redirect:

```bash
curl -i -X PUT "http://<namenode>:9870/webhdfs/v1/saas-cloud/probe?op=CREATE&user.name=saascloud&overwrite=true"
# look at the Location: header -> that exact host:port must be reachable
```

Fixes: add the DataNode hostname to `/etc/hosts` on the controller host, open
port 9864 in the firewall, or set `dfs.datanode.http.address=0.0.0.0:9864`.

### "The HDFS NameNode is unreachable."
```bash
ping <namenode>
curl -s -o /dev/null -w '%{http_code}\n' http://<namenode>:9870/
sudo ufw status             # is 9870 allowed from the controller host?
```
Also confirm `HDFS_BASE_URL` in `.env` uses the **HTTP** port (9870), not the
RPC port (8020) or the old Hadoop-2 port (50070).

### Everything is green but file sizes look wrong / `Size mismatches`
Run `python -m app.tools.inspect_state`. A mismatch means the metadata row and
the stored object disagree — usually an interrupted upload before the metadata
transaction. Delete the file from the UI (which removes both) and re-upload.

### `safe mode is ON`
```bash
hdfs dfsadmin -safemode get
hdfs dfsadmin -safemode leave      # only if the cluster is actually healthy
```

### DataNode not registering
```bash
jps                       # is DataNode running?
cat /opt/hadoop/logs/hadoop-*-datanode-*.log | tail -50
```
Usually a `clusterID` mismatch in `dfs.datanode.data.dir` after re-formatting
the NameNode, or the wrong `fs.defaultFS`. Remove the stale datanode directory
and restart — **only** in a lab cluster holding no real data.

### Java version errors
`UnsupportedClassVersionError`, `InaccessibleObjectException` or
`IllegalAccessError` when starting a daemon means the JVM is too new. Hadoop
3.3/3.4 needs **Java 8 or 11**:

```bash
sudo apt install openjdk-11-jdk
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
```

---

## Cloud Controller

### `503 storage_unavailable`
The controller cannot reach HDFS. Check the message in the UI or call
`/api/admin/hdfs-status` — it distinguishes "timed out", "unreachable",
"root missing" and "permission denied". Do not restart the controller: it
reconnects automatically once the NameNode answers.

### `401 unauthorized` immediately after logging in
`JWT_SECRET` changed (all previous tokens are invalid), the token expired
(`JWT_EXPIRES_MINUTES`), or the account was deleted/deactivated. Log in again.

### `422 validation_error` on upload
Empty file, or the request was truncated. Oversized uploads return **413**.

### `409 conflict` on upload
`MAX_FILES_PER_USER` reached. Delete a file or raise the limit in `.env`.

### CORS errors in the browser console
The browser origin is not in `CORS_ORIGINS`. Add the **exact** origin
(`http://192.168.1.20:5173`, not `192.168.1.20`), or use single-origin mode by
setting `STATIC_DIR` and loading the UI from the controller itself.

### Cannot reach the controller from another PC
* Uvicorn must bind `--host 0.0.0.0`, not `127.0.0.1`.
* Firewall: `sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp`.
* Test with `curl http://<server-ip>:8000/api/health` from the client.
* The client must not use `localhost` or `127.0.0.1` for the API address.

### First admin account
```bash
cd cloud-controller
python -m app.bootstrap_admin
```
There is **no default password**. The environment-driven variant
(`ADMIN_BOOTSTRAP_USERNAME`/`PASSWORD`) only runs when the users table is
empty; remove those variables afterwards.

### SQLite "database is locked"
Enable WAL (already done automatically) and avoid running many Uvicorn workers
against the same SQLite file. SQLite is fine for a lab; for real concurrency
switch `DATABASE_URL` to PostgreSQL.

### Where are the logs?
Uvicorn prints them; on systemd: `journalctl -u lan-saas-cloud -f`.
Unexpected errors are logged with a reference id that is also returned to the
client as `Reference: <id>` — use it to find the traceback server-side. Stack
traces are never returned to the browser.

---

## Frontend

### Blank page after `npm run build` + `STATIC_DIR`
`STATIC_DIR` must point at the directory containing `index.html`
(`.../frontend/dist`), and must be readable by the controller's user.

### `404` on deep links (`/files`) when served by the controller
The SPA fallback route is only registered when `STATIC_DIR` resolves to a
directory containing `index.html`. Check the startup log line
`Serving built frontend from ...`.

### Sidebar badge says "Mock storage (no HDFS)"
`HDFS_ADAPTER=mock` is active. Set `HDFS_ADAPTER=webhdfs`, correct
`HDFS_BASE_URL`, and restart. This mode is for UI development only and the app
says so explicitly — it never reports mock storage as healthy HDFS.
