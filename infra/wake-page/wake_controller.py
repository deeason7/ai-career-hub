"""
wake_controller.py  —  Lambda for the "Wake on Visit" feature.

Fixes vs v1:
- Supports both HTTP API v2 (requestContext.http) and REST API (httpMethod) event shapes
- Health check hits EC2 by PUBLIC IP (not domain) so it works even when
  Route 53 is still routing to CloudFront during the failover window
- Handles all intermediate RDS states gracefully (starting, backing-up, etc.)
- Returns EC2 public IP so the frontend can show it in the status bar

Endpoints:
  GET  /status  →  { ec2, rds, app, ip }
  POST /wake    →  { message, ec2, rds }
"""

import json
import os
import urllib.request

import boto3

# ── Config (from Lambda env vars) ────────────────────────────────────────────
REGION       = os.environ.get("AWS_REGION_", "us-east-1")
EC2_TAG_NAME = os.environ.get("EC2_TAG_NAME", "portfolio-server")
RDS_ID       = os.environ.get("RDS_ID", "portfolio-db")
HEALTH_PORT  = os.environ.get("HEALTH_PORT", "80")   # hit EC2 directly on port 80

ec2 = boto3.client("ec2", region_name=REGION)
rds = boto3.client("rds", region_name=REGION)

CORS_HEADERS = {
    "Content-Type":                "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# RDS states that mean "it's still working on it"
RDS_TRANSITIONAL = {"starting", "stopping", "backing-up", "rebooting",
                     "modifying", "upgrading", "maintenance", "configuring-enhanced-monitoring"}


# ── Entry point ───────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    # Support both HTTP API v2 (requestContext.http) and REST API (httpMethod)
    rc   = event.get("requestContext", {})
    http = rc.get("http", {})
    method = (http.get("method") or event.get("httpMethod", "GET")).upper()
    path   = (http.get("path")   or event.get("rawPath") or event.get("path", "/status"))

    if method == "OPTIONS":
        return _resp(200, "")

    if method == "POST" and "wake" in path:
        return handle_wake()
    return handle_status()


# ── GET /status ───────────────────────────────────────────────────────────────
def handle_status():
    instance = _get_instance()
    ec2_state = instance["state"] if instance else "unknown"
    ec2_ip    = instance["ip"]    if instance else None

    rds_state = _get_rds_state()

    # App is healthy only when EC2 is running AND health endpoint responds
    app_state = "starting"
    if ec2_state == "running" and ec2_ip:
        app_state = "healthy" if _check_health(ec2_ip) else "starting"

    return _resp(200, {
        "ec2": ec2_state,
        "rds": rds_state,
        "app": app_state,
        "ip":  ec2_ip,
    })


# ── POST /wake ────────────────────────────────────────────────────────────────
def handle_wake():
    results = {"message": "Wake signal sent"}

    # ── EC2 ──
    try:
        instance = _get_instance()
        if instance and instance["state"] == "stopped":
            ec2.start_instances(InstanceIds=[instance["id"]])
            results["ec2"] = "starting"
        else:
            results["ec2"] = instance["state"] if instance else "unknown"
    except Exception as exc:
        results["ec2"] = f"error: {exc}"

    # ── RDS ──
    try:
        rds_state = _get_rds_state()
        if rds_state == "stopped":
            rds.start_db_instance(DBInstanceIdentifier=RDS_ID)
            results["rds"] = "starting"
        elif rds_state in RDS_TRANSITIONAL:
            results["rds"] = rds_state   # already waking, don't double-start
        else:
            results["rds"] = rds_state
    except Exception as exc:
        results["rds"] = f"error: {exc}"

    return _resp(202, results)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_instance():
    """Return {id, state, ip} for the tagged EC2, or None."""
    try:
        resp = ec2.describe_instances(
            Filters=[{"Name": "tag:Name", "Values": [EC2_TAG_NAME]}]
        )
        inst = resp["Reservations"][0]["Instances"][0]
        return {
            "id":    inst["InstanceId"],
            "state": inst["State"]["Name"],
            "ip":    inst.get("PublicIpAddress"),
        }
    except (IndexError, KeyError):
        return None


def _get_rds_state():
    try:
        resp = rds.describe_db_instances(DBInstanceIdentifier=RDS_ID)
        return resp["DBInstances"][0]["DBInstanceStatus"]
    except Exception:
        return "unknown"


def _check_health(ip: str) -> bool:
    """Check /health on the EC2 instance directly by IP (avoids DNS failover)."""
    url = f"http://{ip}:{HEALTH_PORT}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WakeController/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _resp(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body) if isinstance(body, dict) else body,
    }
