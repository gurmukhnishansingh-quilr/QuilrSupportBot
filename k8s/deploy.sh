#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE="localhost:32000/quilly-support:latest"
NAMESPACE="quilly-support"

echo "=== Quilly Support — MicroK8s Deploy ==="

# 1. Enable required MicroK8s addons
echo ""
echo ">>> Enabling MicroK8s addons (dns, storage, registry)..."
microk8s enable dns storage registry

# 2. Build the Docker image
echo ""
echo ">>> Building Docker image..."
docker build -t quilly-support:latest "$PROJECT_DIR"

# 3. Tag and push to MicroK8s local registry
echo ""
echo ">>> Pushing image to local registry ($IMAGE)..."
docker tag quilly-support:latest "$IMAGE"
docker push "$IMAGE"

# 4. Apply Kubernetes manifests in order
echo ""
echo ">>> Applying Kubernetes manifests..."
microk8s kubectl apply -f "$SCRIPT_DIR/namespace.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/secret.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/pvc-data.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/pvc-documents.yaml"

# Delete previous seed job if it exists (jobs are immutable)
microk8s kubectl delete job seed-documents -n "$NAMESPACE" --ignore-not-found
microk8s kubectl apply -f "$SCRIPT_DIR/job-seed-docs.yaml"

echo ">>> Waiting for seed job to complete..."
microk8s kubectl wait --for=condition=complete job/seed-documents \
  -n "$NAMESPACE" --timeout=120s

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
