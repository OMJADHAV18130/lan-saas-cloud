# ---------------------------------------------------------------------------
# HDFS NameNode + DataNode image (authoritative: Apache Hadoop 3.4.1).
#
# base-image/Dockerfile builds a local image that derives the official
# apache/hadoop image with:
#   * our WebHDFS-enabled configuration
#   * an entrypoint that formats the NameNode once and starts both daemons
#   * the least-privilege 'saascloud' service identity and /saas-cloud root
#
# Build:  docker build -t lan-saas-hadoop:3.4.1 base-image/
# ---------------------------------------------------------------------------
FROM apache/hadoop:3.4.1

USER root

ENV HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop \
    JAVA_HOME=/usr/lib/jvm/jre

COPY hdfs-site.xml core-site.xml ${HADOOP_CONF_DIR}/
COPY start-hdfs.sh /usr/local/bin/start-hdfs.sh
RUN chmod +x /usr/local/bin/start-hdfs.sh \
    && chown -R hadoop:hadoop ${HADOOP_HOME}/etc/hadoop

# NameNode RPC, NameNode HTTP (WebHDFS UI/API), DataNode HTTP, DataNode data
EXPOSE 8020 9870 9864 9866

# HDFS state must be on volumes: the container runs as the unprivileged
# 'hadoop' user and cannot write to its own root filesystem. These paths are
# mounted as named volumes by docker-compose.yml, where the 'volume-init'
# service sets the correct ownership before this container starts.
VOLUME ["/hadoop/dfs/name", "/hadoop/dfs/data", "/hadoop/tmp"]

# Run everything as the unprivileged hadoop user from the official image.
USER hadoop

ENTRYPOINT ["/usr/local/bin/start-hdfs.sh"]
