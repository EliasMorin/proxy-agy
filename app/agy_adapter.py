import asyncio
import json
import logging
import os
import time
import uuid
from typing import AsyncGenerator, Dict, List, Optional, Tuple, Any

from app.config import settings
from app.schemas import ChatMessage, UsageInfo

logger = logging.getLogger("proxy_agy.adapter")


class AgyAdapter:
    """Adapter to manage subprocess interactions with the agy CLI."""

    def __init__(self, bin_path: Optional[str] = None):
        self.bin_path = bin_path or settings.AGY_BIN_PATH
        self.unavailable_models: set = set()
        self._cached_available_models: Optional[List[str]] = None
        self._last_models_fetch: float = 0
        if not os.path.isfile(self.bin_path) and not os.access(self.bin_path, os.X_OK):
            logger.warning(f"AGY binary not found or not executable at: {self.bin_path}")

    async def get_available_cli_models(self, force: bool = False) -> List[str]:
        """Fetch list of actually available models from agy models CLI command."""
        now = time.time()
        if not force and self._cached_available_models and (now - self._last_models_fetch < 600):
            return self._cached_available_models

        try:
            p = await asyncio.create_subprocess_exec(
                self.bin_path, "models",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(p.communicate(), timeout=15.0)
            lines = stdout.decode("utf-8", errors="replace").splitlines()
            models = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    raw_name = " ".join(parts[1:]).strip()
                    if raw_name:
                        models.append(raw_name)
            if models:
                self._cached_available_models = models
                self._last_models_fetch = now
                logger.info(f"Discovered {len(models)} available AGY models: {models}")
                return models
        except Exception as e:
            logger.warning(f"Failed to fetch models from agy CLI: {e}")

        return [
            "Gemini 3.8 Flash (High)",
            "Gemini 3.8 Flash (Medium)",
            "Gemini 3.8 Flash (Low)",
            "Claude Sonnet 4.6 (Thinking)",
            "Claude Opus 4.6 (Thinking)",
            "GPT-OSS 120B (Medium)",
        ]

    def format_messages_to_prompt(self, messages: List[ChatMessage], is_resuming: bool = False) -> str:
        """Convert OpenAI chat messages into a structured prompt for agy CLI."""
        if not messages:
            return ""

        directive = (
            "[SYSTEM DIRECTIVE: You are an AI reasoning model serving API completions. "
            "DO NOT execute tools, do not run shell commands, do not open browsers on the local server. "
            "Answer directly with explanations, guides, architectural plans, and code.]"
        )

        # If resuming an existing agy conversation, only send the latest user message
        if is_resuming:
            for msg in reversed(messages):
                if msg.role == "user":
                    return f"{directive}\n\n{msg.get_text_content()}"
            return f"{directive}\n\n{messages[-1].get_text_content()}"

        # If there is only one message and it's from user, return directly with directive
        if len(messages) == 1 and messages[0].role == "user":
            return f"{directive}\n\n{messages[0].get_text_content()}"

        # Handle system message(s) + user message(s)
        system_prompts = []
        conversation_turns = []

        for msg in messages:
            content = msg.get_text_content()
            if not content.strip():
                continue
            if msg.role in ("system", "developer"):
                system_prompts.append(content)
            elif msg.role == "user":
                conversation_turns.append(f"User: {content}")
            elif msg.role == "assistant":
                conversation_turns.append(f"Assistant: {content}")
            elif msg.role == "tool":
                conversation_turns.append(f"Tool Output ({msg.name or 'unknown'}): {content}")
            else:
                conversation_turns.append(f"{msg.role.capitalize()}: {content}")

        prompt_parts = [directive]
        if system_prompts:
            prompt_parts.append("### System Instructions\n" + "\n\n".join(system_prompts))

        if conversation_turns:
            # If there's only 1 turn and it's user, format cleanly
            if len(conversation_turns) == 1 and conversation_turns[0].startswith("User: "):
                user_text = conversation_turns[0][len("User: "):]
                if system_prompts:
                    prompt_parts.append(f"### User Request\n{user_text}")
                else:
                    prompt_parts.append(user_text)
            else:
                # Support deep conversation history up to 300,000 characters
                max_history_chars = 300000
                total_len = sum(len(t) for t in conversation_turns)
                if total_len > max_history_chars:
                    trimmed_turns = []
                    curr_len = 0
                    for turn in reversed(conversation_turns):
                        if curr_len + len(turn) > max_history_chars and trimmed_turns:
                            break
                        trimmed_turns.append(turn)
                        curr_len += len(turn)
                    trimmed_turns.reverse()
                    history_text = "[Earlier conversation history trimmed for context limits]\n\n" + "\n\n".join(trimmed_turns)
                else:
                    history_text = "\n\n".join(conversation_turns)

                prompt_parts.append("### Conversation History\n" + history_text + "\n\nAssistant:")

        return "\n\n".join(prompt_parts)

    def build_cli_args(
        self,
        prompt: str,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        conversation_id: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        dangerously_skip_permissions: Optional[bool] = None,
        mode: Optional[str] = None,
    ) -> List[str]:
        """Build argument list for executing agy CLI."""
        resolved_model = settings.resolve_model(model, effort=effort)

        # Fast path: If model is known to be unavailable, route immediately to default
        if resolved_model in self.unavailable_models or "argon" in resolved_model.lower():
            if "argon" in resolved_model.lower() and resolved_model not in self.unavailable_models:
                self.unavailable_models.add(resolved_model)
                logger.warning(
                    f"Requested model {resolved_model} requires Google AI Ultra plan. "
                    f"Gracefully substituting with {settings.DEFAULT_MODEL}."
                )
            logger.warning(
                f"Requested model '{resolved_model}' is currently unavailable on account tier. "
                f"Instantly substituting with '{settings.DEFAULT_MODEL}' to eliminate delay."
            )
            resolved_model = settings.DEFAULT_MODEL

        args = [
            self.bin_path,
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--print-timeout", "30m",
            "--model", resolved_model,
        ]

        # Extract effort if specified in model name but not explicitly passed
        eff = effort
        if not eff and model:
            m_lower = model.lower()
            if "xhigh" in m_lower or "max" in m_lower:
                eff = "max"
            elif "high" in m_lower or "thinking" in m_lower:
                eff = "high"
            elif "medium" in m_lower or "med" in m_lower:
                eff = "medium"
            elif "low" in m_lower:
                eff = "low"
            elif "argon" in m_lower:
                eff = "high"

        # Only pass --effort if model name does not already contain parenthesis specifications
        has_tag_in_name = any(tag in resolved_model for tag in ["(Low)", "(Medium)", "(High)", "(Thinking)"])
        if not has_tag_in_name and eff in ("low", "medium", "high", "xhigh", "max"):
            args.extend(["--effort", eff])

        skip_perms = dangerously_skip_permissions if dangerously_skip_permissions is not None else settings.DANGEROUSLY_SKIP_PERMISSIONS
        if skip_perms:
            args.append("--dangerously-skip-permissions")

        if settings.DISABLE_SLASH_COMMANDS:
            args.append("--disable-slash-commands")

        if conversation_id:
            args.extend(["--conversation", conversation_id])

        if workspace_dir:
            args.extend(["--add-dir", workspace_dir])

        if mode:
            args.extend(["--mode", mode])

        return args

    async def run_stream(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        effort: Optional[str] = None,
        conversation_id: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        dangerously_skip_permissions: Optional[bool] = None,
        mode: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute agy CLI in a subprocess and yield parsed stream-json events.
        Yields dictionary events:
          - {"type": "meta", "conversation_id": "...", "model": "..."}
          - {"type": "content", "delta": "..."}
          - {"type": "thinking", "delta": "..."}
          - {"type": "usage", "usage": UsageInfo(...)}
          - {"type": "done", "response": "...", "usage": UsageInfo(...), "conversation_id": "..."}
          - {"type": "error", "error": "..."}
        """
        is_resuming = bool(conversation_id)
        prompt = self.format_messages_to_prompt(messages, is_resuming=is_resuming)
        args = self.build_cli_args(
            prompt=prompt,
            model=model,
            effort=effort,
            conversation_id=conversation_id,
            workspace_dir=workspace_dir,
            dangerously_skip_permissions=dangerously_skip_permissions,
            mode=mode,
        )

        cwd = workspace_dir or settings.DEFAULT_WORKSPACE
        logger.info(f"Executing agy CLI command: {' '.join(args[:4])}... (model={model}) in cwd={cwd}")

        proc = None
        try:
            resolved_model = settings.resolve_model(model, effort=effort)

            import signal

            def preexec():
                try:
                    import ctypes
                    PR_SET_PDEATHSIG = 1
                    ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
                except Exception:
                    pass
                try:
                    os.setsid()
                except Exception:
                    pass

            def kill_process_tree(p, sig=signal.SIGTERM):
                if not p or p.returncode is not None:
                    return
                try:
                    pgid = os.getpgid(p.pid)
                    os.killpg(pgid, sig)
                except Exception:
                    try:
                        if sig == signal.SIGKILL:
                            p.kill()
                        else:
                            p.terminate()
                    except Exception:
                        pass

            async def launch_proc(cmd_args):
                p = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    preexec_fn=preexec,
                    limit=16 * 1024 * 1024,
                )
                payload = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
                try:
                    p.stdin.write(payload.encode("utf-8"))
                    await p.stdin.drain()
                    p.stdin.close()
                    return p, None
                except (BrokenPipeError, ConnectionResetError):
                    stderr_data = await p.stderr.read()
                    err = stderr_data.decode("utf-8", errors="replace").strip()
                    kill_process_tree(p, signal.SIGKILL)
                    return None, err

            proc, err_text = await launch_proc(args)
            if not proc:
                logger.error(f"Broken pipe writing to agy stdin. CLI stderr: {err_text}")
                # If model is unavailable (e.g. requires Ultra tier or unrecognized), fallback to default
                if ("unavailable" in err_text.lower() or "not recognized" in err_text.lower()) and resolved_model != settings.DEFAULT_MODEL:
                    logger.warning(
                        f"Model '{resolved_model}' unavailable on current account: {err_text}. "
                        f"Falling back transparently to '{settings.DEFAULT_MODEL}'."
                    )
                    fallback_args = self.build_cli_args(
                        prompt=prompt,
                        model=settings.DEFAULT_MODEL,
                        effort=effort,
                        conversation_id=conversation_id,
                        workspace_dir=workspace_dir,
                        dangerously_skip_permissions=dangerously_skip_permissions,
                        mode=mode,
                    )
                    proc, fb_err = await launch_proc(fallback_args)
                    if not proc:
                        yield {
                            "type": "error",
                            "error": f"Failed fallback execution: {fb_err}",
                            "conversation_id": conversation_id or ""
                        }
                        return
                else:
                    yield {
                        "type": "error",
                        "error": f"Failed to execute agy CLI: {err_text or 'Subprocess closed pipe'}",
                        "conversation_id": conversation_id or ""
                    }
                    return

            current_conv_id = conversation_id or ""

            latest_usage = UsageInfo()
            accumulated_content = []

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug(f"Non-JSON line from agy: {line_str}")
                    continue

                event_type = event.get("event")

                if event_type == "init":
                    init_data = event.get("init", {})
                    current_conv_id = event.get("conversation_id", current_conv_id)
                    yield {
                        "type": "meta",
                        "conversation_id": current_conv_id,
                        "model": init_data.get("model", model or settings.DEFAULT_MODEL)
                    }

                elif event_type == "step_update":
                    step = event.get("step_update", {})
                    current_conv_id = step.get("conversation_id", current_conv_id)
                    
                    # Check for usage updates in step
                    if "usage" in step and isinstance(step["usage"], dict):
                        u = step["usage"]
                        latest_usage = UsageInfo(
                            prompt_tokens=u.get("input_tokens", latest_usage.prompt_tokens),
                            completion_tokens=u.get("output_tokens", latest_usage.completion_tokens),
                            total_tokens=u.get("total_tokens", latest_usage.total_tokens),
                            thinking_tokens=u.get("thinking_tokens"),
                            cache_read_tokens=u.get("cache_read_tokens")
                        )

                    # Text delta
                    text_delta = step.get("text_delta")
                    if text_delta:
                        accumulated_content.append(text_delta)
                        yield {
                            "type": "content",
                            "delta": text_delta,
                            "conversation_id": current_conv_id
                        }

                    # Thinking / reasoning delta
                    thinking_delta = step.get("thinking_delta")
                    if thinking_delta:
                        yield {
                            "type": "thinking",
                            "delta": thinking_delta,
                            "conversation_id": current_conv_id
                        }

                elif event_type == "result":
                    res = event.get("result", {})
                    status = res.get("status")
                    current_conv_id = res.get("conversation_id", current_conv_id)

                    if "usage" in res and isinstance(res["usage"], dict):
                        u = res["usage"]
                        latest_usage = UsageInfo(
                            prompt_tokens=u.get("input_tokens", latest_usage.prompt_tokens),
                            completion_tokens=u.get("output_tokens", latest_usage.completion_tokens),
                            total_tokens=u.get("total_tokens", latest_usage.total_tokens),
                            thinking_tokens=u.get("thinking_tokens"),
                            cache_read_tokens=u.get("cache_read_tokens")
                        )

                    if status == "ERROR":
                        err_msg = res.get("error", "Unknown error from agy CLI")
                        logger.error(f"AGY CLI returned error: {err_msg}")
                        if ("unavailable" in err_msg.lower() or "not recognized" in err_msg.lower()):
                            self.unavailable_models.add(resolved_model)
                            if resolved_model != settings.DEFAULT_MODEL and not accumulated_content:
                                logger.warning(
                                    f"Model '{resolved_model}' unavailable on current account: {err_msg}. "
                                    f"Falling back transparently to '{settings.DEFAULT_MODEL}'."
                                )
                                async for fb_event in self.run_stream(
                                    messages=messages,
                                    model=settings.DEFAULT_MODEL,
                                    effort=effort,
                                    conversation_id=conversation_id,
                                    workspace_dir=workspace_dir,
                                    dangerously_skip_permissions=dangerously_skip_permissions,
                                    mode=mode,
                                ):
                                    yield fb_event
                                return
                        yield {
                            "type": "error",
                            "error": err_msg,
                            "conversation_id": current_conv_id
                        }
                        return
                    else:
                        full_response = res.get("response", "\n\n".join(accumulated_content))
                        yield {
                            "type": "done",
                            "response": full_response,
                            "usage": latest_usage,
                            "conversation_id": current_conv_id
                        }

            await proc.wait()

            if proc.returncode != 0 and not accumulated_content:
                stderr_data = await proc.stderr.read()
                stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
                if ("unavailable" in stderr_text.lower() or "not recognized" in stderr_text.lower()):
                    self.unavailable_models.add(resolved_model)
                    if resolved_model != settings.DEFAULT_MODEL:
                        logger.warning(
                            f"Model '{resolved_model}' exited with code {proc.returncode}: {stderr_text}. "
                            f"Falling back transparently to '{settings.DEFAULT_MODEL}'."
                        )
                        async for fb_event in self.run_stream(
                            messages=messages,
                            model=settings.DEFAULT_MODEL,
                            effort=effort,
                            conversation_id=conversation_id,
                            workspace_dir=workspace_dir,
                            dangerously_skip_permissions=dangerously_skip_permissions,
                            mode=mode,
                        ):
                            yield fb_event
                        return
                yield {
                    "type": "error",
                    "error": f"CLI exited with code {proc.returncode}: {stderr_text}",
                    "conversation_id": current_conv_id
                }

        except asyncio.CancelledError:
            logger.warning("Request cancelled by client, terminating agy subprocess...")
            if proc and proc.returncode is None:
                kill_process_tree(proc, signal.SIGTERM)
                try:
                    await asyncio.sleep(0.15)
                    if proc.returncode is None:
                        kill_process_tree(proc, signal.SIGKILL)
                except Exception as e:
                    logger.error(f"Failed to kill agy subprocess: {e}")
            raise
        except Exception as e:
            logger.exception("Exception during agy execution")
            yield {
                "type": "error",
                "error": str(e),
                "conversation_id": current_conv_id if 'current_conv_id' in locals() else ""
            }
        finally:
            if proc and proc.returncode is None:
                kill_process_tree(proc, signal.SIGKILL)


agy_adapter = AgyAdapter()
