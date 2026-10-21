# Hadoop configuration templates

These two files are **pure XML templates** so you can copy the
`<configuration>` block straight into `$HADOOP_HOME/etc/hadoop/`.

| File | Where it goes |
|---|---|
| `core-site.xml.example` | `$HADOOP_HOME/etc/hadoop/core-site.xml` — every node |
| `hdfs-site.xml.example` | `$HADOOP_HOME/etc/hadoop/hdfs-site.xml` — every node |

## Required Hadoop settings (why each one matters)

| Property | Value | Why |
|---|---|---|
| `dfs.webhdfs.enabled` | `true` | **Without this the whole project cannot work.** The Cloud Controller uses only the WebHDFS REST API. |
| `fs.defaultFS` | `hdfs://<namenode>:8020` | Tells every client where the NameNode RPC lives. |
| `dfs.namenode.http-address` | `<namenode>:9870` | WebHDFS is served from the NameNode **HTTP** port (9870 in Hadoop 3.x). |
| `dfs.replication` | `1` (1-node lab) | Set honestly. See "Replication" below. |
| `dfs.permissions.enabled` | `true` | Keeps the least-privilege model meaningful. |
| `dfs.datanode.address/http/ipc` | `9866 / 9864 / 9867` | After the 307 redirect the **controller** must reach a DataNode on these ports. |

## LAN host resolution

WebHDFS performs a two-step protocol:

```
Cloud Controller --PUT op=CREATE--> NameNode :9870
Cloud Controller <--307 Location: http://<datanode>:9864/...--
Cloud Controller --PUT bytes------> DataNode :9864
```

Two consequences for the lab LAN:

1. **The NameNode hostname in `core-site.xml` must resolve on every machine**
   (and from inside containers). Use `/etc/hosts` if the lab has no DNS:

   ```
   192.168.1.20   nn.lab.local   namenode
   192.168.1.21   dn1.lab.local  datanode1
   192.168.1.22   dn2.lab.local  datanode2
   ```

2. **The `Location` header returned to the controller contains a DataNode
   address derived from `dfs.datanode.http.address`** and Hadoop's own
   hostname resolution. The controller machine must be able to resolve *and*
   reach that address. If the redirect points at a hostname your controller
   cannot resolve, uploads fail with "DataNode could not be reached".
   Check with:
   ```bash
   curl -i -X PUT "http://nn.lab.local:9870/webhdfs/v1/test?op=CREATE&user.name=saascloud&overwrite=true"
   # inspect the Location: header
   ```

## Replication — what this lab can and cannot show

* `dfs.replication` is the **configured** target, not a guarantee.
* A cluster with **one DataNode** stores **one physical copy** even if the
  factor is 3 (Hadoop waits for the missing replicas and reports
  `replication` = 1 or under-replicated blocks).
* **Do not claim fault tolerance or replication just because several
  computers exist.** Verify what is actually stored:

  ```bash
  hdfs fsck /saas-cloud/users/<user_id>/<file_id> -files -blocks -locations
  ```
  The `-locations` output lists the physical block locations (one line per
  live replica). `hdfs dfsadmin -report` also shows
  `Live datanode(s)` and `Under-replicated blocks`.

* A single machine or single DataNode setup is a **development
  configuration**, not a resilient production cluster.

## One-time identity and directory bootstrap

```bash
sudo useradd -r -m -s /usr/sbin/nologin saascloud   # least-privilege identity
sudo -u hdfs hdfs dfs -mkdir -p /saas-cloud
sudo -u hdfs hdfs dfs -chown saascloud:supergroup /saas-cloud
sudo -u hdfs hdfs dfs -chmod 0750 /saas-cloud
sudo -u hdfs hdfs dfs -ls -ld /saas-cloud
```

The controller then creates `/saas-cloud/users/<uuid>/` (0750) and object
files (0640) itself, as `saascloud`, through WebHDFS `MKDIRS` / `CREATE`.
