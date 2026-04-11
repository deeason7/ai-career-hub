#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#  setup-wake-on-visit.sh
#
#  One command that provisions the entire "Wake on Visit" infrastructure:
#
#    Phase 1 — S3 bucket (splash page host)
#    Phase 2 — IAM role + Lambda (wake controller)
#    Phase 3 — API Gateway HTTP API (/wake + /status)
#    Phase 4 — ACM certificate (DNS-validated via Route 53)
#    Phase 5 — CloudFront distribution (HTTPS entry point for the wake page)
#    Phase 6 — Route 53 health check + failover routing
#    Phase 7 — Patch & upload wake page to S3
#    Phase 8 — Summary
#
#  State is saved to infra/wake-page/.state after each phase so you can
#  safely re-run if anything fails — completed phases are skipped.
#
#  Usage:
#    bash infra/scripts/setup-wake-on-visit.sh          # full setup
#    bash infra/scripts/setup-wake-on-visit.sh --teardown  # remove everything
#
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WAKE_DIR="$REPO_ROOT/infra/wake-page"
STATE_FILE="$WAKE_DIR/.state"

# ── Constants ────────────────────────────────────────────────────────────────
REGION="us-east-1"
EC2_IP="34.234.125.14"
EC2_TAG="portfolio-server"
RDS_ID="portfolio-db"
DOMAIN="careerhub.deeason.com.np"
ZONE_ID="Z06577191HDSJ3IZ9HWWZ"
BUCKET="careerhub-wake-page"
LAMBDA_NAME="portfolio-wake-controller"
LAMBDA_ROLE="portfolio-wake-lambda-role"
API_NAME="portfolio-wake-api"
CF_COMMENT="careerhub-wake-page"
HC_NAME="portfolio-careerhub-ec2"
CLOUDFRONT_HOSTED_ZONE="Z2FDTNDATAQYW2"  # Global — same for all CloudFront

# ── Colors ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m' YELLOW='\033[1;33m' GREEN='\033[0;32m'
RED='\033[0;31m'  BOLD='\033[1m'      NC='\033[0m'
info()    { echo -e "\n${CYAN}[→]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1" >&2; }
phase()   { echo -e "\n${BOLD}${CYAN}━━━ Phase $1: $2 ━━━${NC}"; }

