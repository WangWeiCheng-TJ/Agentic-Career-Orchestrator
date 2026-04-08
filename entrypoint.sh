#!/bin/bash
# entrypoint.sh - S3 sync wrapper
# 啟動時從 S3 pull data，結束時 push 回去

# set -e  # 任何指令失敗就停止
set -euo pipefail

S3_BUCKET=${S3_BUCKET:-"agentic-career-orchestrator-wcw-dev"}
LOCAL_DATA="/app/data"

echo "📥 Syncing data from S3..."
# aws s3 sync s3://${S3_BUCKET}/data ${LOCAL_DATA} --quiet
aws s3 sync s3://${S3_BUCKET}/data ${LOCAL_DATA}
echo "✅ S3 sync done."

# 執行傳進來的指令（例如 python src/phases/p3_council.py --test-limit 2）
echo "🚀 Running: $@"
"$@"
EXIT_CODE=$?

echo "📤 Syncing results back to S3..."
aws s3 sync ${LOCAL_DATA} s3://${S3_BUCKET}/data --quiet
echo "✅ Upload done."

exit $EXIT_CODE