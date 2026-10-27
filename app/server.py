import asyncio
import logging
import os
import shutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.auth import auth_manager, check_auth_async
from app.routes.chat import router as chat_router
from app.routes.models import router as models_router
from app.routes.auth import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("proxy_agy.server")

app = FastAPI(
    title="Antigravity CLI OpenAI-Compatible Proxy",
    description="Local proxy service providing OpenAI-compatible API endpoints for agy CLI capabilities.",
    version="1.0.0",
)

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(chat_router)
app.include_router(models_router)
app.include_router(auth_router)


@app.on_event("startup")
async def startup_event():
    """Run non-blocking initial CLI authentication status check on startup."""
    asyncio.create_task(check_auth_async(force_recheck=False))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    agy_exists = os.path.isfile(settings.AGY_BIN_PATH) and os.access(settings.AGY_BIN_PATH, os.X_OK)
    is_auth = await check_auth_async(force_recheck=False)
    return {
        "status": "ok" if (agy_exists and is_auth) else ("unauthenticated" if not is_auth else "warning"),
        "service": "agy-openai-proxy",
        "agy_bin": settings.AGY_BIN_PATH,
        "agy_installed": agy_exists,
        "authenticated": is_auth,
        "default_model": settings.DEFAULT_MODEL,
        "default_effort": settings.DEFAULT_EFFORT,
    }


