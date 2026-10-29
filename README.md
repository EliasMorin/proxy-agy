# Proxy-AGY — Passerelle OpenAI Haute Performance pour Antigravity CLI (`agy`)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-412991.svg)](https://platform.openai.com/docs/api-reference)
[![OpenClaw Ready](https://img.shields.io/badge/agent-OpenClaw%20Ready-ff4757.svg)](https://openclaw.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Proxy-AGY** est une passerelle Python asynchrone haute performance encapsulant le CLI **Google Antigravity (`agy`)** sous forme d'une API standard **compatible OpenAI** (`/v1/chat/completions`, `/v1/models`).

Conçu pour alimenter des agents autonomes comme **OpenClaw**, des routeurs de modèles comme **LiteLLM**, ainsi que des interfaces utilisateur (Webchat, Cursor, LibreChat, NextChat, Dify), il assure une diffusion fluide en continu (SSE), la transmission en direct des traces de raisonnement (*thinking tokens*), et une haute disponibilité via un cluster multi-instances.

---

## 🏗️ Architecture Globale

```
┌─────────────────────────────────────────────────────────────┐
│ Clients : OpenClaw (Gateway / Webchat), Cursor, NextChat... │
└──────────────────────────────┬──────────────────────────────┘
                               │  Requêtes OpenAI v1
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 LiteLLM Proxy (Port 4001)                   │
│         Load Balancing round-robin & Fallbacks auto         │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
    HTTP :8000  ▼                 HTTP :8001  ▼
┌───────────────────────────────┐ ┌───────────────────────────────┐
│     Proxy-AGY Instance 1      │ │     Proxy-AGY Instance 2      │
│     (HOME=/opt/.../env1)      │ │     (HOME=/opt/.../env2)      │
└───────────────┬───────────────┘ └───────────────┬───────────────┘
                │ IPC Subprocess                  │ IPC Subprocess
                ▼                                 ▼
┌───────────────────────────────┐ ┌───────────────────────────────┐
│     agy CLI (Google Auth 1)   │ │     agy CLI (Google Auth 2)   │
└───────────────────────────────┘ └───────────────────────────────┘
```

---

## ✨ Fonctionnalités Clés

- **⚡ Compatibilité Totale OpenAI REST & SSE :**
  - Endpoint `POST /v1/chat/completions` avec support complet du streaming Server-Sent Events (`stream: true`) et du mode synchrone JSON.
  - Endpoint `GET /v1/models` dynamique exposant les modèles officiels disponibles sur le palier de compte (`Gemini 3.8 Flash`, `Claude Sonnet 4.6`, `Claude Opus 4.6`, `GPT-OSS 120B`, etc.).
- **🧠 Support Intégral du Raisonnement (*Reasoning / Thinking Tokens*) :**
  - Transmission des réflexions en temps réel via le standard `delta.reasoning_content` (supporté nativement par OpenClaw, DeepSeek-R1, o1/o3 et Ollama).
  - Mode hybride avec balises `<think>...</think>` activable à la demande.
- **🛡️ Tampon Pipe Haute Capacité (16 Mo) :**
  - Dépassement de la limite standard Python `asyncio` (64 Ko) avec un buffer de 16 Mo pour garantir l'absence de saturation ou de gel lors de réponses denses (code volumineux, traces d'analyse complexes).
- **🔄 Cluster Multi-Instance & Zero-Downtime :**
  - Déploiement parallélisé sur plusieurs environnements distincts (`env1`, `env2`) avec leurs propres sessions et jetons Google.
  - Répartition de charge automatique via LiteLLM avec bascule transparente (*fallbacks*).
- **🔒 Directive Pure LLM :**
  - Injection automatique de garde-fous interdisant au moteur CLI local de spawner des navigateurs graphiques ou des commandes bash intempestives lors d'appels API.
- **🛡️ Nettoyage Propre des Processus (Anti-Leak) :**
  - Annulation immédiate (`SIGTERM` puis `SIGKILL`) de l'arbre complet de sous-processus `agy` dès que le client ferme sa connexion HTTP, éliminant les processus zombies.

---

## 🚀 Démarrage Rapide

### 1. Prérequis
- Python 3.10 ou supérieur
- Google Antigravity CLI (`agy`) installé et connecté (`agy auth login`)

### 2. Installation

```bash
git clone https://github.com/EliasMorin/proxy-agy.git
cd proxy-agy
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Lancement Unique (Mode Simple)

```bash
# Lancement direct sur le port 8000
./start.sh run
```

Accédez au tableau de bord et à l'interface de test Playground sur `http://localhost:8000`.

---

## 🏛️ Déploiement en Production (Cluster Multi-Instance)

Pour un usage intensif avec **OpenClaw**, il est recommandé d'exécuter deux instances isolées supervisées par `systemd` derrière **LiteLLM**.

### 1. Scripts de démarrage (`systemd`)

Copiez les unités systemd fournies dans [`deploy/`](./deploy/) vers `/etc/systemd/system/` :

```bash
sudo cp deploy/proxy-agy-1.service /etc/systemd/system/
sudo cp deploy/proxy-agy-2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxy-agy-1.service proxy-agy-2.service
```

### 2. Configuration LiteLLM

Lancez le conteneur LiteLLM avec le fichier [`deploy/litellm_config.yaml`](./deploy/litellm_config.yaml) :

```bash
docker run -d \
  --name litellm \
  -p 4001:4000 \
  -v $(pwd)/deploy/litellm_config.yaml:/app/config.yaml \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --port 4000
```

### 3. Connexion à OpenClaw

Intégrez l'URL du proxy dans votre configuration `openclaw.json` (voir extrait dans [`deploy/openclaw_config_snippet.json`](./deploy/openclaw_config_snippet.json)) :

```json
{
  "models": {
    "mode": "replace",
    "providers": {
      "openai": {
        "baseUrl": "http://127.0.0.1:4001/v1",
        "apiKey": "sk-antigravity-local-bypass-litellm",
        "timeoutSeconds": 600,
        "models": [
          {
            "id": "gemini-3.8-flash",
            "name": "Gemini 3.8 Flash (Réflexion)",
            "contextWindow": 1000000,
            "maxTokens": 64000,
            "reasoning": true
          },
          {
            "id": "gemini-3.8-flash-low",
            "name": "Gemini 3.8 Flash Low (Rapide)",
            "contextWindow": 1000000,
            "maxTokens": 64000,
            "reasoning": true
          }
        ]
      }
    }
  }
}
```

---

## 📡 Modèles Supportés

| Identifiant API | Modèle Cible AGY | Profil |
| :--- | :--- | :--- |
| `gemini-3.8-flash` | Gemini 3.8 Flash (High) | Réflexion avancée & vitesse optimale |
| `gemini-3.8-flash-low` | Gemini 3.8 Flash (Low) | Mode rapide sans latence de réflexion |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 (Thinking) | Raisonnement de pointe & code complexe |
| `claude-opus-4-6` | Claude Opus 4.6 (Thinking) | Analyse exhaustive & architecture |
| `gpt-oss-120b` | GPT-OSS 120B (Medium) | Modèle ouvert open-weights |
| `gemini-4-argon` | Gemini 4 Argon | Fallback automatique vers Flash si palier standard |

---

## 🛠️ Variables d'Environnement

Configurez les variables via votre fichier `.env` ou directement dans l'environnement :

| Variable | Défaut | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | Port d'écoute du serveur HTTP |
| `HOST` | `0.0.0.0` | Adresse de liaison réseau |
| `DEFAULT_WORKSPACE` | `/tmp` | Dossier d'exécution neutre pour le CLI |
| `AGY_BIN_PATH` | `~/.local/bin/agy` | Emplacement du binaire Antigravity |
| `API_KEY` | *(optionnel)* | Clé d'API Bearer pour sécuriser les appels |
| `INCLUDE_REASONING_CONTENT` | `true` | Inclut `reasoning_content` dans les deltas SSE |

---

## 📄 Licence

Ce projet est sous licence [MIT](./LICENSE).
