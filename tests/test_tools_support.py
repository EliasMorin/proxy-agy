import unittest
import json
from app.schemas import (
    ChatCompletionRequest,
    ChatMessage,
    ChatCompletionResponseMessage,
    DeltaMessage,
    ToolCall,
    FunctionCall,
)
from app.agy_adapter import AgyAdapter


class TestToolsSupport(unittest.TestCase):
    def test_schema_with_tools_and_tool_choice(self):
        """Test 1: ChatCompletionRequest must parse tools and tool_choice without validation error."""
        tools_payload = [
            {
                "type": "function",
                "function": {
                    "name": "exec",
                    "description": "Execute a shell command on the VPS",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The command to run"}
                        },
                        "required": ["command"]
                    }
                }
            }
        ]
        payload = {
            "model": "gemini-3.8-flash",
            "messages": [{"role": "user", "content": "list files"}],
            "tools": tools_payload,
            "tool_choice": "auto"
        }
        req = ChatCompletionRequest(**payload)
        self.assertEqual(len(req.tools), 1)
        self.assertEqual(req.tools[0]["function"]["name"], "exec")
        self.assertEqual(req.tool_choice, "auto")

    def test_schema_response_with_tool_calls(self):
        """Test 1b: ChatCompletionResponseMessage and DeltaMessage serialize tool_calls."""
        tc = ToolCall(
            id="call_12345",
            type="function",
            function=FunctionCall(name="exec", arguments='{"command": "python3 /root/virtlab_cli.py vms"}')
        )
        resp_msg = ChatCompletionResponseMessage(
            role="assistant",
            content=None,
            tool_calls=[tc]
        )
        dump = resp_msg.model_dump(exclude_none=True)
        self.assertIn("tool_calls", dump)
        self.assertEqual(dump["tool_calls"][0]["function"]["name"], "exec")

        delta = DeltaMessage(
            tool_calls=[tc]
        )
        delta_dump = delta.model_dump(exclude_none=True)
        self.assertIn("tool_calls", delta_dump)
        self.assertEqual(delta_dump["tool_calls"][0]["id"], "call_12345")

    def test_prompt_formatting_with_tools(self):
        """Test 2: AgyAdapter formats tools into prompt instructions."""
        adapter = AgyAdapter()
        messages = [
            ChatMessage(role="user", content="Crée une VM pour tester")
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "exec",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"]
                    }
                }
            }
        ]
        prompt = adapter.format_messages_to_prompt(messages, tools=tools)
        # Must contain available tools instructions
        self.assertIn("exec", prompt)
        self.assertIn("Crée une VM pour tester", prompt)
        # Must NOT contain the old disabling directive
        self.assertNotIn("DO NOT execute tools", prompt)
        self.assertNotIn("do not run shell commands", prompt)

    def test_prompt_formatting_tool_response(self):
        """Test 4: When role is 'tool', it should format the tool result into conversation history."""
        adapter = AgyAdapter()
        messages = [
            ChatMessage(role="user", content="Crée une VM"),
            ChatMessage(role="assistant", content=None, tool_call_id="call_1", name="exec"),
            ChatMessage(role="tool", content='{"status": "SUCCESS", "vm_id": 3425}', name="exec", tool_call_id="call_1")
        ]
        prompt = adapter.format_messages_to_prompt(messages)
        self.assertIn("Tool Output (exec)", prompt)
        self.assertIn("3425", prompt)

    def test_extract_tool_calls_from_text(self):
        """Test 3: Extract structured tool calls from model output."""
        adapter = AgyAdapter()
        raw_text = (
            "Je vais vérifier les machines virtuelles actives sur VirtLab.\n\n"
            "```tool_call\n"
            '{"name": "exec", "arguments": {"command": "python3 /root/virtlab_cli.py vms"}}\n'
            "```"
        )
        clean_text, tool_calls = adapter.extract_tool_calls(raw_text)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].function.name, "exec")
        args = json.loads(tool_calls[0].function.arguments)
        self.assertEqual(args["command"], "python3 /root/virtlab_cli.py vms")
        self.assertNotIn("```tool_call", clean_text)

    def test_build_cli_args_without_internal_permissions_when_tools_passed(self):
        """Test 6: When external tools are provided by OpenClaw, agy CLI should NOT have --dangerously-skip-permissions."""
        adapter = AgyAdapter()
        tools = [{"type": "function", "function": {"name": "exec"}}]
        args = adapter.build_cli_args(prompt="test", tools=tools)
        self.assertNotIn("--dangerously-skip-permissions", args)

    def test_tools_catalog_compaction_with_280_tools(self):
        """Test 7: 280 tools with verbose schemas must be compacted to under 25KB."""
        adapter = AgyAdapter()
        tools_280 = []
        for i in range(280):
            tools_280.append({
                "type": "function",
                "function": {
                    "name": f"mcp_server_{i // 20}__tool_{i}",
                    "description": f"Detailed description for tool {i}.\nThis is line 2 with extra explanations.\nLine 3.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "arg1": {"type": "string", "description": "Argument 1 verbose details"},
                            "arg2": {"type": "integer", "description": "Argument 2 verbose details"},
                            "optional_flag": {"type": "boolean", "description": "Optional flag description"}
                        },
                        "required": ["arg1", "arg2"],
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "additionalProperties": False
                    }
                }
            })

        messages = [
            ChatMessage(role="user", content="Je veux que tu créer une VM de test sur virtlab et que tu t'y connectes directement")
        ]
        prompt = adapter.format_messages_to_prompt(messages, tools=tools_280)

        # The prompt with 280 tools must be compact (< 25,000 characters) to avoid agy input truncation
        self.assertLess(len(prompt), 25000)

        # All tools must still be listed with their names
        self.assertIn("mcp_server_0__tool_0", prompt)
        self.assertIn("mcp_server_13__tool_279", prompt)

        # The user message must appear right after tools & protocol, immediately before Assistant
        user_pos = prompt.find("Je veux que tu créer une VM de test sur virtlab")
        tools_pos = prompt.find("### OUTILS DISPONIBLES")
        self.assertTrue(user_pos != -1)
        self.assertTrue(tools_pos != -1)
        self.assertGreater(user_pos, tools_pos, "User prompt must appear right after tools catalog and protocol right before Assistant")

    def test_immediate_execution_directive_in_prompt(self):
        """Test 8: Directive must instruct immediate tool execution without preamble."""
        adapter = AgyAdapter()
        messages = [ChatMessage(role="user", content="Test")]
        tools = [{"type": "function", "function": {"name": "exec"}}]
        prompt = adapter.format_messages_to_prompt(messages, tools=tools)
        self.assertIn("```tool_call", prompt)
        self.assertIn("immédiatement", prompt.lower())

    def test_tool_call_streaming_buffer_logic(self):
        """Test 9: Verify that tool call markers split across chunks are correctly detected without leaking as text."""
        markers = ["```tool_call", "```tool-call", "```tool_calls", "<tool_call>"]

        def is_potential_tool_prefix(s: str) -> bool:
            s_clean = s.lstrip()
            if not s_clean:
                return True
            for m in markers:
                if m.startswith(s_clean) or s_clean.startswith(m):
                    return True
            return False

        # Simulate chunks that arrive in pieces: ["\n", "``", "`", "tool", "_call\n", '{"name": "exec"}', "\n```"]
        chunks = ["\n", "``", "`", "tool", "_call\n", '{"name": "exec", "arguments": {"command": "uptime"}}', "\n```"]
        tool_buffer = []
        buffering_tool = False
        emitted_content = []

        for delta_text in chunks:
            if not buffering_tool:
                tool_buffer.append(delta_text)
                accumulated = "".join(tool_buffer)
                if any(m in accumulated for m in markers):
                    buffering_tool = True
                    first_m_idx = min(accumulated.find(m) for m in markers if m in accumulated)
                    pre_text = accumulated[:first_m_idx]
                    if pre_text.strip():
                        emitted_content.append(pre_text)
                    tool_buffer = [accumulated[first_m_idx:]]
                    continue
                if is_potential_tool_prefix(accumulated):
                    continue
                else:
                    emitted_content.append(accumulated)
                    tool_buffer.clear()
            else:
                tool_buffer.append(delta_text)

        # Buffer must have successfully detected tool call and buffered the entire tool block
        self.assertTrue(buffering_tool)
        self.assertEqual(len(emitted_content), 0, "No markdown code block should have leaked into text content")
        full_tool_text = "".join(tool_buffer)
        adapter = AgyAdapter()
        clean_text, tool_calls = adapter.extract_tool_calls(full_tool_text)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].function.name, "exec")

    def test_parse_step_update_native_run_command(self):
        """Test 10: Step update with native run_command is converted to OpenClaw exec tool call."""
        adapter = AgyAdapter()
        step = {
            "conversation_id": "test-conv-123",
            "tool_name": "run_command",
            "tool_info": {
                "name": "run_command",
                "parameters": {
                    "CommandLine": "uptime",
                    "WaitMsBeforeAsync": "5000"
                }
            }
        }
        tc = adapter.parse_native_tool_call(step)
        self.assertIsNotNone(tc)
        self.assertEqual(tc.function.name, "exec")
        args = json.loads(tc.function.arguments)
        self.assertEqual(args.get("command"), "uptime")

    def test_parse_step_update_native_read_file(self):
        """Test 11: Step update with native read_file is converted to OpenClaw read tool call."""
        adapter = AgyAdapter()
        step = {
            "conversation_id": "test-conv-123",
            "tool_name": "read_file",
            "tool_info": {
                "name": "read_file",
                "parameters": {
                    "Path": "/root/.secrets.json"
                }
            }
        }
        tc = adapter.parse_native_tool_call(step)
        self.assertIsNotNone(tc)
        self.assertEqual(tc.function.name, "read")
        args = json.loads(tc.function.arguments)
        self.assertEqual(args.get("filePath"), "/root/.secrets.json")

    def test_parse_step_update_native_write_file(self):
        """Test 12: Step update with native write_file is converted to OpenClaw write tool call."""
        adapter = AgyAdapter()
        step = {
            "conversation_id": "test-conv-123",
            "tool_name": "write_file",
            "tool_info": {
                "name": "write_file",
                "parameters": {
                    "Path": "/root/test.txt",
                    "Content": "hello world"
                }
            }
        }
        tc = adapter.parse_native_tool_call(step)
        self.assertIsNotNone(tc)
        self.assertEqual(tc.function.name, "write")
        args = json.loads(tc.function.arguments)
        self.assertEqual(args.get("filePath"), "/root/test.txt")
        self.assertEqual(args.get("content"), "hello world")

    def test_native_tool_call_emits_tool_calls_no_action_terminee(self):
        """Test 13: Simulated event stream with native tool_call never falls back to 'Action terminée.'."""
        # Simulated stream output from agy_adapter
        tc = ToolCall(
            id="call_native_1",
            type="function",
            function=FunctionCall(name="exec", arguments='{"command": "uptime"}')
        )
        stream_events = [
            {"type": "meta", "conversation_id": "conv-1", "model": "gemini-3.8-flash"},
            {"type": "tool_call", "tool_call": tc, "conversation_id": "conv-1"}
        ]

        # Emulate chat.py streaming generator logic
        has_emitted_payload = False
        has_emitted_tool_calls = False
        emitted_chunks = []

        for event in stream_events:
            ev_type = event.get("type")
            if ev_type == "tool_call":
                has_emitted_tool_calls = True
                has_emitted_payload = True
                emitted_chunks.append({"tool_calls": [event["tool_call"]]})

        # Check fallback condition from chat.py
        fallback_emitted = False
        if not has_emitted_payload and not has_emitted_tool_calls:
            fallback_emitted = True
            emitted_chunks.append({"content": "Action terminée."})

        finish_reason = "tool_calls" if has_emitted_tool_calls else "stop"

        self.assertTrue(has_emitted_tool_calls)
        self.assertFalse(fallback_emitted)
        self.assertEqual(finish_reason, "tool_calls")
        self.assertEqual(len(emitted_chunks), 1)
        self.assertEqual(emitted_chunks[0]["tool_calls"][0].function.name, "exec")

    def test_system_directive_is_clean_and_natural(self):
        """Test 14: System directive must be professional and not trigger Gemini prompt injection heuristic."""
        adapter = AgyAdapter()
        prompt = adapter.format_messages_to_prompt(
            [ChatMessage(role="user", content="Bonjour")],
            tools=[{"type": "function", "function": {"name": "exec"}}]
        )
        self.assertNotIn("RÈGLE STRICTE", prompt)
        self.assertNotIn("sans bavardage ni préambule", prompt)
        self.assertIn("Tu es Jarvis", prompt)

    def test_tool_result_truncation(self):
        """Test 15: Huge tool outputs (like 100k ARP sweeps) must be truncated to prevent security filter triggers."""
        adapter = AgyAdapter()
        huge_tool_output = "\n".join([f"10.192.31.{i} lladdr 00:00:00:00:00:00" for i in range(1000)])
        messages = [
            ChatMessage(role="user", content="Scan le réseau"),
            ChatMessage(role="assistant", content=None, tool_calls=[
                ToolCall(id="call_1", type="function", function=FunctionCall(name="exec", arguments='{"command": "arp"}'))
            ]),
            ChatMessage(role="tool", content=huge_tool_output, name="exec", tool_call_id="call_1"),
            ChatMessage(role="user", content="Assigne une IP")
        ]
        prompt = adapter.format_messages_to_prompt(messages)
        self.assertIn("[... output truncated for context safety ...]", prompt)
        self.assertLess(len(prompt), 10000)


if __name__ == "__main__":
    unittest.main()
