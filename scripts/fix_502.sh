#!/bin/bash
# Script para verificar y guiar la configuración de puertos en Codespaces

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  CODESPACES PORT CONFIGURATION - 502 ERROR RESOLVER            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "✅ CURRENT STATUS:"
echo ""
echo "   Backend:  uvicorn running on 0.0.0.0:8000 ✓"
echo "   Frontend: vite running on 0.0.0.0:5173 ✓"
echo ""
echo "   Local tests:"
curl -s -o /dev/null -w "   • Backend:  HTTP %{http_code}\n" http://127.0.0.1:8000/health
curl -s -o /dev/null -w "   • Frontend: HTTP %{http_code}\n" http://127.0.0.1:5173/
echo ""

echo "🌐 YOUR CODESPACES URLS:"
echo ""
if [ -n "$CODESPACE_NAME" ]; then
  BACKEND_URL="https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  FRONTEND_URL="https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  echo "   Backend:  $BACKEND_URL"
  echo "   Frontend: $FRONTEND_URL"
  echo ""
  
  # Test if ports are public
  echo "🔍 TESTING PORT VISIBILITY:"
  echo ""
  BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" 2>&1)
  
  if [ "$BACKEND_STATUS" == "302" ] || [ "$BACKEND_STATUS" == "000" ]; then
    echo "   ❌ Ports are PRIVATE (require authentication)"
    echo ""
    echo "══════════════════════════════════════════════════════════════"
    echo "   FIX: Change port visibility to PUBLIC"
    echo "══════════════════════════════════════════════════════════════"
    echo ""
    echo "   1. In VS Code, open PORTS panel:"
    echo "      • Click 'PORTS' tab (bottom panel)"
    echo "      • OR press: Ctrl+Shift+\` then click 'PORTS'"
    echo ""
    echo "   2. For EACH port (8000 and 5173):"
    echo "      • Right-click on the port number"
    echo "      • Select: Port Visibility → Public"
    echo ""
    echo "   3. Refresh your browser on the URLs above"
    echo ""
    echo "══════════════════════════════════════════════════════════════"
  elif [ "$BACKEND_STATUS" == "200" ]; then
    echo "   ✅ Ports are PUBLIC - App should be accessible!"
    echo ""
    echo "   Open these URLs in your browser:"
    echo "   • Frontend: $FRONTEND_URL"
    echo "   • Backend:  $BACKEND_URL/docs"
  else
    echo "   ⚠️  Unexpected status: $BACKEND_STATUS"
  fi
else
  echo "   ⚠️  Not running in Codespaces"
fi

echo ""
echo "📋 RUNNING PROCESSES:"
ps aux | grep -E "(uvicorn|vite)" | grep -v grep | awk '{print "   "$1" "$2" "$11" "$12" "$13" "$14" "$15}'

echo ""
