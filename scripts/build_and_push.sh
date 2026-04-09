#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   AWS_REGION=us-east-1 \
#   AWS_ACCOUNT_ID=123456789012 \
#   ECR_REPOSITORY=trading-bot-repo \
#   IMAGE_TAG=latest \
#   ./scripts/build_and_push.sh

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}"
ECR_REPOSITORY="${ECR_REPOSITORY:-trading-bot-repo}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo "[1/4] Login no ECR: ${ECR_REGISTRY}"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "[2/4] Build da imagem: ${IMAGE_URI}"
docker build -t "${IMAGE_URI}" .

echo "[3/4] Push da imagem para ECR"
docker push "${IMAGE_URI}"

echo "[4/4] Concluido"
echo "IMAGE_URI=${IMAGE_URI}"
