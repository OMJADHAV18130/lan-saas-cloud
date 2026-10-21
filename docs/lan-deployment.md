# LAN deployment guide (Linux / Ubuntu first)

Target scenario: **one Ubuntu server** running the HDFS cluster and the Cloud
Controller, plus **several lab client PCs** (Windows or Linux) using the UI in
a browser.

---

## 0. Ports used by this project

| Port | Service | Who needs access |
|---|---|---|
| 5173 | Vite dev server (frontend, development) | lab clients |
| 8000 | FastAPI Cloud Controller | lab clients |
| 9870 | WebHDFS / NameNode HTTP UI | **the controller host only** |
| 9864 | DataNode HTTP (streaming I/O) | **the controller host** (WebHDFS redirect target) |
| 9866 | DataNode data transfer | controller host (and other DataNodes in a multi-node cluster) |
| 9867 | DataNode IPC | cluster nodes only |
| 8020 | NameNode RPC | cluster nodes + `hdfs dfs` CLI users only |
| 22 | SSH | administration |

**Never expose 9870/9864/9866/9870 to end users.** They bypass the controller:
no authentication, no ownership checks, no audit trail. Only 8000 (and 5173 in
development) should be reachable from client PCs.

---

## 1. Prerequisites

```bash
sudo apt update
sudo apt install -y openjdk-11-jdk ssh rsync curl python3.11 python3.11-venv python3-pip
java -version      # must print 11.x
```

> **Java compatibility — read this before choosing a version.**
> Apache Hadoop 3.3.x / 3.4.x are supported on **Java 8 and Java 11**.
> Java 17/21/25 are *not* supported for the Hadoop daemons. On modern Ubuntu
> install `openjdk-11-jdk` explicitly; several newer Hadoop releases still
> crash on Java 17 with `IllegalAccessError` / `InaccessibleObjectException`.
> (This is why the development machine used for this project — which had
> Java 25 — cannot run a Hadoop daemon, and why Hadoop is run under Ubuntu.)

Create a dedicated service identity (least privilege — do **not** run the
controller or the HDFS service calls as `root`):

```bash
sudo useradd -r -m -s /usr/sbin/nologin hdpsvc   # not required, optional
```

---

## 2. Single-machine (pseudo-distributed) Hadoop — develop here first

### 2.1 Download and unpack

```bash
cd /opt
sudo curl -fLO https://downloads.apache.org/hadoop/common/hadoop-3.4.1/hadoop-3.4.1.tar.gz
sudo tar -xzf hadoop-3.4.1.tar.gz
sudo mv hadoop-3.4.1 hadoop
sudo chown -R $USER:$USER /opt/hadoop
```

### 2.2 Environment

Add to `~/.bashrc` (and `/opt/hadoop/etc/hadoop/hadoop-env.sh`):

```bash
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=/opt/hadoop
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
export PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin
export HDFS_NAMENODE_USER=$USER
export HDFS_DATANODE_USER=$USER
export HDFS_SECONDARYNAMENODE_USER=$USER
```

### 2.3 Configuration files

**`$HADOOP_HOME/etc/hadoop/core-site.xml`**

```xml
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:8020</value></property>
  <property><name>hadoop.tmp.dir</name><value>/data/hadoop/tmp</value></property>
  <property><name>hadoop.http.staticuser.user</name><value>hdfs</value></property>
</configuration>
```

**`$HADOOP_HOME/etc/hadoop/hdfs-site.xml`**

```xml
<configuration>
  <property><name>dfs.namenode.http-address</name><value>localhost:9870</value></property>
  <property><name>dfs.webhdfs.enabled</name><value>true</value></property>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>file:///data/hadoop/hdfs/namenode</value></property>
  <property><name>dfs.datanode.data.dir</name><value>file:///data/hadoop/hdfs/datanode</value></property>
  <property><name>dfs.datanode.data.dir.perm</name><value>750</value></property>
</configuration>
```

Copy the templates from `hadoop-config/` and edit them if you prefer.

### 2.4 Prepare directories, format, start

```bash
sudo mkdir -p /data/hadoop/tmp /data/hadoop/hdfs/namenode /data/hadoop/hdfs/datanode
sudo chown -R $USER:$USER /data/hadoop

hdfs namenode -format     # ONCE only, and only on the NameNode
start-dfs.sh
jps                       # expect NameNode, DataNode, SecondaryNameNode
```

