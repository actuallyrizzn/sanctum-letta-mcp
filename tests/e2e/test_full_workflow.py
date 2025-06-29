"""
End-to-end tests for full workflow scenarios.
"""

import pytest
import json
import asyncio
import subprocess
from pathlib import Path
from aiohttp.test_utils import TestClient
import os

# Plugin CLI templates
WORKFLOW_PLUGIN = {
    'name': 'workflow_test_plugin',
    'cli_content': '''#!/usr/bin/env python3
import argparse
import json
import sys

def workflow_command(args):
    param = args.get("param", "default")
    return {"result": f"Workflow executed with param: {param}"}

def main():
    parser = argparse.ArgumentParser(
        description="Workflow test plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available commands:
  workflow-command    Run the workflow command

Examples:
  python cli.py workflow-command --param test_value
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    workflow_parser = subparsers.add_parser("workflow-command", help="Run the workflow command")
    workflow_parser.add_argument("--param", default="default", help="Parameter for workflow")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "workflow-command":
        result = workflow_command({"param": args.param})
        print(json.dumps(result))
        sys.exit(0)
    else:
        print(json.dumps({"error": "Unknown command"}))
        sys.exit(1)
if __name__ == "__main__":
    main()
'''
}

MULTI_PLUGINS = [
    {
        'name': name,
        'cli_content': f'''#!/usr/bin/env python3
import argparse
import json
import sys

def test_command(args):
    return {{"result": f"{name} executed successfully"}}

def main():
    parser = argparse.ArgumentParser(
        description="{name}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available commands:
  test-command    Run the test command

Examples:
  python cli.py test-command
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    test_parser = subparsers.add_parser("test-command", help="Run the test command")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "test-command":
        result = test_command({{}})
        print(json.dumps(result))
        sys.exit(0)
    else:
        print(json.dumps({{"error": "Unknown command"}}))
        sys.exit(1)
if __name__ == "__main__":
    main()
'''
    } for name in ["plugin_a", "plugin_b", "plugin_c"]
]

ERROR_PLUGIN = {
    'name': 'error_plugin',
    'cli_content': '''#!/usr/bin/env python3
import argparse
import json
import sys

def error_command(args):
    return {"error": "This is a test error"}

def main():
    parser = argparse.ArgumentParser(
        description="Error test plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available commands:
  error-command    Run the error command

Examples:
  python cli.py error-command
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    error_parser = subparsers.add_parser("error-command", help="Run the error command")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "error-command":
        result = error_command({})
        print(json.dumps(result))
        sys.exit(0)
    else:
        print(json.dumps({"error": "Unknown command"}))
        sys.exit(1)
if __name__ == "__main__":
    main()
'''
}

CONCURRENT_PLUGIN = {
    'name': 'concurrent_plugin',
    'cli_content': '''#!/usr/bin/env python3
import argparse
import json
import sys
import time

def concurrent_command(args):
    time.sleep(0.1)
    return {"result": "Concurrent execution completed"}

def main():
    parser = argparse.ArgumentParser(
        description="Concurrent test plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available commands:
  concurrent-command    Run the concurrent command

Examples:
  python cli.py concurrent-command
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    concurrent_parser = subparsers.add_parser("concurrent-command", help="Run the concurrent command")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "concurrent-command":
        result = concurrent_command({})
        print(json.dumps(result))
        sys.exit(0)
    else:
        print(json.dumps({"error": "Unknown command"}))
        sys.exit(1)
if __name__ == "__main__":
    main()
'''
}

