# Antigravity CLI OpenAI-Compatible Proxy (AGY 本地中转服务)

这是一个运行在本地的高性能 Python 中转服务，将 Google Antigravity CLI (`agy`) 的强大能力封装为标准的 **OpenAI 兼容 API 接口** (`/v1/chat/completions`, `/v1/models` 等)。

有了这个中转服务，你可以直接在任何支持自定义 OpenAI API 的客户端（如 **Cherry Studio**, **NextChat**, **OpenWebUI**, **Cursor**, **Chatbox**, **LibreChat**, **Dify**, **LangChain**, **LlamaIndex** 以及官方 **OpenAI Python SDK**）中直接使用 `agy` CLI 驱动的模型和能力！

---

## 🌟 核心特性

- ⚡ **完全兼容 OpenAI 标准协议**:
  - `POST /v1/chat/completions`: 支持单轮/多轮对话，支持 **流式传输 (Stream SSE)** 与 **非流式 JSON** 返回。
  - `GET /v1/models` & `GET /v1/models/{model}`: 自动列出支持的模型及友好别名。
  - `POST /v1/completions`: 兼容旧版纯文本补全端点。
- 🔐 **开箱即用的登录引导 (Auth Flow)**:
  - 新用户初次启动时，若检测到未登录，自动提供 **终端交互登录** 或 **网页端可视化一键粘贴 Token 激活**。
  - 支持 `python3 main.py --login` 或 `./start.sh login` 随时触发重新登录。
- 🧠 **思考过程与推理流支持 (Reasoning / Thinking)**:
  - 自动将 `agy` 产生的 thinking 过程通过标准 `delta.reasoning_content` (DeepSeek-R1 / o1 / o3 格式) 实时流式推送至前端渲染。
- 🔄 **智能模型映射 & 别名**:
  - 支持直接输入标准别名（如 `gemini-3.7-flash`, `gemini-3.1-pro`, `claude-3-7-sonnet`, `gpt-4o` 等），自动映射到 `agy` 对应的原生模型全称。
- 🛡️ **异步高性能 & 进程保护**:
  - 基于 FastAPI + Asyncio 异步子进程，低延迟流式响应；客户端断开连接时自动终止后台 CLI 进程，杜绝进程泄漏。
- 💬 **会话连续性 (Conversation Continuity)**:
  - 支持通过 `X-Conversation-Id` Header 或请求体中的 `conversation_id` 继承复用 CLI 的历史会话。

---

## 📂 项目结构

```
proxy-agy/
├── app/
│   ├── __init__.py
│   ├── auth.py          # 认证检测、终端交互与 Token 验证
│   ├── config.py        # 配置管理与模型别名映射
│   ├── schemas.py       # OpenAI 请求与响应 Pydantic 模型
│   ├── agy_adapter.py   # agy CLI 异步子进程与流式解析适配器
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py      # /v1/auth/status 与 /v1/auth/login 路由
│   │   ├── chat.py      # /v1/chat/completions 路由（带未登录拦截保护）
│   │   └── models.py    # /v1/models 路由
│   └── server.py        # FastAPI 实例、CORS 中间件与 Web 登录/状态面板
├── main.py              # 命令行启动入口（支持 --login, --check-auth 等）
├── start.sh             # 便捷服务管理脚本（start, stop, status, login）
├── test_client.py       # 测试客户端脚本
├── requirements.txt     # 依赖项清单
├── .env.example         # 环境变量示例
└── README.md            # 使用文档
```

---

## 🚀 快速启动与登录

### 1. 安装依赖

确保本地已安装 Python 3.9+ 以及 `agy` 命令行工具：

```bash
cd /Users/xm15118057/tyre/proxy-agy
pip install -r requirements.txt
```

### 2. 启动服务

**直接运行：**
```bash
python3 main.py
```

- 若你是**全新用户尚未登录**：
  - 终端将提示进入交互式登录，自动打开浏览器登录链接，并在终端粘贴 Token 完成授权。
  - 或者直接访问网页 `http://127.0.0.1:8000/` 点击授权链接并粘贴 Token 一键激活！

### 3. 服务管理命令 (`./start.sh`)

| 操作 | 命令 | 说明 |
| :--- | :--- | :--- |
| **后台启动** | `./start.sh start` | 在后台静默运行中转服务 |
| **前台调试启动** | `./start.sh` 或 `python3 main.py` | 在前台运行并输出完整日志 |
| **交互式登录** | `./start.sh login` | 专门进入 Antigravity CLI 登录引导 |
| **检查登录状态** | `./start.sh check-auth` | 检查当前 CLI 是否处于登录状态 |
| **查看服务状态** | `./start.sh status` | 检查后台服务 PID 与 Base URL |
| **查看实时日志** | `./start.sh logs` | 跟踪 `proxy.log` 日志输出 |
| **停止后台服务** | `./start.sh stop` | 停止后台运行的代理进程 |
| **重启后台服务** | `./start.sh restart` | 平滑重启服务 |

