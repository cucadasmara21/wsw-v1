#!/bin/bash
# Codespaces Health Check Script

echo "=== CODESPACES HEALTH CHECK ==="
echo ""

echo "1. Process Status:"
echo "   Backend (8000):"
lsof -i :8000 -sTCP:LISTEN 2>/dev/null | grep -v COMMAND || echo "   ❌ Not running"
echo "   Frontend (5173):"
lsof -i :5173 -sTCP:LISTEN 2>/dev/null | grep -v COMMAND || echo "   ❌ Not running"
echo ""

echo "2. Binding Check (must be 0.0.0.0):"
ss -tln | grep -E ":(8000|5173)"
echo ""

echo "3. Local Connectivity:"
echo "   Backend /health:"
curl -s -o /dev/null -w "   HTTP %{http_code} - %{time_total}s\n" http://127.0.0.1:8000/health
echo "   Frontend /:"
curl -s -o /dev/null -w "   HTTP %{http_code} - %{time_total}s\n" http://127.0.0.1:5173/
echo ""

echo "4. Codespaces URLs:"
if [ -n "$CODESPACE_NAME" ]; then
  echo "   ✅ Running in Codespaces: $CODESPACE_NAME"
  echo "   Backend:  https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  echo "   Frontend: https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
else
  echo "   ⚠️  Not running in GitHub Codespaces (or env vars not set)"
fi
echo ""

echo "5. Port Visibility (check in VS Code Ports panel):"
echo "   - Both ports should be 'Public' or 'Private' (not 'Local')"
echo "   - If you see 502, try changing visibility to Public"
echo ""

echo "=== TROUBLESHOOTING ==="
echo "If you get 502 errors:"
echo "1. Open VS Code Ports panel (View → Ports or Ctrl+Shift+\`)"
echo "2. Right-click each port (8000, 5173) → Port Visibility → Public"
echo "3. Refresh your browser"
echo "4. If still failing, stop services and restart"
echo ""