# ── State helpers ─────────────────────────────────────────────────────────────
state_get() { grep -E "^$1=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo ""; }
state_set() { 
  # Remove existing key then append
  local key=$1 val=$2
  grep -v "^${key}=" "$STATE_FILE" 2>/dev/null > "$STATE_FILE.tmp" || true
  echo "${key}=${val}" >> "$STATE_FILE.tmp"
  mv "$STATE_FILE.tmp" "$STATE_FILE"
}
phase_done() { [[ "$(state_get "phase_$1")" == "done" ]]; }
mark_done()  { state_set "phase_$1" "done"; }

# ── ACCOUNT_ID ───────────────────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# ════════════════════════════════════════════════════════════════════════════════
# TEARDOWN MODE
# ════════════════════════════════════════════════════════════════════════════════
if [[ "${1:-}" == "--teardown" ]]; then
  echo -e "\n${RED}${BOLD}⚠  Teardown: removing all wake-on-visit resources${NC}\n"

  CF_ID=$(state_get "cloudfront_id")
  HC_ID=$(state_get "health_check_id")
  API_ID=$(state_get "api_id")

  # 1. Restore simple Route 53 A record
  info "Restoring simple Route 53 A record..."
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch "{
      \"Changes\": [
        {\"Action\":\"DELETE\",\"ResourceRecordSet\":{\"Name\":\"${DOMAIN}.\",\"Type\":\"A\",\"SetIdentifier\":\"primary-ec2\",\"Failover\":\"PRIMARY\",\"TTL\":60,\"HealthCheckId\":\"${HC_ID}\",\"ResourceRecords\":[{\"Value\":\"${EC2_IP}\"}]}},
        {\"Action\":\"DELETE\",\"ResourceRecordSet\":{\"Name\":\"${DOMAIN}.\",\"Type\":\"A\",\"SetIdentifier\":\"secondary-cloudfront\",\"Failover\":\"SECONDARY\",\"AliasTarget\":{\"DNSName\":\"$(state_get cloudfront_domain)\",\"EvaluateTargetHealth\":false,\"HostedZoneId\":\"${CLOUDFRONT_HOSTED_ZONE}\"}}},
        {\"Action\":\"CREATE\",\"ResourceRecordSet\":{\"Name\":\"${DOMAIN}.\",\"Type\":\"A\",\"TTL\":300,\"ResourceRecords\":[{\"Value\":\"${EC2_IP}\"}]}}
      ]
    }" --region "$REGION" > /dev/null 2>&1 || warn "Route 53 restore failed — may need manual cleanup."

  # 2. Disable then delete CloudFront
  if [[ -n "$CF_ID" ]]; then
    info "Disabling CloudFront distribution $CF_ID..."
    ETAG=$(aws cloudfront get-distribution-config --id "$CF_ID" --query ETag --output text 2>/dev/null || echo "")
    if [[ -n "$ETAG" ]]; then
      aws cloudfront get-distribution-config --id "$CF_ID" --query DistributionConfig \
        | python3 -c "import sys,json; d=json.load(sys.stdin); d['Enabled']=False; print(json.dumps(d))" \
        > /tmp/cf-disabled.json
      aws cloudfront update-distribution --id "$CF_ID" --if-match "$ETAG" \
        --distribution-config file:///tmp/cf-disabled.json > /dev/null 2>&1 || true
      warn "CloudFront disabled. It takes 5-15 min to fully deploy; delete it manually in the console after."
    fi
  fi

  # 3. Delete health check
  [[ -n "$HC_ID" ]] && aws route53 delete-health-check --health-check-id "$HC_ID" 2>/dev/null || true && success "Health check deleted."

  # 4. Delete API Gateway
  [[ -n "$API_ID" ]] && aws apigatewayv2 delete-api --api-id "$API_ID" --region "$REGION" 2>/dev/null || true && success "API Gateway deleted."

  # 5. Delete Lambda
  aws lambda delete-function --function-name "$LAMBDA_NAME" --region "$REGION" 2>/dev/null || true && success "Lambda deleted."

  # 6. Delete Lambda role
  aws iam detach-role-policy --role-name "$LAMBDA_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
  aws iam delete-role-policy --role-name "$LAMBDA_ROLE" --policy-name wake-ec2-rds-policy 2>/dev/null || true
  aws iam delete-role --role-name "$LAMBDA_ROLE" 2>/dev/null || true && success "IAM role deleted."

  # 7. Empty and delete S3 bucket
  aws s3 rm "s3://$BUCKET" --recursive --region "$REGION" 2>/dev/null || true
  aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null || true && success "S3 bucket deleted."

  # 8. Clean state
  rm -f "$STATE_FILE"
  echo -e "\n${GREEN}✅ Teardown complete.${NC}\n"
  exit 0
fi

# ════════════════════════════════════════════════════════════════════════════════
# SETUP
# ════════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}   Wake on Visit — Full Setup${NC}"
echo -e "${BOLD}${CYAN}   Domain : $DOMAIN${NC}"
echo -e "${BOLD}${CYAN}   EC2 IP : $EC2_IP${NC}"
echo -e "${BOLD}${CYAN}   Region : $REGION${NC}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${NC}"

# Pre-flight: check required tools
for tool in aws python3 zip; do
  command -v "$tool" &>/dev/null || { error "Missing required tool: $tool"; exit 1; }
done

mkdir -p "$WAKE_DIR"
touch "$STATE_FILE"

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 1 — S3 BUCKET
# ════════════════════════════════════════════════════════════════════════════════
phase 1 "S3 Bucket"

if phase_done 1; then
  success "S3 bucket already set up — skipping."
else
  # Create bucket (us-east-1 doesn't use LocationConstraint)
  if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
    success "Bucket $BUCKET already exists."
  else
    info "Creating S3 bucket: $BUCKET ..."
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" > /dev/null
    success "Bucket created."
  fi

  # Allow public access (it's just a splash page)
  info "Configuring public access..."
  aws s3api put-public-access-block --bucket "$BUCKET" \
    --public-access-block-configuration \
      "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

  aws s3api put-bucket-website --bucket "$BUCKET" \
    --website-configuration '{"IndexDocument":{"Suffix":"index.html"},"ErrorDocument":{"Key":"index.html"}}'

  aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[{
      \"Effect\":\"Allow\",
      \"Principal\":\"*\",
      \"Action\":\"s3:GetObject\",
      \"Resource\":\"arn:aws:s3:::${BUCKET}/*\"
    }]
  }"

  S3_WEBSITE="http://${BUCKET}.s3-website-${REGION}.amazonaws.com"
  state_set "s3_website" "$S3_WEBSITE"
  mark_done 1
  success "S3 bucket ready. Website endpoint: $S3_WEBSITE"
fi

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 2 — IAM ROLE + LAMBDA
# ════════════════════════════════════════════════════════════════════════════════
phase 2 "IAM Role + Lambda"

if phase_done 2; then
  success "Lambda already deployed — skipping."
  LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_NAME}"
