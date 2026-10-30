import subprocess
import json

prompt = """Tu es le moteur d'intelligence de l'agent Jarvis connecté à OpenClaw.
Tu as accès aux outils OpenClaw, notamment :
- exec(command: str): Exécute une commande système sur le VPS.

CONSIGNE STRICTE D'ORCHESTRATION OPENCLAW :
N'exécute AUCUN outil interne dans ce processus. Tu dois déléguer chaque commande à OpenClaw en produisant immédiatement le bloc :
```tool_call
{"name": "exec", "arguments": {"command": "python3 /root/.openclaw/workspace/scripts/virtlab_cli.py create --template-id 4 --name 0531-10-BTS2-TEST"}}
```

Demande : Crée une VM VirtLab de test
"""

payload = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
p = subprocess.run(
    ["/opt/proxy-agy/env1/.local/bin/agy", "--input-format", "stream-json", "--output-format", "stream-json", "--model", "gemini-3.8-flash"],
    input=payload.encode(),
    capture_output=True,
    env={"HOME": "/opt/proxy-agy/env1"}
)
output = p.stdout.decode()
for line in output.splitlines():
    try:
        data = json.loads(line)
        if data.get("event") == "step_update":
            step = data.get("step_update", {})
            if step.get("text_delta"):
                print("TEXT_DELTA:", step.get("text_delta"))
        elif data.get("event") == "result":
            print("RESULT:", data.get("result", {}).get("response"))
    except Exception:
        pass