Verify the cluster:

```bash
hdfs dfsadmin -report                  # "Live datanode(s) : 1"
curl -s "http://localhost:9870/webhdfs/v1/?op=LISTSTATUS&user.name=$USER"
```

### 2.5 Prepare the application root and identity

```bash
sudo useradd -r -m -s /usr/sbin/nologin saascloud
hdfs dfs -mkdir -p /saas-cloud
hdfs dfs -chown saascloud:supergroup /saas-cloud
hdfs dfs -chmod 0750 /saas-cloud
hdfs dfs -ls -ld /saas-cloud
```

### 2.6 Run the controller against real HDFS

```bash
cd lan-saas-cloud/cloud-controller
cp .env.example .env
# edit .env:  HDFS_ADAPTER=webhdfs, HDFS_BASE_URL=http://localhost:9870,
#             HDFS_SERVICE_USER=saascloud, JWT_SECRET=<random>
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.bootstrap_admin          # create the first administrator
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` is what makes the controller reachable from other lab PCs.

Check honest health:

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
# "storage": {"adapter": "webhdfs", "healthy": true, ...}
```

---

## 3. Multi-machine cluster (1 NameNode + 1..N DataNodes)

### 3.1 Hostnames

On **every** machine, `/etc/hosts`:

```
192.168.1.20   nn.lab.local    namenode
192.168.1.21   dn1.lab.local   datanode1
192.168.1.22   dn2.lab.local   datanode2
```

`ping dn1.lab.local` must succeed from the controller host. WebHDFS redirects
to DataNode addresses derived from these names, so resolution on the
**controller** matters as much as on the cluster.

### 3.2 `workers` file (on the NameNode)

`$HADOOP_HOME/etc/hadoop/workers`:

```
dn1.lab.local
dn2.lab.local
```

### 3.3 Configuration

Use `hadoop-config/core-site.xml.example` and
`hadoop-config/hdfs-site.xml.example`, replacing `nn.lab.local`. Copy the same
files to every DataNode.

### 3.4 Passwordless SSH and startup

```bash
ssh-keygen -t rsa -b 4096            # on the NameNode, press Enter
ssh-copy-id dn1.lab.local
ssh-copy-id dn2.lab.local

hdfs namenode -format                # NameNode only, once
start-dfs.sh                         # starts NameNode + the workers
```

On each DataNode: `jps` should show `DataNode`. On the NameNode:
`hdfs dfsadmin -report` should list every DataNode as live.

### 3.5 Replication — what is actually demonstrated

```bash
hdfs dfsadmin -report | head -30
#   Live datanode(s) : 2
#   Under-replicated blocks: ...

hdfs fsck /saas-cloud -files -blocks -locations
```

* With 2 DataNodes and `dfs.replication=2` you can show **two physical block
  locations** for one file.
* With 1 DataNode you have **one copy** — this is a development configuration.
* Existence of several computers does **not** prove fault tolerance. Show
  block placement with `fsck -locations`, then stop a DataNode and observe the
  under-replication/missing-block reporting. Only then can you discuss
  resilience honestly.

### 3.6 Point the controller at the cluster

`.env` on the controller host:

```
HDFS_BASE_URL=http://nn.lab.local:9870
HDFS_SERVICE_USER=saascloud
HDFS_ROOT=/saas-cloud
HDFS_JMX_URL=http://nn.lab.local:9870/jmx     # optional, enables DataNode counts
```

The controller host may be a separate machine from the NameNode; it only needs
network access to 9870 (NameNode HTTP) and 9864 (DataNode HTTP).

---

## 4. Frontend for LAN clients

### Option A (recommended for the demo): single origin

Build once on the server and let FastAPI serve it — no CORS, no second port:

```bash
cd lan-saas-cloud/frontend
npm ci
npm run build                       # produces frontend/dist

# controller .env
STATIC_DIR=/opt/lan-saas-cloud/frontend/dist
CORS_ORIGINS=http://192.168.1.20:8000
```

Restart the controller. Clients open `http://192.168.1.20:8000` and the SPA
uses relative `/api/...` URLs.

### Option B: Vite dev server / separate frontend host

