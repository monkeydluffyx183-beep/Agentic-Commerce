"""
MCP Server - Unified Model Context Protocol server

Mounts at /mcp and exposes all commerce tools to AI agents.
Uses the official MCP SDK with streamable-HTTP transport.
"""

from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


async def create_mcp_server(shopify: Any, razorpay: Any) -> Server:
    """
    Create and configure the MCP server
    
    Args:
        shopify: ShopifyPort implementation
        razorpay: RazorpayPort implementation
    
    Returns:
        Configured MCP Server instance
    """
    from .tools import TOOL_DEFINITIONS, execute_tool
    from ..core.types import RequestContext
    
    server = Server("agent-commerce")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available MCP tools"""
        tools = []
        for name, definition in TOOL_DEFINITIONS.items():
            tools.append(
                Tool(
                    name=name,
                    description=definition["description"],
                    inputSchema=definition["inputSchema"],
                )
            )
        return tools
    
    @server.call_tool()
    async def call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> list[TextContent]:
        """Execute a tool call"""
        # Note: In production, ctx would come from session/auth
        # This is a simplified version for demonstration
        ctx = RequestContext(
            user_id=None,  # Would be set from auth
            merchant_id=None,  # Would be set from auth
            agent_id=None,
            session_id="demo-session",
            scopes=["catalog:read", "cart:write", "checkout:create", "payment:request"],
            idempotency_key=None,
        )
        
        try:
            result = await execute_tool(
                tool_name=name,
                arguments=arguments,
                ctx=ctx,
                shopify=shopify,
                razorpay=razorpay,
            )
            
            return [
                TextContent(
                    type="text",
                    text=str(result),
                )
            ]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error executing {name}: {str(e)}",
                )
            ]
    
    return server


async def run_stdio_server(shopify: Any, razorpay: Any) -> None:
    """Run MCP server over stdio (for local agent integration)"""
    server = await create_mcp_server(shopify, razorpay)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
