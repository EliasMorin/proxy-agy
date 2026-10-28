import os
import shutil
from typing import Dict, List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    API_KEY: Optional[str] = None  # If set, requests must include Bearer token

    # AGY CLI settings
    AGY_BIN_PATH: str = os.getenv("AGY_BIN_PATH") or shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
    DEFAULT_MODEL: str = "Gemini 3.8 Flash (High)"
    DEFAULT_EFFORT: str = "high"
    DEFAULT_WORKSPACE: str = "/tmp"
    
    # Execution behavior
    DANGEROUSLY_SKIP_PERMISSIONS: bool = True
    DISABLE_SLASH_COMMANDS: bool = True
    COMMAND_TIMEOUT: int = 300  # seconds

    # Reasoning / Thinking delta delivery
    INCLUDE_REASONING_CONTENT: bool = True  # Send delta.reasoning_content in SSE chunks
    EMBED_THINKING_IN_TEXT: bool = False    # Wrap thinking in <think>...</think> if true

    # Known model definitions and alias mappings
    MODEL_ALIASES: Dict[str, str] = {
        # Gemini 4 Argon
        "gemini-4-argon": "Gemini 4 Argon",
        "gemini-4-argon-high": "Gemini 4 Argon",
        "gemini-4-argon-medium": "Gemini 4 Argon",
        "gemini-4-argon-low": "Gemini 4 Argon",
        "gemini-4-argon-thinking": "Gemini 4 Argon",
        "gemini-4-argon-max": "Gemini 4 Argon",
        "gemini-4": "Gemini 4 Argon",
        "gemini-4.0": "Gemini 4 Argon",
        "gemini-4.0-argon": "Gemini 4 Argon",
        "gemini-argon": "Gemini 4 Argon",
        "gemini-argon-high": "Gemini 4 Argon",
        "gemini-argon-medium": "Gemini 4 Argon",
        "gemini-argon-low": "Gemini 4 Argon",
        "gemini-argon-thinking": "Gemini 4 Argon",
        "argon": "Gemini 4 Argon",
        "argon-high": "Gemini 4 Argon",
        "argon-medium": "Gemini 4 Argon",
        "argon-low": "Gemini 4 Argon",
        "argon-thinking": "Gemini 4 Argon",
        "argon-max": "Gemini 4 Argon",

        # Gemini 3.8 Flash
        "gemini-3.8-flash": "Gemini 3.8 Flash (High)",
        "gemini-3.8-flash-high": "Gemini 3.8 Flash (High)",
        "gemini-3.8-flash-medium": "Gemini 3.8 Flash (Medium)",
        "gemini-3.8-flash-low": "Gemini 3.8 Flash (Low)",
        "gemini-3.8-flash-thinking": "Gemini 3.8 Flash (High)",
        "gemini-3.8": "Gemini 3.8 Flash (High)",
        "gemini-flash": "Gemini 3.8 Flash (High)",

        # Backward compatibility aliases -> map to Gemini 3.8 Flash
        "gemini-3.7-flash": "Gemini 3.8 Flash (High)",
        "gemini-3.7-flash-high": "Gemini 3.8 Flash (High)",
        "gemini-3.7-flash-medium": "Gemini 3.8 Flash (Medium)",
        "gemini-3.7-flash-low": "Gemini 3.8 Flash (Low)",
        "gemini-3.7-flash-thinking": "Gemini 3.8 Flash (High)",
        "gemini-3.7": "Gemini 3.8 Flash (High)",

        "gemini-3.6-flash": "Gemini 3.8 Flash (High)",
        "gemini-3.6-flash-high": "Gemini 3.8 Flash (High)",
        "gemini-3.6-flash-medium": "Gemini 3.8 Flash (Medium)",
        "gemini-3.6-flash-low": "Gemini 3.8 Flash (Low)",
        "gemini-3.6": "Gemini 3.8 Flash (High)",

        "gemini-3.5-flash": "Gemini 3.8 Flash (High)",
        "gemini-3.5-flash-high": "Gemini 3.8 Flash (High)",
        "gemini-3.5-flash-medium": "Gemini 3.8 Flash (Medium)",
        "gemini-3.5-flash-low": "Gemini 3.8 Flash (Low)",
        "gemini-3.5": "Gemini 3.8 Flash (High)",

        # Gemini Pro -> map to Gemini 3.8 Flash (High)
        "gemini-3.1-pro": "Gemini 3.8 Flash (High)",
        "gemini-3.1-pro-high": "Gemini 3.8 Flash (High)",
        "gemini-3.1-pro-low": "Gemini 3.8 Flash (Low)",
        "gemini-pro": "Gemini 3.8 Flash (High)",
        "gemini-3.1": "Gemini 3.8 Flash (High)",

        # Claude
        "claude-3-7-sonnet": "Claude Sonnet 4.6 (Thinking)",
        "claude-sonnet-4-6": "Claude Sonnet 4.6 (Thinking)",
        "claude-3-7-sonnet-thinking": "Claude Sonnet 4.6 (Thinking)",
        "claude-sonnet": "Claude Sonnet 4.6 (Thinking)",
        "claude-3-5-sonnet": "Claude Sonnet 4.6 (Thinking)",
        "claude-3-opus": "Claude Opus 4.6 (Thinking)",
        "claude-opus-4-6": "Claude Opus 4.6 (Thinking)",
        "claude-opus": "Claude Opus 4.6 (Thinking)",

        # GPT aliases
        "gpt-4o": "GPT-OSS 120B (Medium)",
        "gpt-4": "GPT-OSS 120B (Medium)",
        "gpt-3.5-turbo": "Gemini 3.8 Flash (Low)",
        "gpt-oss": "GPT-OSS 120B (Medium)",
        "gpt-oss-120b": "GPT-OSS 120B (Medium)",

        # Default fallback
        "default": "Gemini 3.8 Flash (High)",
    }

    KNOWN_CLI_MODELS: List[str] = [
        "Gemini 4 Argon",
        "Gemini 3.8 Flash (High)",
        "Gemini 3.8 Flash (Medium)",
        "Gemini 3.8 Flash (Low)",
        "Claude Sonnet 4.6 (Thinking)",
        "Claude Opus 4.6 (Thinking)",
        "GPT-OSS 120B (Medium)",
    ]

    def resolve_model(self, requested_model: Optional[str], effort: Optional[str] = None) -> str:
        """Resolve requested model name or alias to the exact CLI model name."""
        eff = (effort or "").lower().strip()
        if not requested_model or requested_model.strip() == "":
            base_model = self.DEFAULT_MODEL
        else:
            base_model = requested_model.strip()

        # Strip prefixes like "openai/" or "google/" if present
        if "/" in base_model:
            base_model = base_model.split("/", 1)[1]
        
        # 1. Exact match with known CLI models
        for known in self.KNOWN_CLI_MODELS:
            if base_model.lower() == known.lower():
                return known

        # 2. Direct alias check
        req_key = base_model.lower()
        if req_key in self.MODEL_ALIASES:
            resolved = self.MODEL_ALIASES[req_key]
            # If explicit effort is passed (e.g. low/med/high) and model is Gemini Flash, adapt it
            if eff in ("low", "medium", "high") and "Gemini 3" in resolved:
                if eff == "low" and "(Low)" not in resolved:
                    resolved = resolved.replace("(High)", "(Low)").replace("(Medium)", "(Low)")
                elif eff == "medium" and "(Medium)" not in resolved:
                    resolved = resolved.replace("(High)", "(Medium)").replace("(Low)", "(Medium)")
                elif eff == "high" and "(High)" not in resolved:
                    resolved = resolved.replace("(Low)", "(High)").replace("(Medium)", "(High)")
            return resolved
        
        # 3. Fuzzy matches
        if "argon" in req_key or ("4" in req_key and "gemini" in req_key and "flash" not in req_key):
            return "Gemini 4 Argon"
        elif any(v in req_key for v in ["3.8", "3.7", "3.6", "3.5"]) and "flash" in req_key:
            if eff == "low" or "low" in req_key:
                return "Gemini 3.8 Flash (Low)"
            if eff == "medium" or "med" in req_key:
                return "Gemini 3.8 Flash (Medium)"
            return "Gemini 3.8 Flash (High)"
        elif "pro" in req_key:
            if eff == "low" or "low" in req_key:
                return "Gemini 3.8 Flash (Low)"
            return "Gemini 3.8 Flash (High)"
        elif "sonnet" in req_key:
            return "Claude Sonnet 4.6 (Thinking)"
        elif "opus" in req_key:
            return "Claude Opus 4.6 (Thinking)"
        elif "gpt" in req_key or "oss" in req_key:
            return "GPT-OSS 120B (Medium)"
        elif "gemini" in req_key or "flash" in req_key:
            if eff == "low" or "low" in req_key:
                return "Gemini 3.8 Flash (Low)"
            if eff == "medium" or "med" in req_key:
                return "Gemini 3.8 Flash (Medium)"
            return "Gemini 3.8 Flash (High)"

        # Fallback to the requested string directly if nothing matched
        return base_model


settings = Settings()