```bash
cd frontend
npm ci
npm run build           # CI: set VITE_API_BASE_URL first (see below)
npm run dev             # binds 0.0.0.0:5173 (--host is set in package.json)
```

**CI note:** in CI set `VITE_API_BASE_URL` to the controller's LAN URL before
`npm run build`; the value is compiled into the bundle.

To point the dev server's proxy at a controller on another machine:

```bash
VITE_API_PROXY_TARGET=http://192.168.1.20:8000 npm run dev
```

For a split production deployment (static hosting on another port/PC) build
with the absolute API URL:

```bash
VITE_API_BASE_URL=http://192.168.1.20:8000/api npm run build
# then allow that frontend origin on the controller:
#   CORS_ORIGINS=http://192.168.1.20:5173
```

**Do not hardcode `localhost`** anywhere a remote client uses it: `localhost`
on a client PC means that client PC.

---

## 5. Firewall (ufw)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp            # administration
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp   # controller
sudo ufw allow from 192.168.1.0/24 to any port 5173 proto tcp   # dev UI only
sudo ufw enable
sudo ufw status verbose
```

Restrict cluster ports to the machines that need them:

```bash
sudo ufw allow from 192.168.1.20 to any port 9870 proto tcp     # WebHDFS: controller only
sudo ufw allow from 192.168.1.20 to any port 9864 proto tcp     # DataNode HTTP
sudo ufw allow from 192.168.1.0/24 to any port 9866 proto tcp   # cluster transfer
sudo ufw allow from 192.168.1.0/24 to any port 8020 proto tcp   # CLI users only
```

Verify from a client PC:

```bash
curl -s http://192.168.1.20:8000/api/health          # should answer
curl -s --max-time 3 http://192.168.1.20:9870/       # should hang/fail (blocked)
```

---

## 6. HTTPS and production notes

The lab build speaks plain HTTP. Credentials and JWTs are therefore visible to
anyone who can sniff the lab LAN, and anyone on the LAN who reaches port 8000
can attempt logins. This is acceptable **only** in a trusted teaching lab.

To move beyond that:

1. **TLS termination** (nginx/caddy in front of Uvicorn):
   ```nginx
   server {
     listen 443 ssl;
     server_name cloud.lab.local;
     ssl_certificate     /etc/ssl/certs/cloud.lab.local.crt;
     ssl_certificate_key /etc/ssl/private/cloud.lab.local.key;
     client_max_body_size 20m;            # must exceed MAX_UPLOAD_BYTES
     location /api/ { proxy_pass http://127.0.0.1:8000; proxy_set_header X-Forwarded-For $remote_addr; }
     location /     { proxy_pass http://127.0.0.1:8000; }
   }
   ```
   Then keep Uvicorn on `127.0.0.1:8000` only.
2. Real certificates (internal CA or Let's Encrypt with DNS-01 for a
   `.lab.local` name).
3. Rate limiting at the proxy (`limit_req`) in addition to the in-process
   limiter, which is per-process and resets on restart.
4. Move the token out of `localStorage` (HttpOnly, SameSite=Secure cookies)
   for stronger XSS resistance.
5. Run Uvicorn under systemd with a dedicated unprivileged user:
   ```ini
   [Service]
   User=saascloud
   WorkingDirectory=/opt/lan-saas-cloud/cloud-controller
   EnvironmentFile=/opt/lan-saas-cloud/cloud-controller/.env
   ExecStart=/opt/lan-saas-cloud/cloud-controller/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
   Restart=on-failure
   ```
   (Note: multiple workers each keep their own rate-limit counters.)
6. Disable `/docs` and `/redoc` on a public deployment
   (`FastAPI(docs_url=None, redoc_url=None)` in `app/main.py`).

---

## 7. Exact startup order (checklist)

1. Start HDFS: `start-dfs.sh` (NameNode first, then DataNodes).
2. `hdfs dfsadmin -report` → DataNodes live.
3. `hdfs dfs -ls /saas-cloud` → app root exists, owned by `saascloud`.
4. Start the controller: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
5. `curl http://<server-ip>:8000/api/health` → `"healthy": true`.
6. Create the first admin: `python -m app.bootstrap_admin`.
7. Start/serve the frontend (5173 or the built SPA on 8000).
8. From another PC: `http://<server-ip>:8000` → register → upload → verify in HDFS.
