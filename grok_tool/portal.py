#!/usr/bin/env python3
"""
Grok API Customer Portal & Balance Checker & 1-Click Codex Setup (Windows + Linux/macOS).
Accurately synced with Sub2API Quota Enforcement & Instant Real-Time Streaming.
Port: 8082
"""
import http.server
import json
import os
import subprocess
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8082
BASE_URL = "https://grokapi.duckdns.org/v1"
USD_TO_VND = 25600.0

def format_ts(ts_str: str) -> str:
    if not ts_str:
        return "—"
    try:
        clean = ts_str.split(".")[0]
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%H:%M:%S %d/%m/%Y")
    except Exception:
        return ts_str[:19]

def query_key_info(api_key: str) -> dict:
    clean_key = api_key.strip()
    if not clean_key.startswith("sk-"):
        return {"ok": False, "error": "API Key không hợp lệ (phải bắt đầu bằng sk-)"}
    
    # 1. Query Key Info from Postgres
    sql_key = f"SELECT id, name, status, quota, quota_used, created_at, last_used_at FROM api_keys WHERE key = '{clean_key}' AND deleted_at IS NULL LIMIT 1;"
    cmd_key = ["docker", "exec", "sub2api-postgres", "psql", "-U", "sub2api", "-d", "sub2api", "-t", "-A", "-F", "|", "-c", sql_key]
    try:
        res = subprocess.check_output(cmd_key, timeout=5).decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return {"ok": False, "error": f"Lỗi truy vấn hệ thống: {e}"}
    
    if not res:
        return {"ok": False, "error": "Không tìm thấy API Key này trên hệ thống. Vui lòng kiểm tra lại!"}
    
    parts = res.split("|")
    key_id = parts[0]
    name = parts[1] if len(parts) > 1 else "Grok Key"
    status = parts[2] if len(parts) > 2 else "active"
    quota_usd = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
    quota_used_usd = float(parts[4]) if len(parts) > 4 and parts[4] else 0.0
    created_at = parts[5] if len(parts) > 5 else ""
    last_used = parts[6] if len(parts) > 6 else "Chưa sử dụng"
    
    # Base Token Calculation directly from Sub2API Quota ($1 = 500,000 tokens)
    max_tokens = round(quota_usd * 500000)
    remain_usd = max(0.0, quota_usd - quota_used_usd)
    remain_tokens = round(remain_usd * 500000) if quota_usd > 0 else 0
    used_tokens = max(0, max_tokens - remain_tokens)
    remain_pct = round((remain_usd / quota_usd) * 100, 1) if quota_usd > 0 else 0.0

    # 2. Query Usage Logs for this key
    logs = []
    sql_logs = f"SELECT model, input_tokens, output_tokens, total_cost, duration_ms, created_at FROM usage_logs WHERE api_key_id = {key_id} ORDER BY id DESC LIMIT 50;"
    cmd_logs = ["docker", "exec", "sub2api-postgres", "psql", "-U", "sub2api", "-d", "sub2api", "-t", "-A", "-F", "|", "-c", sql_logs]
    try:
        res_logs = subprocess.check_output(cmd_logs, timeout=5).decode("utf-8", errors="ignore").strip()
        if res_logs:
            for line in res_logs.splitlines():
                if not line.strip():
                    continue
                lp = line.split("|")
                if len(lp) >= 6:
                    model = lp[0]
                    in_tok = int(lp[1] or 0)
                    out_tok = int(lp[2] or 0)
                    cost_usd = float(lp[3] or 0.0)
                    cost_vnd = round(cost_usd * USD_TO_VND)
                    dur_ms = int(lp[4] or 0)
                    ts_raw = lp[5]
                    
                    logs.append({
                        "time": format_ts(ts_raw),
                        "model": model,
                        "status": "Oke",
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "tokens_display": f"{in_tok:,} / {out_tok:,}",
                        "cost_vnd": f"{cost_vnd}đ" if cost_vnd > 0 else "< 1đ",
                        "cost_usd": f"${cost_usd:.6f}",
                        "latency": f"{dur_ms / 1000:.3f}s" if dur_ms >= 1000 else f"{dur_ms}ms",
                    })
    except Exception as e:
        print("Error fetching logs:", e)

    return {
        "ok": True,
        "name": name,
        "key_masked": clean_key[:12] + "..." + clean_key[-6:],
        "full_key": clean_key,
        "status": status if remain_tokens > 0 else "exhausted",
        "quota_usd": quota_usd,
        "quota_used_usd": quota_used_usd,
        "max_tokens": max_tokens,
        "used_tokens": used_tokens,
        "remain_tokens": remain_tokens,
        "remain_pct": remain_pct,
        "created_at": format_ts(created_at),
        "last_used": format_ts(last_used) if last_used and last_used != "Chưa sử dụng" else "Chưa sử dụng",
        "models": ["grok-4.6", "grok-4.5", "grok-2", "grok-beta"],
        "base_url": BASE_URL,
        "logs": logs,
    }

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Grok API — Tra Cứu Số Dư & Cài Đặt 1-Click</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(15, 23, 42, 0.85);
      --border: rgba(255, 255, 255, 0.1);
      --primary: #10b981;
      --primary-glow: rgba(16, 185, 129, 0.2);
      --accent: #38bdf8;
      --text: #f1f5f9;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    body { background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 30px 16px; background-image: radial-gradient(circle at 50% 0%, rgba(56, 189, 248, 0.12) 0%, transparent 60%); }
    .container { width: 100%; max-width: 840px; }
    .header { text-align: center; margin-bottom: 24px; }
    .header h1 { font-size: 26px; font-weight: 800; color: #fff; display: flex; align-items: center; justify-content: center; gap: 10px; }
    .header p { font-size: 13px; color: var(--muted); margin-top: 6px; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 22px; margin-bottom: 20px; backdrop-filter: blur(12px); box-shadow: 0 10px 30px rgba(0,0,0,0.4); }
    .input-group { display: flex; gap: 8px; margin-top: 10px; }
    input[type="text"] { flex: 1; background: rgba(0,0,0,0.4); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; color: #fff; font-size: 14px; font-family: monospace; outline: none; transition: border 0.2s; }
    input[type="text"]:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-glow); }
    .btn { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #fff; border: none; border-radius: 10px; padding: 12px 20px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
    .btn:hover { opacity: 0.92; transform: translateY(-1px); }
    .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
    .stat-box { background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }
    .stat-label { font-size: 11px; text-transform: uppercase; color: var(--muted); font-weight: 600; }
    .stat-val { font-size: 20px; font-weight: 800; color: #fff; margin-top: 4px; }
    .battery-bar { width: 100%; height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; margin-top: 14px; }
    .battery-fill { height: 100%; background: linear-gradient(90deg, #10b981 0%, #38bdf8 100%); border-radius: 4px; transition: width 0.4s ease; }
    .code-box { background: rgba(0,0,0,0.6); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 10px; padding: 12px 95px 12px 14px; font-family: monospace; font-size: 12px; color: #38bdf8; word-break: break-all; margin-top: 8px; position: relative; }
    .copy-btn { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); padding: 6px 12px; font-size: 11.5px; font-weight: 700; background: #2563eb; border: none; border-radius: 6px; color: #fff; cursor: pointer; transition: all 0.2s; white-space: nowrap; box-shadow: 0 2px 6px rgba(0,0,0,0.3); }
    .copy-btn:hover { background: var(--primary); }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }
    .badge-active { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid #10b981; }
    .badge-exhausted { background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid #ef4444; }
    
    .table-wrap { width: 100%; overflow-x: auto; margin-top: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
    th { padding: 10px 8px; border-bottom: 1px solid var(--border); color: var(--muted); font-size: 11px; text-transform: uppercase; font-weight: 600; white-space: nowrap; }
    td { padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.04); white-space: nowrap; }
    tr:hover td { background: rgba(255,255,255,0.03); }
    .tag-ok { color: #10b981; font-weight: 700; background: rgba(16,185,129,0.12); padding: 2px 6px; border-radius: 4px; }
    .tok-val { font-family: monospace; font-weight: 600; color: #fff; }
    .cost-val { color: #f59e0b; font-weight: 700; }
    .lat-val { color: #38bdf8; font-family: monospace; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>⚡ GROK API PORTAL</h1>
      <p>Kiểm tra số dư Token, Lịch sử request & Cài đặt 1-Click Windows / Linux</p>
    </div>

    <!-- Search Card -->
    <div class="card">
      <label style="font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase;">Nhập API Key của bạn:</label>
      <div class="input-group">
        <input type="text" id="input-key" placeholder="sk-..." value="" autocomplete="off" />
        <button class="btn" onclick="checkBalance()">Tra Cứu</button>
      </div>
    </div>

    <!-- Result Container -->
    <div id="result-box" style="display: none;"></div>

    <!-- Instructions Card -->
    <div class="card">
      <div style="font-size: 14px; font-weight: 700; margin-bottom: 12px; color: #fff;">📌 Thông Tin Cấu Hình Thủ Công:</div>
      <div style="font-size: 13px; line-height: 1.8; color: var(--muted);">
        <div>🌐 <b>Base URL:</b> <code style="color: #fff;">https://grokapi.duckdns.org/v1</code></div>
        <div>🤖 <b>Model:</b> <code style="color: #38bdf8;">grok-4.6</code>, <code style="color: #38bdf8;">grok-4.5</code>, <code style="color: #38bdf8;">grok-2</code></div>
        <div>⚡ <b>Tương thích:</b> 100% Codex Desktop App, Chatbox, NextChat, Cursor, VS Code, Dify...</div>
      </div>
    </div>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    const initialKey = params.get('key') || '';
    if (initialKey) {
      document.getElementById('input-key').value = initialKey;
      checkBalance();
    }

    async function checkBalance() {
      const key = document.getElementById('input-key').value.trim();
      if (!key) return;
      const resBox = document.getElementById('result-box');
      resBox.style.display = 'block';
      resBox.innerHTML = '<div class="card" style="text-align:center;color:var(--muted);">⏳ Đang tra cứu số dư & lịch sử request...</div>';

      try {
        const r = await fetch('/api/check-key?key=' + encodeURIComponent(key));
        const d = await r.json();
        if (!d.ok) {
          resBox.innerHTML = '<div class="card" style="border-color:#ef4444;background:rgba(239,68,68,0.05);color:#ef4444;font-size:13px;">❌ ' + d.error + '</div>';
          return;
        }

        const isExhausted = d.remain_tokens <= 0;
        const pctColor = d.remain_pct > 50 ? '#10b981' : (d.remain_pct > 15 ? '#f59e0b' : '#ef4444');

        const logsHtml = (d.logs && d.logs.length) ? d.logs.map(l => `
          <tr>
            <td style="color:var(--muted);">${l.time}</td>
            <td><strong style="color:#38bdf8;">${l.model}</strong></td>
            <td><span class="tag-ok">${l.status}</span></td>
            <td class="tok-val">${l.tokens_display}</td>
            <td class="cost-val">${l.cost_vnd} <small style="color:var(--muted); font-size:10px;">(${l.cost_usd})</small></td>
            <td class="lat-val">${l.latency}</td>
          </tr>
        `).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:18px;">Chưa có lượt request nào. Hãy thử chat 1 câu!</td></tr>';

        resBox.innerHTML = `
          <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <span class="badge ${isExhausted ? 'badge-exhausted' : 'badge-active'}">${isExhausted ? 'HẾT TOKEN' : 'ACTIVE'}</span>
                <strong style="margin-left:8px; font-size:16px;">${d.name}</strong>
              </div>
              <span style="font-size:12px; color:var(--muted); font-family:monospace;">${d.key_masked}</span>
            </div>

            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-label">🔋 Token Còn Lại</div>
                <div class="stat-val" style="color:${pctColor};">${d.remain_tokens.toLocaleString()} <small style="font-size:12px;color:var(--muted);">/ ${d.max_tokens.toLocaleString()}</small></div>
                <div style="font-size:11px;color:var(--muted);margin-top:4px;">Còn lại ${d.remain_pct}% ($${d.quota_usd - d.quota_used_usd > 0 ? (d.quota_usd - d.quota_used_usd).toFixed(4) : '0.0000'})</div>
              </div>

              <div class="stat-box">
                <div class="stat-label">⚡ Đã Tiêu Thụ</div>
                <div class="stat-val">${d.used_tokens.toLocaleString()} <small style="font-size:12px;color:var(--muted);">tokens</small></div>
                <div style="font-size:11px;color:var(--muted);margin-top:4px;">$${d.quota_used_usd.toFixed(4)} USD</div>
              </div>
            </div>

            <div class="battery-bar">
              <div class="battery-fill" style="width: ${d.remain_pct}%; background:${pctColor};"></div>
            </div>

            <!-- Windows 1-Click Command -->
            <div style="margin-top:20px; border-top:1px solid var(--border); padding-top:16px;">
              <div style="font-size:12px; font-weight:700; color:#38bdf8; margin-bottom:6px;">⚡ Lệnh 1-Click Cài Đặt Cho Windows (PowerShell / Codex App):</div>
              <div class="code-box">
                <span id="cmd-win">irm "https://grokapi.duckdns.org/setup-codex-windows?key=${d.full_key}" | iex</span>
                <button class="copy-btn" onclick="copyFromElem('cmd-win', this)">📋 Copy</button>
              </div>
            </div>

            <!-- Linux/macOS 1-Click Command -->
            <div style="margin-top:14px;">
              <div style="font-size:12px; font-weight:700; color:#10b981; margin-bottom:6px;">🐧 Lệnh 1-Click Cài Đặt Cho Linux / macOS (Terminal):</div>
              <div class="code-box" style="border-color:rgba(16,185,129,0.3); color:#34d399;">
                <span id="cmd-linux">curl -fsSL "https://grokapi.duckdns.org/setup-linux?key=${d.full_key}" | bash</span>
                <button class="copy-btn" onclick="copyFromElem('cmd-linux', this)">📋 Copy</button>
              </div>
              <p style="font-size:11px; color:var(--muted); margin-top:6px;">Tự động cấu hình <code>~/.codex/config.toml</code> + lưu biến môi trường <code>~/.bashrc</code> và <code>~/.zshrc</code>.</p>
            </div>
          </div>

          <!-- Detailed Request Logs Card -->
          <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
              <div>
                <div style="font-size:15px; font-weight:800; color:#fff;">📋 Logs gần nhất</div>
                <div style="font-size:12px; color:var(--muted);">Chi tiết từng lượt gọi API và số token tiêu hao</div>
              </div>
              <span class="badge badge-active">${(d.logs || []).length} Requests</span>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Thời gian</th>
                    <th>Model</th>
                    <th>Status</th>
                    <th>Token (In / Out)</th>
                    <th>Cost</th>
                    <th>Latency</th>
                  </tr>
                </thead>
                <tbody>
                  ${logsHtml}
                </tbody>
              </table>
            </div>
          </div>
        `;
      } catch (err) {
        resBox.innerHTML = '<div class="card" style="color:#ef4444;">Lỗi kết nối tới máy chủ kiểm tra: ' + err.message + '</div>';
      }
    }

    async function copyFromElem(elemId, btn) {
      const el = document.getElementById(elemId);
      if (!el) return;
      const text = el.innerText || el.textContent;
      
      let success = false;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          success = true;
        }
      } catch (e) {}

      if (!success) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.top = '-9999px';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {
          document.execCommand('copy');
          success = true;
        } catch (err) {}
        document.body.removeChild(ta);
      }

      if (btn) {
        const orig = btn.innerText;
        btn.innerText = '✅ Đã chép!';
        btn.style.background = '#10b981';
        btn.style.color = '#fff';
        setTimeout(() => {
          btn.innerText = orig;
          btn.style.background = '';
          btn.style.color = '';
        }, 2000);
      }
    }
  </script>
</body>
</html>
"""

def generate_codex_ps_script(key: str, default_model: str, small_model: str, medium_model: str, large_model: str) -> str:
    base = BASE_URL
    return f"""# Grok API & Codex App 1-Click Auto Setup Script (Windows PowerShell)
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   ⚡ GROK API & CODEX APP 1-CLICK AUTO SETUP (WINDOWS)" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan

$apiKey = "{key}"
$baseUrl = "{base}"
$defaultModel = "{default_model}"
$smallModel = "{small_model}"
$mediumModel = "{medium_model}"
$largeModel = "{large_model}"

if (-not $apiKey) {{
    Write-Host "[!] Loi: Thieu API Key trong duong dan." -ForegroundColor Red
    return
}}

Write-Host "[..] Dang thiet lap bien moi truong he thong Windows..." -ForegroundColor Gray
[System.Environment]::SetEnvironmentVariable('GROK_DEPLOYMENT_KEY', $apiKey, 'User')
[System.Environment]::SetEnvironmentVariable('OPENAI_BASE_URL', $baseUrl, 'User')
[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $apiKey, 'User')
[System.Environment]::SetEnvironmentVariable('CODEX_API_KEY', $apiKey, 'User')
[System.Environment]::SetEnvironmentVariable('XAI_BASE_URL', $baseUrl, 'User')
[System.Environment]::SetEnvironmentVariable('XAI_API_KEY', $apiKey, 'User')
$env:GROK_DEPLOYMENT_KEY = $apiKey
$env:OPENAI_BASE_URL = $baseUrl
$env:OPENAI_API_KEY = $apiKey
$env:XAI_BASE_URL = $baseUrl
$env:XAI_API_KEY = $apiKey
Write-Host "[OK] Da thiet lap API Gateway thanh cong!" -ForegroundColor Green
Write-Host "[OK] Da luu API Key vao he thong Windows thanh cong!" -ForegroundColor Green

# Configure Codex Desktop / CLI App (~/.codex)
$codexDir = Join-Path $env:USERPROFILE ".codex"
if (-not (Test-Path $codexDir)) {{
    New-Item -ItemType Directory -Path $codexDir -Force | Out-Null
}}

$configToml = @"
model_provider = "grok"
model = "$defaultModel"
model_small = "$smallModel"
model_medium = "$mediumModel"
model_large = "$largeModel"

[model_providers.grok]
name = "Grok API"
base_url = "$baseUrl"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
"@

Set-Content -Path (Join-Path $codexDir "config.toml") -Value $configToml -Encoding UTF8

$authJson = @"
{{
  "OPENAI_API_KEY": "$apiKey",
  "CODEX_API_KEY": "$apiKey",
  "api_key": "$apiKey",
  "grok": {{
    "api_key": "$apiKey"
  }}
}}
"@

Set-Content -Path (Join-Path $codexDir "auth.json") -Value $authJson -Encoding UTF8
Write-Host "[OK] Da tu dong cau hinh file ~/.codex/config.toml cho Codex Desktop App!" -ForegroundColor Green

# Configure Grok Build CLI (~/.grok)
$grokDir = Join-Path $env:USERPROFILE ".grok"
if (-not (Test-Path $grokDir)) {{
    New-Item -ItemType Directory -Path $grokDir -Force | Out-Null
}}

$grokConfigToml = @"
[models]
default = "grok-4.6"

[model.grok-4.6]
model = "$defaultModel"
base_url = "$baseUrl"
name = "Grok 4.6 Flagship"
env_key = "XAI_API_KEY"

[model.grok-2]
model = "grok-2"
base_url = "$baseUrl"
name = "Grok 2 Flash"
env_key = "XAI_API_KEY"
"@

Set-Content -Path (Join-Path $grokDir "config.toml") -Value $grokConfigToml -Encoding UTF8
Set-Content -Path (Join-Path $grokDir "auth.json") -Value $authJson -Encoding UTF8
Write-Host "[OK] Da tu dong cau hinh ~/.grok/config.toml cho Grok Build CLI!" -ForegroundColor Green

$desktop = [Environment]::GetFolderPath("Desktop")
$batPath = "$desktop\\Chat_Grok.bat"

$chatScript = @"
@echo off
chcp 65001 >nul
title Grok 4.6 AI Terminal
python -c "import urllib.request, json, os, sys; BASE='$baseUrl'; KEY='$apiKey'; MODEL='$defaultModel'; print('=== 🚀 GROK 4.6 AI DA KET NOI (Go quit de thoat, /clear de xoa chat) ===\n');\
while True:\
    try:\
        q = input('👤 Ban: ');\
    except (EOFError, KeyboardInterrupt):\
        print('\nTam biet!'); break;\
    if q.lower() in ['quit', 'exit']: break;\
    if not q.strip(): continue;\
    if q.lower() in ['/clear', '/cls', '/reset', '/new']:\
        os.system('cls');\
        print('=== 🚀 GROK 4.6 AI DA KET NOI (Go quit de thoat, /clear de xoa chat) ===\n'); continue;\
    if q.startswith('/model '):\
        MODEL = q.split(' ', 1)[1].strip();\
        print(f'⚡ Da doi sang model: {{MODEL}}\n'); continue;\
    try:\
        msgs = [{{'role': 'system', 'content': 'You are Grok 4.6, the latest flagship AI developed by xAI. You are extremely intelligent, fast, and helpful.'}}, {{'role': 'user', 'content': q}}];\
        req = urllib.request.Request(f'{{BASE}}/chat/completions', headers={{'Authorization': f'Bearer {{KEY}}', 'Content-Type': 'application/json'}}, data=json.dumps({{'model': MODEL, 'messages': msgs, 'stream': True}}).encode('utf-8'));\
        print(f'🤖 Grok 4.6: ', end='', flush=True);\
        with urllib.request.urlopen(req, timeout=90) as resp:\
            for line in resp:\
                l = line.decode('utf-8').strip();\
                if not l or not l.startswith('data:'): continue;\
                d = l[5:].strip();\
                if d == '[DONE]': break;\
                try:\
                    c = json.loads(d).get('choices',[{{}}])[0].get('delta',{{}}).get('content','');\
                    if c: print(c, end='', flush=True);\
                except: pass;\
        print('\n')\
    except Exception as e: print(f'\nLoi: {{e}}\n')\
"
pause
"@

Set-Content -Path $batPath -Value $chatScript -Encoding UTF8
Write-Host "[OK] Da tao icon 'Chat_Grok.bat' tren Desktop!" -ForegroundColor Green

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "🎉 CAI DAT HOAN TAT 100%! Ban co the mo Codex Desktop App hoac Chatbot ngay!" -ForegroundColor Yellow
"""

def generate_codex_bash_script(key: str, default_model: str, small_model: str, medium_model: str, large_model: str) -> str:
    base = BASE_URL
    return f"""#!/usr/bin/env bash
# Grok API & Codex 1-Click Auto Setup Script for Linux / macOS
set -e

API_KEY="{key}"
BASE_URL="{base}"
DEFAULT_MODEL="{default_model}"
SMALL_MODEL="{small_model}"
MEDIUM_MODEL="{medium_model}"
LARGE_MODEL="{large_model}"

echo -e "\\033[1;36m============================================================\\033[0m"
echo -e "\\033[1;33m   ⚡ GROK API & CODEX 1-CLICK AUTO SETUP (LINUX / MACOS)\\033[0m"
echo -e "\\033[1;36m============================================================\\033[0m"

if [ -z "$API_KEY" ]; then
    echo -e "\\033[1;31m[!] Loi: Thieu API Key trong duong dan cai dat.\\033[0m"
    exit 1
fi

# 1. Configure Shell RC files
SHELL_FILES=("$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile")
ENV_BLOCK="
# Grok API & Grok Build Environment Variables
export XAI_API_KEY=\"$API_KEY\"
export XAI_API_BASE_URL=\"$BASE_URL\"
export GROK_XAI_API_BASE_URL=\"$BASE_URL\"
export GROK_MODELS_BASE_URL=\"$BASE_URL\"
export GROK_DEPLOYMENT_KEY=\"$API_KEY\"
export OPENAI_BASE_URL=\"$BASE_URL\"
export OPENAI_API_KEY=\"$API_KEY\"
export CODEX_API_KEY=\"$API_KEY\"
"

for rc in "${{SHELL_FILES[@]}}"; do
    if [ -f "$rc" ]; then
        grep -v "OPENAI_BASE_URL" "$rc" | grep -v "OPENAI_API_KEY" | grep -v "CODEX_API_KEY" | grep -v "XAI_BASE_URL" | grep -v "XAI_API_KEY" > "$rc.tmp" 2>/dev/null || true
        mv "$rc.tmp" "$rc" 2>/dev/null || true
        echo "$ENV_BLOCK" >> "$rc"
    elif [ "$rc" = "$HOME/.bashrc" ]; then
        echo "$ENV_BLOCK" >> "$rc"
    fi
done

echo -e "\\033[1;32m[OK] Da thiet lap API Gateway thanh cong!\\033[0m"

# 2. Configure Codex Desktop & CLI (~/.codex)
CODEX_DIR="$HOME/.codex"
mkdir -p "$CODEX_DIR"

cat <<EOF > "$CODEX_DIR/config.toml"
model_provider = "grok"
model = "$DEFAULT_MODEL"
model_small = "$SMALL_MODEL"
model_medium = "$MEDIUM_MODEL"
model_large = "$LARGE_MODEL"

[model_providers.grok]
name = "Grok API"
base_url = "$BASE_URL"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
EOF

cat <<EOF > "$CODEX_DIR/auth.json"
{{
  "OPENAI_API_KEY": "$API_KEY",
  "CODEX_API_KEY": "$API_KEY",
  "api_key": "$API_KEY",
  "grok": {{
    "api_key": "$API_KEY"
  }}
}}
EOF

echo -e "\\033[1;32m[OK] Da tu dong cau hinh ~/.codex/config.toml cho Codex Desktop App!\\033[0m"

# Configure Grok Build CLI (~/.grok)
GROK_DIR="$HOME/.grok"
mkdir -p "$GROK_DIR"

cat <<EOF > "$GROK_DIR/config.toml"
[models]
default = "grok-4.6"

[model.grok-4.6]
model = "$DEFAULT_MODEL"
base_url = "$BASE_URL"
name = "Grok 4.6 Flagship"
env_key = "XAI_API_KEY"

[model.grok-2]
model = "grok-2"
base_url = "$BASE_URL"
name = "Grok 2 Flash"
env_key = "XAI_API_KEY"
EOF

cat <<EOF > "$GROK_DIR/auth.json"
{{
  "OPENAI_API_KEY": "$API_KEY",
  "XAI_API_KEY": "$API_KEY",
  "api_key": "$API_KEY"
}}
EOF
echo -e "\\033[1;32m[OK] Da tu dong cau hinh ~/.grok/config.toml cho Grok Build CLI!\\033[0m"

# 3. Create quick real-time streaming test chat command ~/chat_grok
cat <<EOF > "$HOME/chat_grok"
#!/usr/bin/env python3
import urllib.request, json, os, sys

BASE = os.environ.get("OPENAI_BASE_URL", "$BASE_URL")
KEY = os.environ.get("OPENAI_API_KEY", "$API_KEY")
MODEL = "$DEFAULT_MODEL"

print("=== 🚀 GROK 4.6 AI DA KET NOI (Go quit de thoat, /clear de xoa chat) ===\\n")
while True:
    try:
        q = input("👤 Ban: ")
    except (EOFError, KeyboardInterrupt):
        print("\\nTam biet!")
        break
    if q.lower() in ["quit", "exit"]:
        break
    if not q.strip():
        continue
    if q.lower() in ["/clear", "/cls", "/reset", "/new"]:
        os.system("clear")
        print("=== 🚀 GROK 4.6 AI DA KET NOI (Go quit de thoat, /clear de xoa chat) ===\\n")
        continue
    if q.startswith("/model "):
        MODEL = q.split(" ", 1)[1].strip()
        print(f"⚡ Da doi sang model: {{MODEL}}\\n")
        continue
    
    try:
        msgs = [
            {{"role": "system", "content": "You are Grok 4.6, the latest flagship AI developed by xAI. You are extremely intelligent, fast, and helpful."}},
            {{"role": "user", "content": q}}
        ]
        req = urllib.request.Request(
            f"{{BASE}}/chat/completions",
            headers={{"Authorization": f"Bearer {{KEY}}", "Content-Type": "application/json"}},
            data=json.dumps({{"model": MODEL, "messages": msgs, "stream": True}}).encode("utf-8")
        )
        
        print(f"🤖 Grok 4.6: ", end="", flush=True)
        with urllib.request.urlopen(req, timeout=90) as resp:
            for line in resp:
                l = line.decode("utf-8").strip()
                if not l or not l.startswith("data:"):
                    continue
                d = l[5:].strip()
                if d == "[DONE]":
                    break
                try:
                    c = json.loads(d).get("choices", [{{}}])[0].get("delta", {{}}).get("content", "")
                    if c:
                        print(c, end="", flush=True)
                except Exception:
                    pass
        print("\\n")
    except Exception as e:
        print(f"\\nLoi: {{e}}\\n")
EOF
chmod +x "$HOME/chat_grok" 2>/dev/null || true

# Add alias grok so user can simply type 'grok' in WSL/Linux terminal
if ! grep -q 'alias grok=' "$HOME/.bashrc" 2>/dev/null; then
    echo "alias grok=\"\$HOME/chat_grok\"" >> "$HOME/.bashrc"
fi
if [ -f "$HOME/.zshrc" ] && ! grep -q 'alias grok=' "$HOME/.zshrc" 2>/dev/null; then
    echo "alias grok=\"\$HOME/chat_grok\"" >> "$HOME/.zshrc"
fi
mkdir -p "$HOME/.local/bin" 2>/dev/null || true
cp "$HOME/chat_grok" "$HOME/.local/bin/grok" 2>/dev/null || true
chmod +x "$HOME/.local/bin/grok" 2>/dev/null || true

echo -e "\\033[1;36m============================================================\\033[0m"
echo -e "\\033[1;33m🎉 CAI DAT HOAN TAT 100% TREN WSL / LINUX / MACOS!\\033[0m"
echo -e "\\033[1;37m👉 De ap dung ngay, go lenh: \\033[1;32msource ~/.bashrc\\033[0m"
echo -e "\\033[1;37m👉 Bat dau chat ngay bang cach go chu: \\033[1;32mgrok\\033[0m"
"""

class PortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        
        if path in ("/check", "/balance"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if path == "/api/check-key":
            key = qs.get("key", [""])[0]
            data = query_key_info(key)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path in ("/setup-windows", "/setup-codex-windows", "/api/v1/setup-codex-windows"):
            key = qs.get("key", [""])[0]
            model = qs.get("model", ["grok-4.6"])[0]
            small = qs.get("small", ["grok-4.6"])[0]
            medium = qs.get("medium", ["grok-4.6"])[0]
            large = qs.get("large", ["grok-4.6"])[0]
            
            ps_script = generate_codex_ps_script(key, model, small, medium, large)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(ps_script.encode("utf-8"))
            return

        if path in ("/setup-linux", "/setup-codex-linux", "/api/v1/setup-codex-linux", "/setup-mac"):
            key = qs.get("key", [""])[0]
            model = qs.get("model", ["grok-4.6"])[0]
            small = qs.get("small", ["grok-4.6"])[0]
            medium = qs.get("medium", ["grok-4.6"])[0]
            large = qs.get("large", ["grok-4.6"])[0]
            
            bash_script = generate_codex_bash_script(key, model, small, medium, large)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(bash_script.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), PortalHandler)
    print(f"Portal running on port {PORT}")
    server.serve_forever()