class TestFullWorkflow:
    """Test cases for full workflow scenarios."""
    
    @pytest.mark.usefixtures("client")
    @pytest.mark.parametrize("temp_plugins_dir_with_plugins", [[WORKFLOW_PLUGIN]], indirect=True)
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_complete_plugin_workflow(self, client, temp_plugins_dir_with_plugins):
        """Test complete workflow from plugin discovery to execution."""
        # Test 1: Health check shows 1 plugin
        async with client.get('/health') as response:
            health_data = await response.json()
            assert health_data["plugins"] == 1

        # Test 2: SSE connection shows tools manifest
        async with client.get('/sse') as response:
            assert response.status == 200
            data = await asyncio.wait_for(response.content.readline(), timeout=10.0)
            data_str = data.decode('utf-8').strip()
            json_str = data_str[6:]
            event_data = json.loads(json_str)
            tools = event_data["params"]["tools"]
            assert len(tools) > 0
            workflow_tool = next((t for t in tools if t["name"] == "workflow_test_plugin.workflow-command"), None)
            assert workflow_tool is not None
            assert "param" in workflow_tool["inputSchema"]["properties"]

        # Test 3: Execute the plugin tool
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workflow_test_plugin.workflow-command",
                "arguments": {"param": "test_value"}
            }
        }
        async with client.post('/message', json=request) as response:
            assert response.status == 200
            data = await response.json()
            assert "jsonrpc" in data
            assert data["jsonrpc"] == "2.0"
            assert "result" in data
            assert "content" in data["result"]
            assert len(data["result"]["content"]) == 1
            assert data["result"]["content"][0]["type"] == "text"
            assert "Workflow executed with param: test_value" in data["result"]["content"][0]["text"]

        # Test 4: Health check shows plugin count
        async with client.get('/health') as response:
            health_data = await response.json()
            assert health_data["plugins"] == 1
    
    @pytest.mark.usefixtures("client")
    @pytest.mark.parametrize("temp_plugins_dir_with_plugins", [MULTI_PLUGINS], indirect=True)
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)  # 45 second timeout for multiple plugins
    async def test_multiple_plugins_workflow(self, client, temp_plugins_dir_with_plugins):
        """Test workflow with multiple plugins."""
        plugins = ["plugin_a", "plugin_b", "plugin_c"]
        
        # Test SSE shows all plugins
        async with client.get('/sse') as response:
            assert response.status == 200
            
            data = await asyncio.wait_for(response.content.readline(), timeout=10.0)
            data_str = data.decode('utf-8').strip()
            json_str = data_str[6:]
            event_data = json.loads(json_str)
            
            tools = event_data["params"]["tools"]
            assert len(tools) == len(plugins)  # One tool per plugin
            
            # Check all plugins are present
            for plugin_name in plugins:
                tool_name = f"{plugin_name}.test-command"
                tool = next((t for t in tools if t["name"] == tool_name), None)
                assert tool is not None
        
        # Test executing each plugin
        for plugin_name in plugins:
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": f"{plugin_name}.test-command",
                    "arguments": {}
                }
            }
            
            async with client.post('/message', json=request) as response:
                assert response.status == 200
                
                data = await response.json()
                assert "result" in data
                assert f"{plugin_name} executed successfully" in data["result"]["content"][0]["text"]
    
    @pytest.mark.usefixtures("client")
    @pytest.mark.parametrize("temp_plugins_dir_with_plugins", [[ERROR_PLUGIN]], indirect=True)
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # 30 second timeout for error handling
    async def test_error_handling_workflow(self, client, temp_plugins_dir_with_plugins):
        """Test error handling in complete workflow."""
        # Test error handling
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "error_plugin.error-command",
                "arguments": {}
            }
        }
        
        async with client.post('/message', json=request) as response:
            assert response.status == 200
            
            data = await response.json()
            assert "error" in data
            assert data["error"]["code"] == -32603  # Internal error
            assert "This is a test error" in data["error"]["message"]
    
    @pytest.mark.usefixtures("client")
    @pytest.mark.parametrize("temp_plugins_dir_with_plugins", [[CONCURRENT_PLUGIN]], indirect=True)
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # 60 second timeout for concurrent requests
    async def test_concurrent_requests_workflow(self, client, temp_plugins_dir_with_plugins):
        """Test handling of concurrent requests."""
        # Test concurrent requests
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "concurrent_plugin.concurrent-command",
                "arguments": {}
            }
        }
        
        # Send multiple concurrent requests
        tasks = []
        for i in range(5):
            task = client.post('/message', json=request)
            tasks.append(task)
        
        # Wait for all requests to complete with timeout
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30.0)
        
        # Check all responses
        for response in responses:
            assert response.status == 200
            
            data = await response.json()
            assert "result" in data
            assert "Concurrent execution completed" in data["result"]["content"][0]["text"]
    
    @pytest.mark.usefixtures("client")
    @pytest.mark.asyncio
    @pytest.mark.timeout(45)  # 45 second timeout for session management
    async def test_session_management_workflow(self, client):
        """Test session management in workflow."""
        # Test multiple SSE connections
        connections = []
        
        # Create multiple SSE connections
        for i in range(3):
            response = await client.get('/sse')
            assert response.status == 200
            connections.append(response)
        
        # Check session count
        async with client.get('/health') as response:
            health_data = await response.json()
            assert health_data["sessions"] >= 3
        
        # Read from each connection with timeout
        for conn in connections:
            data = await asyncio.wait_for(conn.content.readline(), timeout=10.0)
            assert data is not None
        
        # Close connections
        for conn in connections:
            await asyncio.wait_for(conn.content.readline(), timeout=5.0)  # Read one more line to establish connection
        
        # Wait for cleanup (poll /health until sessions == 0 or timeout)
        for _ in range(20):  # up to 2 seconds
            async with client.get('/health') as response:
                health_data = await response.json()
                if health_data["sessions"] == 0:
                    break
            await asyncio.sleep(0.1)
        else:
            # If we exit the loop without breaking, fail the test
            async with client.get('/health') as response:
                health_data = await response.json()
                assert health_data["sessions"] == 0 