#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE="localhost:32000/quilly-support:latest"
NAMESPACE="quilly-support"
APP_DEPLOYMENT="quilly-support"
SEED_JOB="seed-documents"
FORCE_SEED_DOCS="${FORCE_SEED_DOCS:-false}"
SKIP_BUILD="${SKIP_BUILD:-false}"
BUILD_NO_CACHE="${BUILD_NO_CACHE:-false}"
SKIP_ADDONS="${SKIP_ADDONS:-false}"
FORCE_ROLLOUT_RESTART="${FORCE_ROLLOUT_RESTART:-true}"
ENABLE_HTTPS_LETSENCRYPT="${ENABLE_HTTPS_LETSENCRYPT:-false}"
ENABLE_HTTPS_SELFSIGNED="${ENABLE_HTTPS_SELFSIGNED:-false}"
APP_DOMAIN="${APP_DOMAIN:-}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
LETSENCRYPT_STAGING="${LETSENCRYPT_STAGING:-false}"
LETSENCRYPT_ISSUER_NAME="${LETSENCRYPT_ISSUER_NAME:-}"
TLS_SECRET_NAME="${TLS_SECRET_NAME:-quilly-support-tls}"
SELF_SIGNED_CERT_DAYS="${SELF_SIGNED_CERT_DAYS:-365}"

ensure_addon() {
  local addon="$1"
  if microk8s status --wait-ready 2>/dev/null | grep -qE "^[[:space:]]*${addon}:[[:space:]]+enabled$"; then
    echo ">>> Addon '${addon}' already enabled."
  else
    echo ">>> Enabling addon '${addon}'..."
    microk8s enable "$addon"
  fi
}

echo "=== Quilly Support — MicroK8s Deploy ==="

if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ] && [ "$ENABLE_HTTPS_SELFSIGNED" = "true" ]; then
  echo "ERROR: ENABLE_HTTPS_LETSENCRYPT and ENABLE_HTTPS_SELFSIGNED cannot both be true."
  exit 1
fi

if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ]; then
  if [ -z "$APP_DOMAIN" ]; then
    echo "ERROR: ENABLE_HTTPS_LETSENCRYPT=true but APP_DOMAIN is not set."
    echo "Set APP_DOMAIN to your public DNS host (example: support.example.com)."
    exit 1
  fi
  if [ -z "$LETSENCRYPT_EMAIL" ]; then
    echo "ERROR: ENABLE_HTTPS_LETSENCRYPT=true but LETSENCRYPT_EMAIL is not set."
    echo "Set LETSENCRYPT_EMAIL to an address used for ACME registration."
    exit 1
  fi
fi

if [ "$ENABLE_HTTPS_SELFSIGNED" = "true" ]; then
  if [ -z "$APP_DOMAIN" ]; then
    echo "ERROR: ENABLE_HTTPS_SELFSIGNED=true but APP_DOMAIN is not set."
    echo "Set APP_DOMAIN (example: support.example.com)."
    exit 1
  fi
fi

# 1. Enable required MicroK8s addons
echo ""
if [ "$SKIP_ADDONS" = "true" ]; then
  echo ">>> SKIP_ADDONS=true — skipping addon checks."
else
  echo ">>> Ensuring MicroK8s addons (dns, storage, registry)..."
  ensure_addon dns
  ensure_addon storage
  ensure_addon registry
  if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ] || [ "$ENABLE_HTTPS_SELFSIGNED" = "true" ]; then
    echo ">>> HTTPS enabled — ensuring ingress addon..."
    ensure_addon ingress
  fi
  if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ]; then
    echo ">>> Let's Encrypt enabled — ensuring cert-manager addon..."
    ensure_addon cert-manager
  fi
fi

# 2. Build the Docker image
echo ""
if [ "$SKIP_BUILD" = "true" ]; then
  echo ">>> SKIP_BUILD=true — skipping image build and push."
