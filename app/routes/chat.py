import asyncio
import json
import logging
import time
import uuid
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionResponseMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    DeltaMessage,
    CompletionRequest,
    ChatMessage,
    UsageInfo,
)
from app.agy_adapter import agy_adapter
from app.auth import auth_manager, check_auth_async

logger = logging.getLogger("proxy_agy.routes.chat")
router = APIRouter()


async def verify_auth(authorization: Optional[str] = Header(None)):
    """Verify Bearer token if API_KEY is configured in settings."""
    if not settings.API_KEY:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def ensure_cli_authenticated():
    """Ensure agy CLI is authenticated before processing AI chat requests."""
    if not auth_manager.is_authenticated:
        is_auth = await check_auth_async(force_recheck=False)
        if not is_auth:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "Antigravity CLI 未登录。请在浏览器访问 http://127.0.0.1:8000 提交 Token 激活，或在终端运行 python3 main.py --login 进行登录。",
                        "type": "authentication_required",
                        "code": 401,
                        "login_url": auth_manager.current_oauth_url or "http://127.0.0.1:8000/",
                    }
                },
            )


@router.post("/v1/chat/completions", dependencies=[Depends(ensure_cli_authenticated)])
async def chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    authorization: Optional[str] = Header(None, dependencies=[Depends(verify_auth)]),
    x_conversation_id: Optional[str] = Header(None, alias="X-Conversation-Id"),
    x_working_directory: Optional[str] = Header(None, alias="X-Working-Directory"),
    x_skip_permissions: Optional[bool] = Header(None, alias="X-Skip-Permissions"),
    x_effort: Optional[str] = Header(None, alias="X-Effort"),
):
    """
    OpenAI-compatible /v1/chat/completions endpoint.
    Supports streaming (SSE) and non-streaming responses.
    """
    conversation_id = req.conversation_id or x_conversation_id
    workspace_dir = req.workspace_dir or x_working_directory
    dangerously_skip_permissions = (
        req.dangerously_skip_permissions if req.dangerously_skip_permissions is not None else x_skip_permissions
    )
    effort = req.reasoning_effort or req.effort or x_effort

    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_time = int(time.time())

    # --- 1. STREAMING MODE ---
    if req.stream:
        async def event_generator():
            try:
                # 1. Send initial role notification chunk
                first_chunk = ChatCompletionChunk(
                    id=req_id,
                    created=created_time,
                    model=req.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=DeltaMessage(role="assistant"),
                            finish_reason=None
                        )
                    ]
                )
                yield f"data: {first_chunk.model_dump_json(exclude_none=True)}\n\n"

                final_usage = UsageInfo()
                has_error = False
                buffering_tool = False
                tool_buffer = []

                async for event in agy_adapter.run_stream(
                    messages=req.messages,
                    model=req.model,
                    effort=effort,
                    tools=req.tools,
                    conversation_id=conversation_id,
                    workspace_dir=workspace_dir,
                    dangerously_skip_permissions=dangerously_skip_permissions,
                    mode=req.mode,
                ):
                    event_type = event.get("type")

                    if event_type == "content":
                        delta_text = event.get("delta", "")

                        # If tools are defined, check for tool call markup
                        if req.tools:
                            if "```tool_call" in delta_text or "<tool_call>" in delta_text:
                                buffering_tool = True

                            if buffering_tool:
                                tool_buffer.append(delta_text)
                                continue

                        chunk = ChatCompletionChunk(
                            id=req_id,
                            created=created_time,
                            model=req.model,
                            choices=[
                                ChatCompletionChunkChoice(
                                    index=0,
                                    delta=DeltaMessage(content=delta_text),
                                    finish_reason=None
                                )
                            ]
                        )
                        yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

                    elif event_type == "thinking":
                        delta_thinking = event.get("delta", "")
                        if settings.INCLUDE_REASONING_CONTENT:
                            chunk = ChatCompletionChunk(
                                id=req_id,
                                created=created_time,
                                model=req.model,
                                choices=[
                                    ChatCompletionChunkChoice(
                                        index=0,
                                        delta=DeltaMessage(
                                            content="" if not settings.EMBED_THINKING_IN_TEXT else f"<think>{delta_thinking}</think>",
                                            reasoning_content=delta_thinking
                                        ),
                                        finish_reason=None
                                    )
                                ]
                            )
                            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
                        elif settings.EMBED_THINKING_IN_TEXT:
                            chunk = ChatCompletionChunk(
                                id=req_id,
                                created=created_time,
                                model=req.model,
                                choices=[
                                    ChatCompletionChunkChoice(
                                        index=0,
                                        delta=DeltaMessage(content=f"<think>{delta_thinking}</think>"),
                                        finish_reason=None
                                    )
                                ]
                            )
                            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

                    elif event_type == "done":
                        final_usage = event.get("usage", final_usage)

                    elif event_type == "error":
                        has_error = True
                        err_msg = event.get("error", "Error occurred during agy generation")
                        
                        # Check if error indicates authentication is required
                        if "unauthorized" in err_msg.lower() or "auth" in err_msg.lower() or "login" in err_msg.lower():
                            auth_manager.is_authenticated = False
                            auth_manager.login_message = err_msg

                        error_chunk = ChatCompletionChunk(
                            id=req_id,
                            created=created_time,
                            model=req.model,
                            choices=[
                                ChatCompletionChunkChoice(
                                    index=0,
                                    delta=DeltaMessage(content=f"\n[Error: {err_msg}]\n"),
                                    finish_reason="error"
                                )
                            ]
                        )
                        yield f"data: {error_chunk.model_dump_json(exclude_none=True)}\n\n"

                # If tools were buffered, extract and emit tool calls
                finish_reason = "stop" if not has_error else "error"
                if req.tools and tool_buffer:
                    buffered_raw = "".join(tool_buffer)
                    _, tool_calls = agy_adapter.extract_tool_calls(buffered_raw)
                    if tool_calls:
                        finish_reason = "tool_calls"
                        tc_chunk = ChatCompletionChunk(
                            id=req_id,
                            created=created_time,
                            model=req.model,
                            choices=[
                                ChatCompletionChunkChoice(
                                    index=0,
                                    delta=DeltaMessage(tool_calls=tool_calls),
                                    finish_reason=None
                                )
                            ]
                        )
                        yield f"data: {tc_chunk.model_dump_json(exclude_none=True)}\n\n"
                    else:
                        # Flush buffered text if not parsed as tool calls
                        flush_chunk = ChatCompletionChunk(
                            id=req_id,
                            created=created_time,
                            model=req.model,
                            choices=[
                                ChatCompletionChunkChoice(
                                    index=0,
                                    delta=DeltaMessage(content=buffered_raw),
                                    finish_reason=None
                                )
                            ]
                        )
                        yield f"data: {flush_chunk.model_dump_json(exclude_none=True)}\n\n"

                # Final finish chunk
                finish_chunk = ChatCompletionChunk(
                    id=req_id,
                    created=created_time,
                    model=req.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=DeltaMessage(),
                            finish_reason=finish_reason
                        )
                    ],
                    usage=final_usage if (req.stream_options and req.stream_options.include_usage) else None
                )
                yield f"data: {finish_chunk.model_dump_json(exclude_none=True)}\n\n"
                yield "data: [DONE]\n\n"

            except asyncio.CancelledError:
                logger.info("Client closed connection during stream.")
                raise
            except Exception as e:
                logger.exception("Error during event streaming")
                error_payload = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(error_payload)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    # --- 2. NON-STREAMING MODE ---
    collected_content = []
    collected_reasoning = []
    final_usage = UsageInfo()
    last_conv_id = conversation_id or ""
    error_msg = None

    async for event in agy_adapter.run_stream(
        messages=req.messages,
        model=req.model,
        effort=effort,
        tools=req.tools,
        conversation_id=conversation_id,
        workspace_dir=workspace_dir,
        dangerously_skip_permissions=dangerously_skip_permissions,
        mode=req.mode,
    ):
        event_type = event.get("type")
        if event.get("conversation_id"):
            last_conv_id = event["conversation_id"]

        if event_type == "content":
            collected_content.append(event.get("delta", ""))
        elif event_type == "thinking":
            collected_reasoning.append(event.get("delta", ""))
        elif event_type == "done":
            if event.get("response"):
                collected_content = [event["response"]]
            final_usage = event.get("usage", final_usage)
        elif event_type == "error":
            error_msg = event.get("error")

    if error_msg:
        if "unauthorized" in error_msg.lower() or "auth" in error_msg.lower() or "login" in error_msg.lower():
            auth_manager.is_authenticated = False
            auth_manager.login_message = error_msg
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": error_msg,
                    "type": "agy_execution_error",
                    "code": 500,
                }
            }
        )

    full_text = "".join(collected_content)
    full_reasoning = "".join(collected_reasoning) if collected_reasoning else None

    clean_text, tool_calls = agy_adapter.extract_tool_calls(full_text) if req.tools else (full_text, [])
    finish_reason = "tool_calls" if tool_calls else ("stop" if not error_msg else "error")

    response_data = ChatCompletionResponse(
        id=req_id,
        created=created_time,
        model=req.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionResponseMessage(
                    role="assistant",
                    content=clean_text if clean_text else None,
                    reasoning_content=full_reasoning if settings.INCLUDE_REASONING_CONTENT else None,
                    tool_calls=tool_calls if tool_calls else None
                ),
                finish_reason=finish_reason
            )
        ],
        usage=final_usage
    )

    return response_data


@router.post("/v1/completions", dependencies=[Depends(ensure_cli_authenticated)])
async def completions(
    req: CompletionRequest,
    authorization: Optional[str] = Header(None, dependencies=[Depends(verify_auth)]),
):
    """Legacy /v1/completions endpoint, translates prompt to chat completion."""
    prompt_text = req.prompt if isinstance(req.prompt, str) else "\n".join(req.prompt)
    chat_req = ChatCompletionRequest(
        model=req.model,
        messages=[ChatMessage(role="user", content=prompt_text)],
        stream=req.stream,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    return await chat_completions(req=chat_req, request=None, authorization=authorization)
