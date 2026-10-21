"""Validate the compose setup is internally consistent (no Docker needed).

Checks that the service names, environment variables and volumes referenced by
docker-compose.yml actually line up with the directories and Dockerfiles in the
repository. Run:  python docker/validate_compose.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required for this check: pip install pyyaml")
    raise SystemExit(3)

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {message}")
    if not condition:
        errors.append(message)


print("== files referenced by the compose file ==")
compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
services = compose["services"]

controller_build = services["controller"]["build"]
namenode_build = services["namenode"]["build"]

check((ROOT / controller_build["dockerfile"]).is_file(),
      f"controller Dockerfile exists: {controller_build['dockerfile']}")
check((ROOT / "cloud-controller/requirements.txt").is_file(),
      "cloud-controller/requirements.txt exists (copied by the Dockerfile)")
check((ROOT / "cloud-controller/app/main.py").is_file(),
      "cloud-controller/app/main.py exists")
check((ROOT / "frontend/package.json").is_file(), "frontend/package.json exists")
check((ROOT / "frontend/package-lock.json").is_file(),
      "frontend/package-lock.json exists (required by `npm ci`)")
check((ROOT / namenode_build["context"] / namenode_build["dockerfile"]).is_file(),
      "base-image Dockerfile exists")
check((ROOT / "cloud-controller/base-image/start-hdfs.sh").is_file(),
      "base-image/start-hdfs.sh exists")
check((ROOT / ".dockerignore").is_file(), "root .dockerignore exists")
check((ROOT / "docker/init-volumes.sh").is_file(), "docker/init-volumes.sh exists")

print("\n== compose service topology ==")
check(list(services) == ["volume-init", "namenode", "controller"],
      f"expected volume-init + namenode + controller services: {list(services)}")
check(services["namenode"]["depends_on"]["volume-init"]["condition"]
      == "service_completed_successfully",
      "namenode starts only after the volume ownership is prepared")
check(services["controller"]["depends_on"]["namenode"]["condition"]
      == "service_healthy",
      "controller waits for a healthy NameNode (avoids racing WebHDFS)")
check(services["namenode"]["healthcheck"]["test"][0] == "CMD-SHELL",
      "NameNode healthcheck is a shell command (uses curl over HTTP)")

print("\n== HDFS endpoint consistency ==")
env = services["controller"]["environment"]
check(env["HDFS_BASE_URL"] == "http://namenode:9870",
      "controller targets the NameNode by SERVICE NAME on the WebHDFS port")
check("namenode" in services, "the service name used in HDFS_BASE_URL exists")

# Every service that talks to another by DNS name must share a network.
# This was a REAL bug found by running the stack: the controller was left on the
# implicit "default" network while the NameNode sat on "cloudnet", so the host
# "namenode" failed to resolve with
#   [Errno -3] Temporary failure in name resolution
# and every WebHDFS call failed.
service_networks = {
    name: set(svc.get("networks", ["default"])) for name, svc in services.items()
}
check(service_networks["controller"] == service_networks["namenode"],
      "controller and namenode share a network "
      f"(controller={sorted(service_networks['controller'])}, "
      f"namenode={sorted(service_networks['namenode'])})")
check(service_networks["controller"] == service_networks["volume-init"],
      "volume-init shares the same network as the containers it prepares volumes for")
check(all("default" not in nets for nets in service_networks.values()),
      "no service silently falls back to the implicit default network")
check("cloudnet" in compose.get("networks", {}),
      "the named network used by the services is declared in the top-level block")

core_site = (ROOT / "cloud-controller/base-image/core-site.xml").read_text(encoding="utf-8")
hdfs_site = (ROOT / "cloud-controller/base-image/hdfs-site.xml").read_text(encoding="utf-8")
check("hdfs://namenode:8020" in core_site,
      "fs.defaultFS uses the same service name (no hardcoded IP)")
check("dfs.webhdfs.enabled" in hdfs_site and "<value>true</value>" in hdfs_site,
      "dfs.webhdfs.enabled=true (required, else every WebHDFS call is 403)")
check("0.0.0.0:9864" in hdfs_site,
      "DataNode HTTP bound on all interfaces so the 307 redirect target is reachable")
check("<value>1</value>" in hdfs_site and "dfs.replication" in hdfs_site,
      "dfs.replication=1 (honest single-DataNode lab value)")

print("\n== least-privilege / ownership ==")
dockerfile = (ROOT / "cloud-controller/Dockerfile").read_text(encoding="utf-8")
hadoop_dockerfile = (ROOT / "cloud-controller/base-image/Dockerfile").read_text(encoding="utf-8")
check("USER appuser" in dockerfile, "controller image runs as a non-root user")
check("useradd" in dockerfile, "controller creates a dedicated unprivileged account")
check("USER hadoop" in hadoop_dockerfile, "hadoop image runs as the unprivileged hadoop user")
init_vol = (ROOT / "docker/init-volumes.sh").read_text(encoding="utf-8")
check("1000:1000" in init_vol and "10001:10001" in init_vol,
      "named volumes are pre-owned with the UIDs the containers run as")

print("\n== secrets are not baked into images ==")
check(".env" in (ROOT / ".dockerignore").read_text(encoding="utf-8"),
      ".dockerignore excludes .env from the build context")
check("${JWT_SECRET" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8"),
      "JWT_SECRET is injected from the environment, not committed")
check("JWT_SECRET" not in dockerfile,
      "no secret is hardcoded in the controller Dockerfile")

print("\n== host port exposure (least exposure on a lab LAN) ==")
nn_ports = services["namenode"]["ports"]
check(all(p.startswith("127.0.0.1:") for p in nn_ports),
      f"NameNode/DataNode ports bound to localhost only: {nn_ports}")
check(any("8000" in p for p in services["controller"]["ports"]),
      "controller published on the LAN-facing port (container side is 8000)")

if errors:
    print(f"\n{len(errors)} CHECK(S) FAILED")
    sys.exit(1)
print("\nALL COMPOSE CONSISTENCY CHECKS PASSED")