else
  # IAM Role
  if aws iam get-role --role-name "$LAMBDA_ROLE" 2>/dev/null | grep -q RoleId; then
    success "IAM role $LAMBDA_ROLE already exists."
  else
    info "Creating IAM role $LAMBDA_ROLE ..."
    aws iam create-role --role-name "$LAMBDA_ROLE" \
      --assume-role-policy-document '{
        "Version":"2012-10-17",
        "Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]
      }' > /dev/null
    aws iam attach-role-policy --role-name "$LAMBDA_ROLE" \
      --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    aws iam put-role-policy --role-name "$LAMBDA_ROLE" \
      --policy-name wake-ec2-rds-policy \
      --policy-document '{
        "Version":"2012-10-17",
        "Statement":[{
          "Effect":"Allow",
          "Action":[
            "ec2:DescribeInstances","ec2:StartInstances","ec2:StopInstances",
            "rds:DescribeDBInstances","rds:StartDBInstance","rds:StopDBInstance"
          ],
          "Resource":"*"
        }]
      }'
    success "IAM role created. Waiting 12s for IAM propagation..."
    sleep 12
  fi

  ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE}"

  # Package Lambda
  info "Packaging Lambda..."
  cd "$WAKE_DIR"
  zip -q wake_controller.zip wake_controller.py
  cd "$REPO_ROOT"

  ENV_VARS="Variables={AWS_REGION_=$REGION,EC2_TAG_NAME=$EC2_TAG,RDS_ID=$RDS_ID,HEALTH_PORT=80}"

  if aws lambda get-function --function-name "$LAMBDA_NAME" --region "$REGION" 2>/dev/null | grep -q FunctionArn; then
    info "Updating existing Lambda $LAMBDA_NAME ..."
    aws lambda update-function-code \
      --function-name "$LAMBDA_NAME" \
      --zip-file "fileb://$WAKE_DIR/wake_controller.zip" \
      --region "$REGION" > /dev/null
    aws lambda update-function-configuration \
      --function-name "$LAMBDA_NAME" \
      --timeout 30 \
      --environment "$ENV_VARS" \
      --region "$REGION" > /dev/null
  else
    info "Creating Lambda $LAMBDA_NAME ..."
    aws lambda create-function \
      --function-name "$LAMBDA_NAME" \
      --runtime python3.12 \
      --handler wake_controller.lambda_handler \
      --role "$ROLE_ARN" \
      --zip-file "fileb://$WAKE_DIR/wake_controller.zip" \
      --timeout 30 \
      --environment "$ENV_VARS" \
      --region "$REGION" > /dev/null
  fi

  LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_NAME}"
  state_set "lambda_arn" "$LAMBDA_ARN"
  mark_done 2
  success "Lambda deployed: $LAMBDA_ARN"
fi

LAMBDA_ARN=$(state_get "lambda_arn" || echo "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_NAME}")

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 3 — API GATEWAY HTTP API
# ════════════════════════════════════════════════════════════════════════════════
phase 3 "API Gateway HTTP API"

if phase_done 3; then
  success "API Gateway already set up — skipping."
  API_ID=$(state_get "api_id")
  API_URL=$(state_get "api_url")
