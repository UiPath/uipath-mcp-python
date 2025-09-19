#!/bin/bash

cleanup() {
    echo "Cleaning up..."
    if [ ! -z "$MCP_PID" ]; then
        echo "Stopping MCP server (PID: $MCP_PID)..."
        kill $MCP_PID 2>/dev/null || true
        wait $MCP_PID 2>/dev/null || true
    fi
}

# Set trap to cleanup on script exit
trap cleanup EXIT

echo "Syncing dependencies..."
uv sync

echo "Authenticating with UiPath..."
uv run uipath auth --client-id="$CLIENT_ID" --client-secret="$CLIENT_SECRET" --base-url="$BASE_URL"

# Generate dynamic values
PR_NUMBER=${GITHUB_PR_NUMBER:-"local"}
UNIQUE_ID=$(cat /proc/sys/kernel/random/uuid)
MCP_SERVER_NAME="mathmcp-${PR_NUMBER}"

echo "Updating uipath.json with dynamic values... PR Number: $PR_NUMBER, MCP Server Name: $MCP_SERVER_NAME, Unique ID: $UNIQUE_ID"

# Remove empty tenantId line if exists
sed -i '/^UIPATH_TENANT_ID=[[:space:]]*$/d' .env

# Replace placeholders in uipath.json using sed
sed -i "s/PRNUMBER/$PR_NUMBER/g" mcp.json
sed -i "s/PRNUMBER/$PR_NUMBER/g" uipath.json
sed -i "s/163f06b8-31e6-4639-aa31-ae4a88968a92/$UNIQUE_ID/g" uipath.json

echo "Packing agent..."
uv run uipath pack

# uipath run will block, so we run it in the background
echo "Starting MCP server in background..."
uv run uipath run "$MCP_SERVER_NAME" > mcp_server_output.log 2>&1 &
MCP_PID=$!

echo "MCP server started with PID: $MCP_PID"
echo "Waiting a moment for server to initialize..."
sleep 20

echo "Running integration test..."
MCP_SERVER_NAME="$MCP_SERVER_NAME" uv run test.py

# Capture test exit code
TEST_EXIT_CODE=$?

echo "====== MCP Server Output ======"
cat mcp_server_output.log

echo "Test completed with exit code: $TEST_EXIT_CODE"

# Cleanup will happen automatically due to trap
exit $TEST_EXIT_CODE