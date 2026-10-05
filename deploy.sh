#!/usr/bin/env bash
# deploy.sh — Deploy pubmed-mcp to Google Cloud Run
#
# Prerequisites:
#   1. Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install
#   2. Authenticate: gcloud auth login
#   3. Create a project: gcloud projects create YOUR_PROJECT_ID
#   4. Enable billing on the project (free tier covers 2M requests/month)
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                          # uses defaults
#   ./deploy.sh my-project us-central1   # explicit project & region
#
# After deploy, your MCP endpoint will be:
#   https://pubmed-mcp-HASH-REGION.a.run.app/mcp
#
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-us-central1}"
SERVICE_NAME="pubmed-mcp"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Deploying ${SERVICE_NAME} to Cloud Run${NC}"
echo -e "${CYAN}  Project:  ${PROJECT_ID}${NC}"
echo -e "${CYAN}  Region:   ${REGION}${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"

# ── Step 1: Enable required APIs ─────────────────────────────
echo -e "\n${GREEN}[1/4] Enabling Cloud Run & Artifact Registry APIs...${NC}"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  --project="${PROJECT_ID}" --quiet

# ── Step 2: Build container image ────────────────────────────
echo -e "\n${GREEN}[2/4] Building container image with Cloud Build...${NC}"
gcloud builds submit --tag "${IMAGE}" --project="${PROJECT_ID}" --quiet

# ── Step 3: Deploy to Cloud Run ──────────────────────────────
echo -e "\n${GREEN}[3/4] Deploying to Cloud Run...${NC}"
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300 \
  --set-env-vars="MCP_TRANSPORT=streamable-http" \
  --set-env-vars="NCBI_EMAIL=${NCBI_EMAIL:-}" \
  --set-env-vars="UNPAYWALL_EMAIL=${UNPAYWALL_EMAIL:-}" \
  --set-env-vars="NCBI_API_KEY=${NCBI_API_KEY:-}" \
  --quiet

# ── Step 4: Print the URL ────────────────────────────────────
echo -e "\n${GREEN}[4/4] Fetching service URL...${NC}"
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo -e "\n${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Deployed successfully!${NC}"
echo -e ""
echo -e "  Service URL:  ${SERVICE_URL}"
echo -e "  MCP Endpoint: ${SERVICE_URL}/mcp"
echo -e ""
echo -e "  ${CYAN}Remote MCP client config:${NC}"
echo -e "  {"
echo -e "    \"mcpServers\": {"
echo -e "      \"pubmed-scraper\": {"
echo -e "        \"url\": \"${SERVICE_URL}/mcp\""
echo -e "      }"
echo -e "    }"
echo -e "  }"
echo -e ""
echo -e "  ${CYAN}OpenCode config:${NC}"
echo -e "  {"
echo -e "    \"mcp\": {"
echo -e "      \"pubmed-scraper\": {"
echo -e "        \"type\": \"remote\","
echo -e "        \"url\": \"${SERVICE_URL}/mcp\""
echo -e "      }"
echo -e "    }"
echo -e "  }"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
