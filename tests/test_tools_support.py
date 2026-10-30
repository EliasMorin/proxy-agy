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


if __name__ == "__main__":
    unittest.main()