else
  if API_ID=$(aws apigatewayv2 get-apis --region "$REGION" \
      --query "Items[?Name=='$API_NAME'].ApiId" --output text 2>/dev/null) && [[ -n "$API_ID" && "$API_ID" != "None" ]]; then
    success "API $API_NAME already exists ($API_ID)."
  else
    info "Creating HTTP API $API_NAME ..."
    API_ID=$(aws apigatewayv2 create-api \
      --name "$API_NAME" \
      --protocol-type HTTP \
      --cors-configuration "AllowOrigins=[\"*\"],AllowMethods=[\"GET\",\"POST\",\"OPTIONS\"],AllowHeaders=[\"content-type\"]" \
      --region "$REGION" \
      --query ApiId --output text)
    success "API created: $API_ID"
  fi

  # Lambda integration
  info "Creating Lambda integration..."
  INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id "$API_ID" \
    --integration-type AWS_PROXY \
    --integration-uri "$LAMBDA_ARN" \
    --payload-format-version "2.0" \
    --region "$REGION" \
    --query IntegrationId --output text)

  # Routes
  for ROUTE in "POST /wake" "GET /status" "OPTIONS /wake" "OPTIONS /status"; do
    aws apigatewayv2 create-route --api-id "$API_ID" \
      --route-key "$ROUTE" --target "integrations/$INTEGRATION_ID" \
      --region "$REGION" > /dev/null 2>&1 || true
  done

  # Deploy stage
  aws apigatewayv2 create-stage --api-id "$API_ID" \
    --stage-name prod --auto-deploy --region "$REGION" > /dev/null 2>&1 || true

  # Allow API Gateway to invoke Lambda
  aws lambda add-permission \
    --function-name "$LAMBDA_NAME" \
    --statement-id "AllowAPIGateway-${API_ID}" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*/*" \
    --region "$REGION" > /dev/null 2>&1 || true

  API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod"
  state_set "api_id"  "$API_ID"
  state_set "api_url" "$API_URL"
  mark_done 3
  success "API Gateway ready: $API_URL"
fi

API_ID=$(state_get "api_id")
API_URL=$(state_get "api_url")

# Quick smoke test
echo ""
info "Smoke-testing API Gateway /status ..."
sleep 2
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/status" 2>/dev/null || echo "000")
if [[ "$HTTP" == "200" ]]; then
  success "API /status responded 200 ✓"
else
  warn "API returned $HTTP — may need a few seconds to warm up. Continuing..."
fi

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 4 — ACM CERTIFICATE (required for CloudFront HTTPS)
# ════════════════════════════════════════════════════════════════════════════════
phase 4 "ACM Certificate (us-east-1, DNS validated)"

if phase_done 4; then
  success "ACM certificate already validated — skipping."
  CERT_ARN=$(state_get "cert_arn")
else
  # Check for existing valid cert
  CERT_ARN=$(aws acm list-certificates --region "$REGION" \
    --query "CertificateSummaryList[?DomainName=='$DOMAIN' && Status=='ISSUED'].CertificateArn" \
    --output text 2>/dev/null || echo "")

  if [[ -n "$CERT_ARN" && "$CERT_ARN" != "None" ]]; then
    success "Existing issued cert found: $CERT_ARN"
  else
    # Check for PENDING cert
    PENDING_ARN=$(aws acm list-certificates --region "$REGION" \
      --query "CertificateSummaryList[?DomainName=='$DOMAIN' && Status=='PENDING_VALIDATION'].CertificateArn" \
      --output text 2>/dev/null || echo "")

    if [[ -z "$PENDING_ARN" || "$PENDING_ARN" == "None" ]]; then
      info "Requesting ACM certificate for $DOMAIN ..."
      PENDING_ARN=$(aws acm request-certificate \
        --domain-name "$DOMAIN" \
        --validation-method DNS \
        --region "$REGION" \
        --query CertificateArn --output text)
      success "Certificate requested: $PENDING_ARN"
      sleep 5   # Give ACM time to generate validation records
    else
      success "Pending cert already exists: $PENDING_ARN"
    fi

    # Add DNS validation record to Route 53 automatically
    info "Fetching DNS validation record from ACM..."
    for i in {1..10}; do
      CNAME_RECORD=$(aws acm describe-certificate \
        --certificate-arn "$PENDING_ARN" --region "$REGION" \
        --query "Certificate.DomainValidationOptions[0].ResourceRecord" \
        --output json 2>/dev/null || echo "null")
      if [[ "$CNAME_RECORD" != "null" && "$CNAME_RECORD" != "" ]]; then break; fi
      echo "  Waiting for ACM to generate validation record ($i/10)..."
      sleep 5
    done

    CNAME_NAME=$(echo "$CNAME_RECORD" | python3 -c "import sys,json; print(json.load(sys.stdin)['Name'])")
    CNAME_VALUE=$(echo "$CNAME_RECORD" | python3 -c "import sys,json; print(json.load(sys.stdin)['Value'])")

    info "Adding DNS validation CNAME to Route 53..."
    aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
      --change-batch "{
        \"Changes\":[{
          \"Action\":\"UPSERT\",
          \"ResourceRecordSet\":{
            \"Name\":\"$CNAME_NAME\",
            \"Type\":\"CNAME\",
            \"TTL\":300,
            \"ResourceRecords\":[{\"Value\":\"$CNAME_VALUE\"}]
          }
        }]
      }" > /dev/null
    success "DNS validation record added."

    info "Waiting for ACM certificate to be issued (usually 1-3 min)..."
    aws acm wait certificate-validated --certificate-arn "$PENDING_ARN" --region "$REGION"
    CERT_ARN="$PENDING_ARN"
    success "Certificate issued! ✓"
  fi

  state_set "cert_arn" "$CERT_ARN"
  mark_done 4
  success "ACM cert ready: $CERT_ARN"
fi

CERT_ARN=$(state_get "cert_arn")

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 5 — CLOUDFRONT DISTRIBUTION
# ════════════════════════════════════════════════════════════════════════════════
phase 5 "CloudFront Distribution (takes 10-15 min to deploy)"

if phase_done 5; then
  success "CloudFront already deployed — skipping."
  CF_ID=$(state_get "cloudfront_id")
  CF_DOMAIN=$(state_get "cloudfront_domain")
else
  # Check existing
  CF_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment=='$CF_COMMENT'].Id" \
    --output text 2>/dev/null || echo "")

  if [[ -n "$CF_ID" && "$CF_ID" != "None" ]]; then
    CF_DOMAIN=$(aws cloudfront get-distribution --id "$CF_ID" \
      --query "Distribution.DomainName" --output text)
    success "CloudFront distribution $CF_ID already exists."
  else
    S3_ORIGIN="${BUCKET}.s3-website-${REGION}.amazonaws.com"

    info "Creating CloudFront distribution... (this takes 10-15 minutes)"
    CF_CONFIG=$(cat <<EOF
{
  "Comment": "${CF_COMMENT}",
  "Origins": {
    "Quantity": 1,
    "Items": [{
      "Id": "S3-wake-page",
      "DomainName": "${S3_ORIGIN}",
      "CustomOriginConfig": {
        "HTTPPort": 80,
        "HTTPSPort": 443,
        "OriginProtocolPolicy": "http-only"
      }
    }]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "S3-wake-page",
    "ViewerProtocolPolicy": "redirect-to-https",
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "AllowedMethods": {"Quantity":2,"Items":["GET","HEAD"],"CachedMethods":{"Quantity":2,"Items":["GET","HEAD"]}},
    "Compress": true
  },
  "Aliases": {"Quantity":1,"Items":["${DOMAIN}"]},
  "ViewerCertificate": {
    "ACMCertificateArn": "${CERT_ARN}",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021"
  },
  "Enabled": true,
  "HttpVersion": "http2",
  "PriceClass": "PriceClass_100",
  "DefaultRootObject": "index.html",
  "CustomErrorResponses": {
    "Quantity": 1,
    "Items": [{"ErrorCode":403,"ResponseCode":"200","ResponsePagePath":"/index.html","ErrorCachingMinTTL":0}]
  },
  "CallerReference": "careerhub-wake-$(date +%s)"
}
EOF
)

    CF_RESULT=$(aws cloudfront create-distribution \
      --distribution-config "$CF_CONFIG" \
      --query "[Distribution.Id,Distribution.DomainName]" \
      --output text)

    CF_ID=$(echo "$CF_RESULT" | awk '{print $1}')
    CF_DOMAIN=$(echo "$CF_RESULT" | awk '{print $2}')
    success "CloudFront distribution created: $CF_ID"
    echo "  Domain: $CF_DOMAIN"

    info "Waiting for CloudFront to deploy (≈10-15 min)..."
    aws cloudfront wait distribution-deployed --id "$CF_ID"
    success "CloudFront deployed! ✓"
  fi

  state_set "cloudfront_id"     "$CF_ID"
  state_set "cloudfront_domain" "$CF_DOMAIN"
  mark_done 5
  success "CloudFront ready: https://$CF_DOMAIN"
fi

CF_ID=$(state_get "cloudfront_id")
CF_DOMAIN=$(state_get "cloudfront_domain")

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 6 — ROUTE 53: HEALTH CHECK + FAILOVER ROUTING
# ════════════════════════════════════════════════════════════════════════════════
phase 6 "Route 53 Health Check + Failover Records"

if phase_done 6; then
  success "Route 53 failover already configured — skipping."
  HC_ID=$(state_get "health_check_id")
else
  # Create health check on EC2
  EXISTING_HC=$(aws route53 list-health-checks \
    --query "HealthChecks[?HealthCheckConfig.FullyQualifiedDomainName=='$EC2_IP' && HealthCheckConfig.Port==\`80\`].Id" \
    --output text 2>/dev/null || echo "")

  if [[ -n "$EXISTING_HC" && "$EXISTING_HC" != "None" ]]; then
    HC_ID="$EXISTING_HC"
    success "Health check already exists: $HC_ID"
  else
    info "Creating Route 53 health check on $EC2_IP:80/health ..."
    HC_CONFIG="{
      \"IPAddress\":\"${EC2_IP}\",
      \"Port\":80,
      \"Type\":\"HTTP\",
      \"ResourcePath\":\"/health\",
      \"RequestInterval\":30,
      \"FailureThreshold\":2,
      \"EnableSNI\":false
    }"
    HC_ID=$(aws route53 create-health-check \
      --caller-reference "careerhub-ec2-$(date +%s)" \
      --health-check-config "$HC_CONFIG" \
      --query HealthCheck.Id --output text)
    # Tag for easy identification
    aws route53 change-tags-for-resource \
      --resource-type healthcheck --resource-id "$HC_ID" \
      --add-tags "Key=Name,Value=${HC_NAME}" > /dev/null
    success "Health check created: $HC_ID"
  fi

  state_set "health_check_id" "$HC_ID"

  # Convert existing simple A record → failover routing
  info "Updating Route 53 records to failover routing..."
  info "  Deleting simple A record for $DOMAIN ..."
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch "{
      \"Changes\":[{
        \"Action\":\"DELETE\",
        \"ResourceRecordSet\":{
          \"Name\":\"${DOMAIN}.\",
          \"Type\":\"A\",
          \"TTL\":300,
          \"ResourceRecords\":[{\"Value\":\"${EC2_IP}\"}]
        }
      }]
    }" > /dev/null

  info "  Creating PRIMARY failover record (EC2 with health check)..."
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch "{
      \"Changes\":[{
        \"Action\":\"CREATE\",
        \"ResourceRecordSet\":{
          \"Name\":\"${DOMAIN}.\",
          \"Type\":\"A\",
          \"SetIdentifier\":\"primary-ec2\",
          \"Failover\":\"PRIMARY\",
          \"TTL\":60,
          \"HealthCheckId\":\"${HC_ID}\",
          \"ResourceRecords\":[{\"Value\":\"${EC2_IP}\"}]
        }
      }]
    }" > /dev/null

  info "  Creating SECONDARY failover record (CloudFront wake page)..."
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch "{
      \"Changes\":[{
        \"Action\":\"CREATE\",
        \"ResourceRecordSet\":{
          \"Name\":\"${DOMAIN}.\",
          \"Type\":\"A\",
          \"SetIdentifier\":\"secondary-cloudfront\",
          \"Failover\":\"SECONDARY\",
          \"AliasTarget\":{
            \"DNSName\":\"${CF_DOMAIN}\",
            \"EvaluateTargetHealth\":false,
            \"HostedZoneId\":\"${CLOUDFRONT_HOSTED_ZONE}\"
          }
        }
      }]
    }" > /dev/null

  mark_done 6
  success "Route 53 failover routing configured."
  echo ""
  echo -e "  ${CYAN}How it works now:${NC}"
  echo -e "  ${GREEN}EC2 running${NC}   → Route 53 health check passes → traffic → EC2 (real app)"
  echo -e "  ${YELLOW}EC2 stopped${NC}  → Route 53 health check fails  → traffic → CloudFront → S3 wake page"
fi

HC_ID=$(state_get "health_check_id")

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 7 — PATCH WAKE PAGE + UPLOAD TO S3
# ════════════════════════════════════════════════════════════════════════════════
phase 7 "Patch wake page with API URL + upload to S3"

if phase_done 7; then
  success "Wake page already uploaded — skipping."
  warn "If you changed index.html manually, run: aws s3 cp infra/wake-page/index.html s3://$BUCKET/index.html --content-type text/html --region $REGION"
else
  API_URL=$(state_get "api_url")
  WAKE_HTML="$WAKE_DIR/index.html"

  if [[ ! -f "$WAKE_HTML" ]]; then
    error "infra/wake-page/index.html not found! Run from the repo root."
    exit 1
  fi

  info "Injecting API Gateway URL into index.html..."
  # Replace the placeholder URL
  sed -i.bak "s|https://YOUR_API_GATEWAY_ID\.execute-api\.us-east-1\.amazonaws\.com/prod|${API_URL}|g" "$WAKE_HTML"
  rm -f "${WAKE_HTML}.bak"
  success "API URL injected: $API_URL"

  info "Uploading index.html to s3://$BUCKET ..."
  aws s3 cp "$WAKE_HTML" "s3://$BUCKET/index.html" \
    --content-type "text/html" \
    --cache-control "no-cache, no-store, must-revalidate" \
    --region "$REGION"
  success "Wake page uploaded."

  mark_done 7
fi

# ════════════════════════════════════════════════════════════════════════════════
# PHASE 8 — SUMMARY
# ════════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  ✅  Wake on Visit — Setup Complete!${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Domain${NC}          : https://${DOMAIN}"
echo -e "  ${BOLD}CloudFront${NC}      : https://$(state_get cloudfront_domain)"
echo -e "  ${BOLD}API Gateway${NC}     : $(state_get api_url)"
echo -e "  ${BOLD}Lambda${NC}          : ${LAMBDA_NAME}"
echo -e "  ${BOLD}S3 bucket${NC}       : s3://${BUCKET}"
echo -e "  ${BOLD}HC (health check)${NC}: $(state_get health_check_id)"
echo ""
echo -e "  ${BOLD}${CYAN}Estimated monthly cost:${NC}"
echo -e "    Lambda + API GW + S3 + CloudFront : ~\$0.00  (free tier)"
echo -e "    Route 53 health check             : ~\$0.50/month"
echo -e "    EC2 + RDS (only when a recruiter visits) : ~\$0.10–0.50"
echo -e "    ${BOLD}Total                             : ~\$1–2/month${NC}"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "    1. ${YELLOW}Stop EC2 + RDS now:${NC}  bash infra/scripts/stop.sh"
echo -e "    2. ${YELLOW}Test the wake page:${NC}   open https://${DOMAIN}"
echo -e "    3. ${YELLOW}Watch the magic:${NC}      click 'Wake Up the App' on the page"
echo ""
echo -e "  ${BOLD}To update the wake page:${NC}"
echo -e "    Edit infra/wake-page/index.html, then:"
echo -e "    aws s3 cp infra/wake-page/index.html s3://${BUCKET}/index.html --content-type text/html --region ${REGION}"
echo ""
echo -e "  ${BOLD}To undo everything:${NC}"
echo -e "    bash infra/scripts/setup-wake-on-visit.sh --teardown"
echo ""
