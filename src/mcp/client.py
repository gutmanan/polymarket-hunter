import httpx
from typing import Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MCPClient:
    """Client for interacting with MCP servers"""
    
    def __init__(self, server_url: str, timeout: int = 30):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def call_tool(
        self, 
        tool_name: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[Any, Any]:
        """Call a tool on the MCP server"""
        try:
            payload = {
                "tool": tool_name,
                "parameters": parameters or {}
            }
            
            logger.info(f"Calling MCP tool: {tool_name} on {self.server_url}")
            
            response = await self.client.post(
                f"{self.server_url}/call-tool",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"MCP response: {result}")
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"MCP call failed: {e}")
            raise
    
    async def list_tools(self) -> list[Dict[str, Any]]:
        """List available tools on the MCP server"""
        try:
            response = await self.client.get(f"{self.server_url}/list-tools")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to list tools: {e}")
            raise
    
    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()
