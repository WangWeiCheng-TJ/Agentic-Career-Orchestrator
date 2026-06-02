#!/bin/bash
set -euo pipefail

S3_BUCKET=${S3_BUCKET:-"agentic-career-orchestrator-wcw-dev"}
LOCAL_DATA="/app/data"
RUNTIME_ENV=${ACO_RUNTIME_ENV:-"local"}

if [ "$RUNTIME_ENV" = "aws" ]; then
  echo "📥 Syncing data from S3..."
  aws s3 sync s3://${S3_BUCKET}/data ${LOCAL_DATA}
  echo "✅ S3 sync done."
else
  echo "🏠 Local mode detected. Skip S3 sync."
fi

echo "🚀 Running: $@"
"$@"
EXIT_CODE=$?

if [ "$RUNTIME_ENV" = "aws" ]; then
  echo "📤 Syncing results back to S3..."
  aws s3 sync ${LOCAL_DATA} s3://${S3_BUCKET}/data --quiet
  echo "✅ Upload done."
else
  echo "🏠 Local mode detected. Skip S3 upload."
fi

exit $EXIT_CODE