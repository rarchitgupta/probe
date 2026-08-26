#!/usr/bin/env bash
set -euo pipefail

readonly CLUSTER_NAME="probe"
readonly NAMESPACE="probe"
readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

for command_name in docker kind kubectl rg; do
  command -v "$command_name" >/dev/null || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example before starting the cluster." >&2
  exit 1
fi

if ! kind get clusters | rg -qx "$CLUSTER_NAME"; then
  kind create cluster --name "$CLUSTER_NAME" --wait 120s
fi
kubectl config use-context "kind-$CLUSTER_NAME" >/dev/null

docker build -t probe-backend:local .
docker build \
  --build-arg NEXT_PUBLIC_PROBE_API_URL=http://localhost:8000 \
  -t probe-client:local client
kind load docker-image --name "$CLUSTER_NAME" probe-backend:local probe-client:local

kubectl apply -f deploy/kubernetes/local/namespace.yaml
kubectl -n "$NAMESPACE" create secret generic probe-app-secrets \
  --from-env-file=.env \
  --dry-run=client \
  -o yaml | kubectl apply -f -

kubectl apply -k deploy/kubernetes/local/infra
kubectl -n "$NAMESPACE" rollout status statefulset/postgres --timeout=180s
kubectl -n "$NAMESPACE" rollout status statefulset/minio --timeout=180s
kubectl -n "$NAMESPACE" rollout status statefulset/temporal --timeout=180s

kubectl -n "$NAMESPACE" delete job probe-migrate probe-minio-init --ignore-not-found
kubectl apply -k deploy/kubernetes/local/jobs
kubectl -n "$NAMESPACE" wait --for=condition=complete job/probe-migrate --timeout=180s
kubectl -n "$NAMESPACE" wait --for=condition=complete job/probe-minio-init --timeout=180s

kubectl apply -k deploy/kubernetes/local/apps
kubectl -n "$NAMESPACE" rollout restart deployment/probe-api deployment/probe-worker deployment/probe-client
kubectl -n "$NAMESPACE" rollout status deployment/probe-api --timeout=180s
kubectl -n "$NAMESPACE" rollout status deployment/probe-worker --timeout=180s
kubectl -n "$NAMESPACE" rollout status deployment/probe-client --timeout=180s

cat <<'EOF'

Probe is running in kind. Open separate terminals for:
  kubectl -n probe port-forward service/probe-client 3000:3000
  kubectl -n probe port-forward service/probe-api 8000:8000
  kubectl -n probe port-forward service/minio 9000:9000 9001:9001
  kubectl -n probe port-forward service/temporal 8233:8233

Inspect the deployment with:
  kubectl -n probe get pods
EOF
