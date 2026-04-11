"""
wake_controller.py  —  Lambda for the "Wake on Visit" feature.

Changes vs v1:
- Supports both HTTP API v2 (requestContext.http) and REST API (httpMethod) event shapes
- Health check hits EC2 by PUBLIC IP (not domain) so it works even when
  Route 53 is still routing to CloudFront during the failover window
- Handles all intermediate RDS states gracefully (starting, backing-up, etc.)
- Returns EC2 public IP so the frontend can show it in the status bar
- AUTO-SLEEP: on every /wake call, schedules a one-time EventBridge Scheduler
  rule to stop EC2+RDS after AUTO_STOP_MINUTES (default 90 min). Each new
  wake call resets the timer. Zero manual action required.

Endpoints:
  GET  /status  →  { ec2, rds, app, ip }
  POST /wake    →  { message, ec2, rds }
  (internal)    →  invoked by EventBridge Scheduler with { "action": "stop" }
"""

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import boto3

# ── Config (from Lambda env vars) ────────────────────────────────────────────
REGION          = os.environ.get("AWS_REGION_", "us-east-1")
EC2_TAG_NAME    = os.environ.get("EC2_TAG_NAME", "portfolio-server")
RDS_ID          = os.environ.get("RDS_ID", "portfolio-db")
HEALTH_PORT     = os.environ.get("HEALTH_PORT", "80")
AUTO_STOP_MIN   = int(os.environ.get("AUTO_STOP_MINUTES", "90"))
LAMBDA_ARN      = os.environ.get("LAMBDA_ARN", "")          # own ARN for scheduler target
SCHEDULER_ROLE  = os.environ.get("SCHEDULER_ROLE_ARN", "")  # role that lets scheduler invoke us
SCHEDULE_NAME   = "portfolio-auto-stop"

ec2       = boto3.client("ec2",       region_name=REGION)
rds       = boto3.client("rds",       region_name=REGION)
scheduler = boto3.client("scheduler", region_name=REGION)

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
    # Internal call from EventBridge Scheduler (auto-stop timer)
    if event.get("action") == "stop":
        return handle_auto_stop()

    # Support both HTTP API v2 (requestContext.http) and REST API (httpMethod)
    rc     = event.get("requestContext", {})
    http   = rc.get("http", {})
    method = (http.get("method") or event.get("httpMethod", "GET")).upper()
    path   = (http.get("path")   or event.get("rawPath") or event.get("path", "/status"))

    if method == "OPTIONS":
        return _resp(200, "")

    if method == "POST" and "wake" in path:
        return handle_wake()
    return handle_status()


# ── GET /status ───────────────────────────────────────────────────────────────
def handle_status():
    # EC2 and RDS describe calls are independent — run in parallel to halve latency.
    # Serial took ~1-1.3s; parallel takes ~400ms (dominant call wins).
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_instance = pool.submit(_get_instance)
        f_rds      = pool.submit(_get_rds_state)
        instance   = f_instance.result()
        rds_state  = f_rds.result()

    ec2_state = instance["state"] if instance else "unknown"
    ec2_ip    = instance["ip"]    if instance else None

    # Health check runs AFTER EC2 result (needs the IP) — still sequential but now
    # only adds one extra call on top of the already-parallel EC2+RDS results.
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

    # ── Schedule auto-stop (reset timer on every wake call) ──
    _schedule_auto_stop()

    return _resp(202, results)


# ── AUTO-STOP (invoked by EventBridge Scheduler) ──────────────────────────────
def handle_auto_stop():
    """Stop EC2 + RDS. Called automatically after AUTO_STOP_MINUTES of uptime."""
    results = {}

    try:
        instance = _get_instance()
        if instance and instance["state"] == "running":
            ec2.stop_instances(InstanceIds=[instance["id"]])
            results["ec2"] = "stopping"
            print(f"[auto-stop] EC2 {instance['id']} stop signal sent")
        else:
            results["ec2"] = instance["state"] if instance else "unknown"
    except Exception as exc:
        results["ec2"] = f"error: {exc}"
        print(f"[auto-stop] EC2 error: {exc}")

    try:
        rds_state = _get_rds_state()
        if rds_state == "available":
            rds.stop_db_instance(DBInstanceIdentifier=RDS_ID)
            results["rds"] = "stopping"
            print(f"[auto-stop] RDS {RDS_ID} stop signal sent")
        else:
            results["rds"] = rds_state
    except Exception as exc:
        results["rds"] = f"error: {exc}"
        print(f"[auto-stop] RDS error: {exc}")

    return {"statusCode": 200, "body": json.dumps(results)}


# ── SCHEDULE AUTO-STOP ────────────────────────────────────────────────────────
def _schedule_auto_stop():
    """
    Create (or reset) a one-time EventBridge Scheduler rule that calls this
    Lambda with {"action": "stop"} after AUTO_STOP_MINUTES.

    Requires env vars: LAMBDA_ARN, SCHEDULER_ROLE_ARN
    """
    if not LAMBDA_ARN or not SCHEDULER_ROLE:
        print("[auto-stop] LAMBDA_ARN or SCHEDULER_ROLE_ARN not set — skipping")
        return

    stop_at  = datetime.now(timezone.utc) + timedelta(minutes=AUTO_STOP_MIN)
    at_expr  = f"at({stop_at.strftime('%Y-%m-%dT%H:%M:%S')})"

    # Delete existing schedule first (to reset the timer)
    try:
        scheduler.delete_schedule(Name=SCHEDULE_NAME)
        print(f"[auto-stop] previous schedule deleted")
    except scheduler.exceptions.ResourceNotFoundException:
        pass
    except Exception as exc:
        print(f"[auto-stop] delete schedule error: {exc}")

    # Create new one-time schedule
    try:
        scheduler.create_schedule(
            Name=SCHEDULE_NAME,
            ScheduleExpression=at_expr,
            ScheduleExpressionTimezone="UTC",
            Target={
                "Arn":    LAMBDA_ARN,
                "RoleArn": SCHEDULER_ROLE,
                "Input":  json.dumps({"action": "stop"}),
            },
            FlexibleTimeWindow={"Mode": "OFF"},
            ActionAfterCompletion="DELETE",   # self-deletes after firing
        )
        print(f"[auto-stop] scheduled at {stop_at.isoformat()} (in {AUTO_STOP_MIN} min)")
    except Exception as exc:
        print(f"[auto-stop] create schedule error: {exc}")


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
    """Check /health on the EC2 instance directly by IP (avoids DNS failover).

    timeout=3 (was 5): faster failure detection when EC2 is still booting.
    Each failed poll previously took the full 5s; 3s saves ~2s × 8 pre-healthy
    polls = ~16s of avoided waiting during the wake sequence.
    """
    url = f"http://{ip}:{HEALTH_PORT}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WakeController/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _resp(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body) if isinstance(body, dict) else body,
    }