@app.get("/", response_class=HTMLResponse)
async def home_page():
    """Dashboard page showing status, dynamic PKCE OAuth web login, and interactive test chat."""
    agy_exists = os.path.isfile(settings.AGY_BIN_PATH) and os.access(settings.AGY_BIN_PATH, os.X_OK)
    is_auth = auth_manager.is_authenticated

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity CLI OpenAI Proxy</title>
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: #151d30;
            --card-border: #243049;
            --text: #f1f5f9;
            --text-dim: #94a3b8;
            --primary: #38bdf8;
            --primary-hover: #0ea5e9;
            --accent: #818cf8;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --code-bg: #070a12;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px 16px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            max-width: 920px;
            width: 100%;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        h1 {{
            font-size: 24px;
            margin: 0;
            background: linear-gradient(90deg, var(--primary), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header-actions {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        }}
        .auth-card {{
            border-color: var(--warning);
            background: linear-gradient(180deg, rgba(245, 158, 11, 0.08) 0%, var(--card-bg) 100%);
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: #fff;
            padding: 9px 16px;
            font-size: 13.5px;
            font-weight: 600;
            border-radius: 8px;
            text-decoration: none;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none; }}
        .btn-success {{ background: linear-gradient(135deg, #059669, #10b981); }}
        .btn-secondary {{ background: #334155; color: #f8fafc; }}
        .btn-secondary:hover {{ background: #475569; }}
        .input-group {{
            display: flex;
            gap: 10px;
            margin-top: 12px;
        }}
        input[type="text"], textarea, select {{
            flex: 1;
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            color: #fff;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 14px;
            outline: none;
            font-family: inherit;
        }}
        input[type="text"]:focus, textarea:focus, select:focus {{
            border-color: var(--primary);
        }}
        .status-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 13.5px;
        }}
        .status-row:last-child {{ margin-bottom: 0; }}
        .label {{ color: var(--text-dim); }}
        .value {{ font-family: monospace; font-weight: 600; }}
        pre {{
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 14px;
            overflow-x: auto;
            color: #38bdf8;
            font-size: 13px;
            line-height: 1.5;
            margin: 8px 0 0 0;
        }}
        .badge {{
            background: #0369a1;
            color: #fff;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 12px;
            font-family: monospace;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            margin: 20px 0 10px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .chat-output {{
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 14px;
            min-height: 120px;
            max-height: 380px;
            overflow-y: auto;
            font-size: 14px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-word;
            margin-top: 10px;
        }}
        .reasoning-box {{
            background: rgba(129, 140, 248, 0.08);
            border-left: 3px solid var(--accent);
            padding: 8px 12px;
            margin-bottom: 10px;
            font-size: 13px;
            color: #c7d2fe;
            border-radius: 0 6px 6px 0;
            display: none;
        }}
        .url-box {{
            background: var(--code-bg);
            border: 1px dashed var(--warning);
            border-radius: 8px;
            padding: 10px 14px;
            margin-top: 10px;
            font-size: 12px;
            color: #fde047;
            word-break: break-all;
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🚀 Antigravity CLI OpenAI Proxy</h1>
                <div style="font-size: 13px; color: var(--text-dim); margin-top: 4px;">
                    本地 OpenAI API 兼容中转服务 (动态 PKCE 认证管理)
                </div>
            </div>
            <div class="header-actions">
                <button class="btn btn-secondary" onclick="toggleAuthPanel()">🔐 网页端登录 / 重新认证</button>
            </div>
        </header>
        
        <!-- 登录面板 (动态 PKCE 交互) -->
        <div id="auth-panel" class="card auth-card" style="display: {'block' if not is_auth else 'none'};">
            <div style="font-size: 16px; font-weight: bold; color: var(--warning); margin-bottom: 6px;">
                🔐 Antigravity CLI 授权登录
            </div>
            <div style="font-size: 13.5px; color: var(--text-dim); line-height: 1.5;">
                由于 Antigravity CLI 采用 OAuth2 PKCE 安全协议，系统将实时生成专属授权链接：
            </div>
            
            <div style="margin-top: 14px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                <button class="btn" id="fetch-url-btn" onclick="fetchDynamicLoginUrl()">
                    🔗 1. 点击生成并打开 Google 授权登录页
                </button>
                <span style="font-size: 13px; color: var(--text-dim);" id="url-status-hint">（点击后将在新标签页打开授权页）</span>
            </div>

            <div id="generated-url-box" class="url-box"></div>

            <div style="margin-top: 16px; font-size: 13px; color: var(--text-dim);">
                2. 完成网页授权后，将页面返回的 <b>Authorization Code</b> 粘贴在下方：
            </div>
            <div class="input-group">
                <input type="text" id="token-input" placeholder="在此粘贴 Authorization Code (例如：4/0AdQt8...)..." />
                <button class="btn btn-success" id="submit-token-btn" onclick="submitToken()">🚀 提交 Code 激活服务</button>
            </div>
            <div id="login-feedback" style="margin-top: 10px; font-size: 13.5px;"></div>
        </div>

        <!-- 服务状态卡片 -->
        <div class="card">
            <div class="status-row">
                <span class="label">服务状态:</span>
                <span class="value" id="status-badge">
                    {'<span style="color:var(--success)">● Ready (已就绪)</span>' if is_auth else '<span style="color:var(--warning)">● 待登录激活</span>'}
                </span>
            </div>
            <div class="status-row">
                <span class="label">API Base URL:</span>
                <span class="value" style="color: var(--primary);">http://127.0.0.1:{settings.PORT}/v1</span>
            </div>
            <div class="status-row">
                <span class="label">默认模型:</span>
                <span class="value">{settings.DEFAULT_MODEL}</span>
            </div>
            <div class="status-row">
                <span class="label">CLI 可执行路径:</span>
                <span class="value">{settings.AGY_BIN_PATH}</span>
            </div>
        </div>

        <!-- 网页端测试对话窗口 -->
        <div class="card">
            <div class="section-title">💬 网页端在线对话测试 (Playground)</div>
            <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                <select id="chat-model" style="max-width: 260px;">
                    <option value="gemini-4-argon">gemini-4-argon (Gemini 4 Argon)</option>
                    <option value="gemini-3.8-flash" selected>gemini-3.8-flash (Gemini 3.8 Flash High)</option>
                    <option value="gemini-3.8-flash-low">gemini-3.8-flash-low (Rapide)</option>
                    <option value="claude-sonnet-4-6">claude-sonnet-4-6 (Claude)</option>
                    <option value="gpt-oss">gpt-oss (GPT-OSS 120B)</option>
                </select>
                <input type="text" id="chat-input" placeholder="输入你想测试的问题..." value="用一句话简单问好" />
                <button class="btn" id="send-btn" onclick="sendTestChat()">发送</button>
            </div>

            <div id="reasoning-box" class="reasoning-box"></div>
            <div id="chat-output" class="chat-output">等待发送测试消息...</div>
        </div>

        <!-- 快速调用示例 -->
        <div class="card">
            <div class="section-title">📡 常用客户端接入说明</div>
            <div style="font-size: 13.5px; color: var(--text-dim); margin-bottom: 10px;">
                在 <b>Cherry Studio</b> / <b>NextChat</b> / <b>OpenWebUI</b> / <b>Cursor</b> 等工具中配置：
            </div>
            <pre><code>Base URL : http://127.0.0.1:{settings.PORT}/v1
API Key  : none (或任意填写)
Models   : gemini-3.7-flash, gemini-3.1-pro, claude-3-7-sonnet, gpt-4o</code></pre>
        </div>
    </div>

    <script>
        let currentAuthUrl = null;

        function toggleAuthPanel() {{
            const panel = document.getElementById('auth-panel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }}

        async function fetchDynamicLoginUrl() {{
            const btn = document.getElementById('fetch-url-btn');
            const hint = document.getElementById('url-status-hint');
            const urlBox = document.getElementById('generated-url-box');

            btn.disabled = true;
            btn.innerText = '⏳ 正在启动 CLI 进程获取实时 OAuth 链接...';
            hint.innerText = '正在与本地 agy CLI 建立 PKCE 交互会话...';

            try {{
                const res = await fetch('/v1/auth/session', {{ method: 'POST' }});
                const data = await res.json();
                if (res.ok && data.login_url) {{
                    currentAuthUrl = data.login_url;
                    urlBox.style.display = 'block';
                    urlBox.innerHTML = '👉 <b>授权链接:</b> <a href="' + currentAuthUrl + '" target="_blank" style="color:var(--primary)">' + currentAuthUrl + '</a>';
                    window.open(currentAuthUrl, '_blank');
                    btn.innerText = '🔗 重新打开 Google 授权页';
                    hint.innerText = '✅ 已在新标签页打开授权页，请在授权后复制 Code 粘贴至下方输入框';
                }} else {{
                    hint.innerText = '❌ 获取链接失败: ' + (data.detail?.message || data.message || '未知错误');
                    btn.innerText = '重试生成授权链接';
                }}
            }} catch (e) {{
                hint.innerText = '❌ 请求异常: ' + e.message;
                btn.innerText = '重试生成授权链接';
            }} finally {{
                btn.disabled = false;
            }}
        }}

        async function submitToken() {{
            const input = document.getElementById('token-input');
            const feedback = document.getElementById('login-feedback');
            const btn = document.getElementById('submit-token-btn');
            const code = input.value.trim();
            
            if (!code) {{
                feedback.innerHTML = '<span style="color:var(--danger)">⚠️ 请先输入获取到的 Authorization Code</span>';
                return;
            }}

            btn.disabled = true;
            btn.innerText = '正在向 CLI 写入 Code 进行 Token 交换...';
            feedback.innerHTML = '<span style="color:var(--primary)">⏳ 正在与 Google 交换 Token 并保存凭据...</span>';

            try {{
                const res = await fetch('/v1/auth/login', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{code: code}})
                }});
                const data = await res.json();
                if (res.ok) {{
                    feedback.innerHTML = '<span style="color:var(--success)">🎉 登录成功！Antigravity CLI 凭据已持久化，服务已就绪。</span>';
                    document.getElementById('status-badge').innerHTML = '<span style="color:var(--success)">● Ready (已就绪)</span>';
                    setTimeout(() => {{
                        document.getElementById('auth-panel').style.display = 'none';
                    }}, 2000);
                }} else {{
                    feedback.innerHTML = '<span style="color:var(--danger)">❌ 验证失败: ' + (data.detail?.message || data.message || 'Code 无效或会话已过期') + '</span>';
                }}
            }} catch (err) {{
                feedback.innerHTML = '<span style="color:var(--danger)">❌ 请求异常: ' + err.message + '</span>';
            }} finally {{
                btn.disabled = false;
                btn.innerText = '🚀 提交 Code 激活服务';
            }}
        }}

        async function sendTestChat() {{
            const input = document.getElementById('chat-input');
            const modelSelect = document.getElementById('chat-model');
            const output = document.getElementById('chat-output');
            const reasoningBox = document.getElementById('reasoning-box');
            const sendBtn = document.getElementById('send-btn');
            const text = input.value.trim();

            if (!text) return;

            sendBtn.disabled = true;
            sendBtn.innerText = '生成中...';
            output.innerText = '正在连接流式响应...\\n';
            reasoningBox.style.display = 'none';
            reasoningBox.innerText = '';

            try {{
                const response = await fetch('/v1/chat/completions', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        model: modelSelect.value,
                        messages: [{{role: 'user', content: text}}],
                        stream: true
                    }})
                }});

                if (!response.ok) {{
                    const errData = await response.json();
                    output.innerText = '❌ 请求失败: ' + JSON.stringify(errData, null, 2);
                    sendBtn.disabled = false;
                    sendBtn.innerText = '发送';
                    return;
                }}

                output.innerText = '';
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let accumulatedText = '';
                let accumulatedReasoning = '';

                while (true) {{
                    const {{done, value}} = await reader.read();
                    if (done) break;

                    const chunkStr = decoder.decode(value, {{stream: true}});
                    const lines = chunkStr.split('\\n');

                    for (const line of lines) {{
                        const trimmed = line.trim();
                        if (trimmed.startsWith('data: ')) {{
                            const dataStr = trimmed.substring(6);
                            if (dataStr === '[DONE]') break;
                            try {{
                                const json = JSON.parse(dataStr);
                                const delta = json.choices[0]?.delta || {{}};
                                if (delta.reasoning_content) {{
                                    accumulatedReasoning += delta.reasoning_content;
                                    reasoningBox.style.display = 'block';
                                    reasoningBox.innerText = '🧠 思考过程:\\n' + accumulatedReasoning;
                                }}
                                if (delta.content) {{
                                    accumulatedText += delta.content;
                                    output.innerText = accumulatedText;
                                }}
                            }} catch(e) {{}}
                        }}
                    }}
                }}
            }} catch (err) {{
                output.innerText = '❌ 发生异常: ' + err.message;
            }} finally {{
                sendBtn.disabled = false;
                sendBtn.innerText = '发送';
            }}
        }}

        document.getElementById('chat-input').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter') sendTestChat();
        }});
        document.getElementById('token-input').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter') submitToken();
        }});
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
