"""
MCP Stream Client
Supports HTTP Streamable communication (non-SSE)
"""

import json
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    import aiohttp


class MCPStreamClient:
    """
    MCP流式客户端，支持HTTP Streamable通信
    不使用SSE，而是使用HTTP流式响应
    """

    def __init__(self, base_url: str, token: str, cookies: Optional[Dict] = None):
        # 安全：token 一律走 Authorization 请求头，不再拼进 URL。
        # URL（含 query）会进 nginx/Tornado 的 access log，token 一旦入日志就无法回收。
        self.base_url = base_url
        self.token = token or ""
        self.auth_headers = (
            {"Authorization": "Bearer %s" % self.token} if self.token else {}
        )
        self.session: Optional["aiohttp.ClientSession"] = None
        self.tools_cache: Optional[List[Dict]] = None
        self.cookies = cookies
        logging.debug("MCP client initialized: %s", base_url)

    async def connect(self):
        """连接到MCP服务器"""
        import aiohttp
        self.session = aiohttp.ClientSession()
        await self.initialize_session()

    async def initialize_session(self):
        """初始化MCP会话"""
        try:
            # 发送初始化请求
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "DeepSeek-MCP-Client",
                        "version": "1.0.0"
                    }
                }
            }

            response = await self._send_request(init_request)
            return response
        except Exception as e:
            logging.warning("MCP 初始化失败: %s", e)
            return None

    async def _send_request(self, request_data: Dict) -> Dict:
        """发送请求到MCP服务器（支持流式和普通响应）"""
        try:
            headers = {"Content-Type": "application/json"}
            headers.update(self.auth_headers)
            kwargs = {
                "json": request_data,
                "headers": headers
            }
            # 如果有 cookies，添加到请求中
            if self.cookies:
                kwargs["cookies"] = self.cookies

            async with self.session.post(self.base_url, **kwargs) as response:

                # 检查是否流式响应
                content_type = response.headers.get('Content-Type', '')
                if 'stream' in content_type.lower() or 'chunked' in response.headers.get('Transfer-Encoding', ''):
                    # 处理流式响应
                    return await self._read_stream_response(response)
                else:
                    # 处理普通响应
                    return await response.json()

        except Exception as e:
            logging.warning("请求 MCP 服务器失败: %s", e)
            raise

    async def _read_stream_response(self, response) -> Dict:
        """读取HTTP流式响应"""
        try:
            buffer = ""
            async for chunk in response.content.iter_any():
                buffer += chunk.decode('utf-8')
                # 尝试解析完整的JSON对象
                try:
                    data = json.loads(buffer.strip())
                    return data
                except json.JSONDecodeError:
                    # 继续累积数据
                    continue

            # 如果循环结束，尝试最后一次解析
            if buffer:
                try:
                    return json.loads(buffer.strip())
                except:
                    pass

            return {"error": "无法解析流式响应"}
        except Exception as e:
            return {"error": f"读取流式响应失败: {e}"}

    async def list_tools(self) -> List[Dict]:
        """获取可用的工具列表"""
        if self.tools_cache is not None:
            return self.tools_cache

        try:
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }

            response = await self._send_request(tools_request)
            if response.get("error"):
                raise RuntimeError(response["error"].get("message", "MCP tools/list request failed"))
            result = response.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                raise RuntimeError("MCP tools/list response is missing a tools list")
            self.tools_cache = [self._normalize_tool(tool) for tool in result["tools"] if isinstance(tool, dict)]
            return self.tools_cache
        except Exception as e:
            logging.exception("Failed to retrieve MCP tool definitions")
            raise RuntimeError(f"Failed to retrieve MCP tool definitions: {e}") from e

    @staticmethod
    def _normalize_tool(tool: Dict) -> Dict:
        """兼容两种工具 schema 命名：规范里的 camelCase 与部分实现的 snake_case。"""
        tool = dict(tool)
        if "inputSchema" not in tool and "input_schema" in tool:
            tool["inputSchema"] = tool.pop("input_schema")
        return tool

    async def call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """调用指定的工具"""
        try:
            call_request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }

            # 只记录工具名：参数里可能含用户搜索词、笔记正文等隐私信息
            logging.debug("调用 MCP 工具: %s", tool_name)

            response = await self._send_request(call_request)

            if "result" in response:
                result = response["result"]
                logging.debug("MCP 工具调用成功: %s", tool_name)
                return result
            else:
                error = response.get("error", {})
                error_msg = error.get("message", "未知错误")
                logging.warning("MCP 工具调用失败: %s (%s)", tool_name, error_msg)
                return {"error": error_msg}

        except Exception as e:
            logging.warning("MCP 工具调用异常: %s (%s)", tool_name, e)
            return {
                "error": f"Failed to call the tool: {tool_name}",
                "message": str(e)
            }

    async def close(self):
        """关闭连接"""
        if self.session:
            await self.session.close()
