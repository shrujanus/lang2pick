#!/usr/bin/env bash
set -euo pipefail

# Generate Python gRPC code from .proto files into the package source tree.
# Usage: ./generate_proto.sh [-p PROTO_DIR] [-o OUT_DIR]
# Run this from the repository root.

usage() {
  cat <<EOF
Usage: $0 [-p PROTO_DIR] [-o OUT_DIR]

Options:
  -p, --proto-dir   Directory containing .proto files (default: "proto")
  -o, --out         Output Python package directory for generated files (default: "vla/src/vision_bridge")
  -h, --help        Show this help

Example:
  $0 -p proto -o vla/src/vision_bridge
EOF
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--out)
      OUT_DIR="$2"
      shift 2
      ;;
    -p|--proto-dir)
      PROTO_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

echo "Generating python grpc code from ${PROTO_DIR}/*.proto -> ${OUT_DIR}"

# Ensure output directory exists
mkdir -p "${OUT_DIR}"

python3 -m grpc_tools.protoc \
  -I "${PROTO_DIR}" \
  --python_out="${OUT_DIR}" \
  --grpc_python_out="${OUT_DIR}" \
  "${PROTO_DIR}"/vision_bridge.proto

echo "Generation complete. You may need to add the generated files to version control."