---

## 📋 支持的模型与别名对照

| 请求使用的 Model 别名 | 实际映射的 AGY CLI 模型 | 特性说明 |
| :--- | :--- | :--- |
| `gemini-3.7-flash` / `gemini-3.7-flash-high` | `Gemini 3.7 Flash (High)` | 默认推荐，速度极快且具备深度思考 |
| `gemini-3.7-flash-medium` | `Gemini 3.7 Flash (Medium)` | 中度思考预算 |
| `gemini-3.7-flash-low` | `Gemini 3.7 Flash (Low)` | 低延迟轻量推理 |
| `gemini-3.6-flash` | `Gemini 3.6 Flash (High)` | Gemini 3.6 系列 |
| `gemini-3.5-flash` | `Gemini 3.5 Flash (High)` | Gemini 3.5 系列 |
| `gemini-3.1-pro` / `gemini-pro` | `Gemini 3.1 Pro (High)` | 复杂代码与强逻辑推理 |
| `claude-3-7-sonnet` / `claude-sonnet` | `Claude Sonnet 4.6 (Thinking)` | 包含深度 Thinking 链路 |
| `claude-3-opus` / `claude-opus` | `Claude Opus 4.6 (Thinking)` | 深度理解与写作 |
| `gpt-4o` / `gpt-oss` / `gpt-oss-120b` | `GPT-OSS 120B (Medium)` | 开源百亿级大模型 |

---

## 💻 接入客户端指南

### 1. Python (OpenAI SDK)

```python
from openai import OpenAI

# 将 base_url 指向本地中转服务
client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="none"  # 未开启 --api-key 时可填任意非空字符串
)

# 流式调用
response = client.chat.completions.create(
    model="gemini-3.7-flash",
    messages=[
        {"role": "system", "content": "You are a professional software architect."},
        {"role": "user", "content": "用Python写一个简单的异步HTTP服务器"}
    ],
    stream=True
)

for chunk in response:
    delta = chunk.choices[0].delta
    # 打印思考过程（若客户端支持）
    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
        print(f"[思考] {delta.reasoning_content}", end="", flush=True)
    # 打印正文内容
    if delta.content:
        print(delta.content, end="", flush=True)
```

### 2. cURL 调用

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.7-flash",
    "messages": [
      {"role": "user", "content": "你好，请写一个快速排序。"}
    ],
    "stream": true
  }'
```

### 3. Cherry Studio / NextChat / OpenWebUI / Cursor 配置

- **接口类型**: `OpenAI`
- **Base URL**: `http://127.0.0.1:8000/v1`
- **API Key**: 留空或填写 `sk-none`
- **模型**: `gemini-3.7-flash`, `gemini-3.1-pro`, `claude-3-7-sonnet`, `gpt-4o` 等。

---

## 🧪 运行测试

```bash
python3 test_client.py
```

将依次测试：
1. 认证状态检查 (`/v1/auth/status`)
2. 可用模型列表获取 (`/v1/models`)
3. 非流式单轮对话 (`/v1/chat/completions`)
4. 流式传输与 Token 输出 (SSE)

---

## 🚢 Multi-Instance & LiteLLM / OpenClaw Deployment

Pour déployer en production avec équilibrage de charge et haute disponibilité (ex: pour OpenClaw via LiteLLM) :

### 1. Services Systemd Multi-Instances
Deux services d'arrière-plan distincts tournent sur les ports `8000` et `8001` avec des environnements isolés :
```bash
sudo cp deploy/proxy-agy-1.service /etc/systemd/system/
sudo cp deploy/proxy-agy-2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxy-agy-1 proxy-agy-2
```

### 2. Routeur LiteLLM
Le fichier `deploy/litellm_config.yaml` configure la répartition de charge (`simple-shuffle`), la gestion des timeouts et les fallbacks automatiques :
```yaml
router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  fallbacks:
    - gemini-4-argon: ["gemini-3.8-flash"]
    - gemini-4-argon-high: ["gemini-3.8-flash"]
```

### 3. OpenClaw
Dans `openclaw.json`, configurez le provider OpenAI pointant sur le port LiteLLM (4001) :
```json
{
  "models": {
    "providers": {
      "openai": {
        "baseUrl": "http://127.0.0.1:4001/v1",
        "apiKey": "sk-dummy"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gemini-3.8-flash"
    }
  }
}
```

---

## 📄 License
MIT License
