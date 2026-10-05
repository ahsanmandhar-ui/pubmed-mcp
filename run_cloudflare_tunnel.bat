@echo off
REM =====================================================================
REM Start PubMed MCP Server with Cloudflare Tunnel (Public HTTPS URL)
REM =====================================================================

cd /d "%~dp0"

echo [1/3] Checking cloudflared...
where cloudflared >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo cloudflared not found. Downloading standalone cloudflared.exe from Cloudflare...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
    set "CLOUDFLARED=%~dp0cloudflared.exe"
) else (
    set "CLOUDFLARED=cloudflared"
)

echo [2/3] Starting PubMed MCP Server on port 8080 (streamable-http)...
set MCP_TRANSPORT=streamable-http
set PORT=8080
start "PubMed MCP Server" .venv\Scripts\python.exe server.py

echo [3/3] Starting Cloudflare Tunnel...
echo Your public MCP endpoint will be displayed below:
echo (Copy the https://*.trycloudflare.com URL and add /mcp to it for OpenCode)
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:8080
