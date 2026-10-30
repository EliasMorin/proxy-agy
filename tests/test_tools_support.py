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


if __name__ == "__main__":
    unittest.main()