else
  echo ">>> Building Docker image..."
  BUILD_FLAGS=()
  if [ "$BUILD_NO_CACHE" = "true" ]; then
    BUILD_FLAGS+=(--no-cache)
  fi
  docker build "${BUILD_FLAGS[@]}" -t quilly-support:latest "$PROJECT_DIR"

  # 3. Tag and push to MicroK8s local registry
  echo ""
  echo ">>> Pushing image to local registry ($IMAGE)..."
  docker tag quilly-support:latest "$IMAGE"
  docker push "$IMAGE"
fi

# 4. Apply Kubernetes manifests in order
echo ""
echo ">>> Applying Kubernetes manifests..."
microk8s kubectl apply -f "$SCRIPT_DIR/namespace.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/secret.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/pvc-data.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/pvc-documents.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/pvc-images.yaml"

# Seed docs only on first install (or when explicitly forced) to avoid
# repeatedly triggering document indexing during normal redeploys.
if [ "$FORCE_SEED_DOCS" = "true" ]; then
  echo ">>> FORCE_SEED_DOCS=true — rerunning seed job..."
  microk8s kubectl delete job "$SEED_JOB" -n "$NAMESPACE" --ignore-not-found
  microk8s kubectl apply -f "$SCRIPT_DIR/job-seed-docs.yaml"
  echo ">>> Waiting for seed job to complete..."
  microk8s kubectl wait --for=condition=complete "job/$SEED_JOB" \
    -n "$NAMESPACE" --timeout=120s
elif microk8s kubectl get deployment "$APP_DEPLOYMENT" -n "$NAMESPACE" >/dev/null 2>&1; then
  echo ">>> Existing deployment found — skipping seed job to avoid re-indexing."
else
  echo ">>> First deploy detected — running seed job..."
  microk8s kubectl apply -f "$SCRIPT_DIR/job-seed-docs.yaml"
  echo ">>> Waiting for seed job to complete..."
  microk8s kubectl wait --for=condition=complete "job/$SEED_JOB" \
    -n "$NAMESPACE" --timeout=120s
fi

microk8s kubectl apply -f "$SCRIPT_DIR/deployment.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/service.yaml"

if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ]; then
  if [ "$LETSENCRYPT_STAGING" = "true" ]; then
    ACME_SERVER="https://acme-staging-v02.api.letsencrypt.org/directory"
    if [ -z "$LETSENCRYPT_ISSUER_NAME" ]; then
      LETSENCRYPT_ISSUER_NAME="letsencrypt-staging"
    fi
  else
    ACME_SERVER="https://acme-v02.api.letsencrypt.org/directory"
    if [ -z "$LETSENCRYPT_ISSUER_NAME" ]; then
      LETSENCRYPT_ISSUER_NAME="letsencrypt-prod"
    fi
  fi

  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT

  echo ">>> Rendering and applying ClusterIssuer (${LETSENCRYPT_ISSUER_NAME})..."
  sed \
    -e "s|__ISSUER_NAME__|$LETSENCRYPT_ISSUER_NAME|g" \
    -e "s|__LETSENCRYPT_EMAIL__|$LETSENCRYPT_EMAIL|g" \
    -e "s|__ACME_SERVER__|$ACME_SERVER|g" \
    "$SCRIPT_DIR/clusterissuer-letsencrypt.template.yaml" > "$TMP_DIR/clusterissuer.yaml"
  microk8s kubectl apply -f "$TMP_DIR/clusterissuer.yaml"

  echo ">>> Rendering and applying Ingress for ${APP_DOMAIN}..."
  sed \
    -e "s|__ISSUER_NAME__|$LETSENCRYPT_ISSUER_NAME|g" \
    -e "s|__APP_DOMAIN__|$APP_DOMAIN|g" \
    -e "s|__TLS_SECRET_NAME__|$TLS_SECRET_NAME|g" \
    "$SCRIPT_DIR/ingress-letsencrypt.template.yaml" > "$TMP_DIR/ingress.yaml"
  microk8s kubectl apply -f "$TMP_DIR/ingress.yaml"

  echo ">>> Waiting for TLS certificate secret (${TLS_SECRET_NAME})..."
  microk8s kubectl wait --for=condition=ready certificate/"$TLS_SECRET_NAME" \
    -n "$NAMESPACE" --timeout=300s || true
