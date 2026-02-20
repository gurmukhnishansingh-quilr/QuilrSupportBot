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

# 1. Enable required MicroK8s addons
echo ""
if [ "$SKIP_ADDONS" = "true" ]; then
  echo ">>> SKIP_ADDONS=true — skipping addon checks."
else
  echo ">>> Ensuring MicroK8s addons (dns, storage, registry)..."
  ensure_addon dns
  ensure_addon storage
  ensure_addon registry
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

# 5. Wait for the deployment to be ready
echo ""
echo ">>> Waiting for deployment to be ready..."
microk8s kubectl rollout status deployment/quilly-support \
  -n "$NAMESPACE" --timeout=300s

# 6. Print access URL
NODE_IP=$(microk8s kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo ""
echo "=== Deployment complete! ==="
echo "Access the app at: http://${NODE_IP}:30082"
echo "  (or http://localhost:30082 if running locally)"
echo ""
echo "Useful commands:"
echo "  microk8s kubectl get pods -n $NAMESPACE"
echo "  microk8s kubectl logs -n $NAMESPACE deployment/quilly-support"
echo "  microk8s kubectl describe pod -n $NAMESPACE -l app=quilly-support"