fi

if [ "$ENABLE_HTTPS_SELFSIGNED" = "true" ]; then
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  NODE_IP_FOR_CERT="$(microk8s kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"

  echo ">>> Generating self-signed certificate for ${APP_DOMAIN} and ${NODE_IP_FOR_CERT} (${SELF_SIGNED_CERT_DAYS} days)..."
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$TMP_DIR/tls.key" \
    -out "$TMP_DIR/tls.crt" \
    -days "$SELF_SIGNED_CERT_DAYS" \
    -subj "/CN=${APP_DOMAIN}" \
    -addext "subjectAltName=DNS:${APP_DOMAIN},IP:${NODE_IP_FOR_CERT}" >/dev/null 2>&1

  echo ">>> Creating/updating TLS secret (${TLS_SECRET_NAME})..."
  microk8s kubectl create secret tls "$TLS_SECRET_NAME" \
    --cert="$TMP_DIR/tls.crt" \
    --key="$TMP_DIR/tls.key" \
    -n "$NAMESPACE" \
    --dry-run=client -o yaml | microk8s kubectl apply -f -

  echo ">>> Applying HTTPS ingress (self-signed)..."
  sed \
    -e "s|__APP_DOMAIN__|$APP_DOMAIN|g" \
    -e "s|__TLS_SECRET_NAME__|$TLS_SECRET_NAME|g" \
    "$SCRIPT_DIR/ingress-selfsigned.template.yaml" > "$TMP_DIR/ingress-selfsigned.yaml"
  microk8s kubectl apply -f "$TMP_DIR/ingress-selfsigned.yaml"

  # Remove stale cert-manager resources for this secret/certificate name, if present.
  microk8s kubectl delete certificate "$TLS_SECRET_NAME" -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
  microk8s kubectl delete certificaterequest,order,challenge \
    -n "$NAMESPACE" -l "cert-manager.io/certificate-name=${TLS_SECRET_NAME}" >/dev/null 2>&1 || true
fi

if [ "$FORCE_ROLLOUT_RESTART" = "true" ]; then
  echo ">>> Restarting deployment pods to pick up latest image..."
  microk8s kubectl rollout restart "deployment/$APP_DEPLOYMENT" -n "$NAMESPACE"
fi

# 5. Wait for the deployment to be ready
echo ""
echo ">>> Waiting for deployment to be ready..."
microk8s kubectl rollout status deployment/quilly-support \
  -n "$NAMESPACE" --timeout=300s

# 6. Print access URL
NODE_IP=$(microk8s kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo ""
echo "=== Deployment complete! ==="
if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ]; then
  echo "HTTPS configured for: https://${APP_DOMAIN}"
  echo "  (ensure DNS A/AAAA for ${APP_DOMAIN} points to this node and ports 80/443 are reachable)"
fi
if [ "$ENABLE_HTTPS_SELFSIGNED" = "true" ]; then
  echo "HTTPS configured with self-signed cert for: https://${APP_DOMAIN}"
  echo "  (clients will show an untrusted certificate warning unless they trust this cert)"
fi
echo "HTTP access: http://${NODE_IP}:30082"
echo "  (or http://localhost:30082 if running locally)"
echo ""
echo "Useful commands:"
echo "  microk8s kubectl get pods -n $NAMESPACE"
if [ "$ENABLE_HTTPS_LETSENCRYPT" = "true" ] || [ "$ENABLE_HTTPS_SELFSIGNED" = "true" ]; then
  echo "  microk8s kubectl get ingress,certificate,challenge -n $NAMESPACE"
fi
echo "  microk8s kubectl logs -n $NAMESPACE deployment/quilly-support"
echo "  microk8s kubectl describe pod -n $NAMESPACE -l app=quilly-support"
