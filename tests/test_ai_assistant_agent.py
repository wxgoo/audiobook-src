import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

import webserver.assistant.ai_assistant_agent as assistant_agent_module
from webserver.assistant.ai_assistant_agent import AIAssistantMCPAgent, TOOL_GROUPS
from webserver.assistant.mcp_client import MCPStreamClient
from webserver.mcp.api_tools import API_TOOLS
from webserver.mcp.mcp_service import MCPService


def test_tool_selection_limits_tools_to_matching_domains():
    tools = [
        {"name": "search_books"},
        {"name": "get_book"},
        {"name": "tts_convert"},
        {"name": "edit_book"},
    ]

    selected_names = {tool["name"] for tool in AIAssistantMCPAgent.select_tools("帮我查一下《三体》", tools)}

    assert selected_names == {"search_books", "get_book"}


def test_tool_selection_includes_all_requested_domains():
    tools = [
        {"name": "search_books"},
        {"name": "get_notes"},
        {"name": "tts_convert"},
    ]

    selected_names = {tool["name"] for tool in AIAssistantMCPAgent.select_tools("查询这本书的笔记并转换成有声书", tools)}

    assert selected_names == {"search_books", "get_notes", "tts_convert"}


def test_unrelated_input_does_not_expose_mcp_tools():
    # 产品行为：关键词未命中时兜底附上最核心的查书工具，避免模型凭空编造伪工具标签。
    assert AIAssistantMCPAgent.select_tools("你好，查看天气怎么样？", [{"name": "search_books"}]) == [{"name": "search_books"}]


def test_library_statistics_route_to_the_small_general_toolset():
    tools = [
        {"name": "get_books_count"},
        {"name": "search_books"},
        {"name": "tts_convert"},
        {"name": "delete_booklist"},
    ]

    selected_names = {tool["name"] for tool in AIAssistantMCPAgent.select_tools("书库里有多少本书？", tools)}

    assert selected_names == {"get_books_count", "search_books"}


def test_explicit_follow_up_keeps_the_previous_turn_toolset():
    tools = [
        {"name": "search_books"},
        {"name": "get_book"},
        {"name": "reading"},
        {"name": "tts_convert"},
    ]

    selected_names = {
        tool["name"]
        for tool in AIAssistantMCPAgent.select_tools("然后呢？", tools, {"search_books", "get_book"})
    }

    assert selected_names == {"search_books", "get_book"}


def test_current_intent_and_follow_up_toolsets_are_combined():
    tools = [
        {"name": "search_books"},
        {"name": "get_book"},
        {"name": "reading"},
        {"name": "tts_convert"},
    ]

    selected_names = {
        tool["name"]
        for tool in AIAssistantMCPAgent.select_tools("把它标记为已读", tools, {"search_books", "get_book"})
    }

    assert selected_names == {"search_books", "get_book", "reading"}


def test_every_mcp_tool_is_assigned_to_a_routing_group(monkeypatch):
    monkeypatch.setattr(assistant_agent_module, "AI_API_KEY", "test-key")
    service = MCPService.__new__(MCPService)
    service.need_login = False
    service.need_login_prompt = ""
    mcp_tools = asyncio.run(service.list_tools())
    routed_names = set().union(*TOOL_GROUPS.values())

    assert set(API_TOOLS) <= routed_names
    assert {tool.name for tool in mcp_tools} <= routed_names
    selected_count_tools = AIAssistantMCPAgent.select_tools(
        "书库里有多少本书？",
        [tool.model_dump() for tool in mcp_tools],
    )
    assert {tool["name"] for tool in selected_count_tools} == TOOL_GROUPS["general"]
    graph = AIAssistantMCPAgent()._build_react_agent([tool.model_dump() for tool in mcp_tools])
    assert callable(graph.astream_events)


def test_mcp_schema_is_converted_to_validated_tool_arguments():
    schema = AIAssistantMCPAgent._tool_args_schema({
        "name": "reading",
        "inputSchema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "integer", "description": "Book ID"},
                "read_state": {"type": "integer", "enum": [0, 1, 2]},
                "note": {"type": "string"},
            },
            "required": ["book_id", "read_state"],
        },
    })

    assert schema.model_validate({"book_id": 7, "read_state": 1}).book_id == 7
    with pytest.raises(ValidationError):
        schema.model_validate({"book_id": 7, "read_state": 4})
    with pytest.raises(ValidationError):
        schema.model_validate({"read_state": 1})


def test_mcp_schema_any_of_requirements_are_preserved():
    schema = AIAssistantMCPAgent._tool_args_schema({
        "name": "query_book_metadata",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "isbn": {"type": "string"},
            },
            "anyOf": [{"required": ["title"]}, {"required": ["isbn"]}],
        },
    })

    assert schema.model_validate({"isbn": "9780000000000"}).isbn == "9780000000000"
    assert schema.model_json_schema()["anyOf"] == [{"required": ["title"]}, {"required": ["isbn"]}]
    with pytest.raises(ValidationError):
        schema.model_validate({})


def test_react_graph_builds_from_an_mcp_tool_definition(monkeypatch):
    monkeypatch.setattr(assistant_agent_module, "AI_API_KEY", "test-key")
    agent = AIAssistantMCPAgent()

    graph = agent._build_react_agent([{
        "name": "search_books",
        "description": "Search the library",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Search term"}},
            "required": ["name"],
        },
    }])

    assert callable(graph.astream_events)


def test_assistant_websocket_origin_must_match_host():
    from webserver.handlers.assistant import is_same_host_origin

    host = "books.example.com:9800"
    assert is_same_host_origin("http://books.example.com:9800", host)
    assert is_same_host_origin("https://books.example.com:9800", host)
    assert not is_same_host_origin("https://evil.example.com", host)
    assert not is_same_host_origin("http://books.example.com", host)
    # 非浏览器客户端不带 Origin：放行
    assert is_same_host_origin("", host)
    assert is_same_host_origin(None, host)
    # 沙箱 iframe 的 "null" / file:// 一律拒绝
    assert not is_same_host_origin("null", host)
    assert not is_same_host_origin("file:///tmp/x", host)


def test_assistant_origin_reverse_proxy_and_default_ports():
    """群晖 :88 反代 / 默认端口归一化：Origin 与候选 host 任一匹配即同源。"""
    from webserver.handlers.assistant import is_same_host_origin, _norm_host

    # 默认端口归一化：:443 / :80 视为等价空端口
    assert _norm_host("Books.Example.com:443") == "books.example.com"
    assert _norm_host("books.example.com:80") == "books.example.com"
    assert _norm_host("[::1]:443") == "[::1]"

    # 群晖反代：Origin 带 :88，request.host 是内部地址，但 X-Forwarded-Host 带 :88
    assert is_same_host_origin(
        "https://annybook.synology.me:88",
        "127.0.0.1:8000",
        ["annybook.synology.me:88"],
    )
    # 反代丢了端口：X-Forwarded-Host 不带端口，Origin 带 :443 -> 归一化后同源
    assert is_same_host_origin(
        "https://annybook.synology.me",
        "127.0.0.1:8000",
        ["annybook.synology.me"],
    )
    # 跨站依然拒绝：即便有一个候选是本机，也不能放行 evil
    assert not is_same_host_origin(
        "https://evil.example.com",
        "127.0.0.1:8000",
        ["annybook.synology.me:88"],
    )


def test_assistant_http_chat_handler_registered():
    """HTTP 降级通道必须注册在路由表中。"""
    from webserver.handlers.assistant import routes

    paths = [r[0] for r in routes()]
    assert "/api/assistant/chat" in paths
    assert "/api/assistant/ws" in paths


def test_mcp_token_is_sent_as_bearer_header_not_in_url():
    client = MCPStreamClient("http://localhost/mcp", "secret-token")

    assert client.base_url == "http://localhost/mcp"
    assert "secret-token" not in client.base_url
    assert client.auth_headers == {"Authorization": "Bearer secret-token"}


def test_mcp_request_log_redacts_credentials():
    from webserver.handlers.mcp import redact

    redacted = redact({
        "method": "tools/call",
        "params": {
            "token": "abc",
            "password": "p",
            "nested": {"api_key": "k", "name": "keep-me"},
        },
        "list": [{"authorization": "Bearer x"}],
    })

    assert redacted["params"]["token"] == "***"
    assert redacted["params"]["password"] == "***"
    assert redacted["params"]["nested"] == {"api_key": "***", "name": "keep-me"}
    assert redacted["list"] == [{"authorization": "***"}]
    assert redacted["method"] == "tools/call"


def test_mcp_tool_listing_failure_is_reported_instead_of_using_fake_tools():
    client = MCPStreamClient("http://localhost/mcp", "")
    client._send_request = AsyncMock(return_value={"error": {"message": "not available"}})

    with pytest.raises(RuntimeError, match="not available"):
        asyncio.run(client.list_tools())


class _FakeMCPClient:
    async def list_tools(self):
        return [{"name": "search_books"}]

    async def close(self):
        return None


class _FakeGraph:
    async def astream_events(self, input_data, config, version):
        assert input_data["messages"][-1]["content"] == "查询《三体》"
        assert config["recursion_limit"] == assistant_agent_module.AGENT_RECURSION_LIMIT
        assert version == "v2"
        yield {"event": "on_tool_start", "name": "search_books"}
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="找到了这本书。")},
        }


def test_react_events_keep_the_existing_websocket_event_shape():
    agent = AIAssistantMCPAgent()
    agent.mcp_client = _FakeMCPClient()

    def build_graph(selected_tools):
        assert [tool["name"] for tool in selected_tools] == ["search_books"]
        return _FakeGraph()

    agent._build_react_agent = build_graph

    events = asyncio.run(_collect_events(agent.process_user_input("查询《三体》")))

    assert events == [
        {"type": "status", "content": "正在调用工具: search_books..."},
        {"type": "content", "content": "找到了这本书。"},
    ]
    assert agent.conversation_history == [
        {"role": "user", "content": "查询《三体》"},
        {"role": "assistant", "content": "找到了这本书。"},
    ]


async def _collect_events(events):
    return [event async for event in events]


class _RecordingMCPClient(_FakeMCPClient):
    def __init__(self, text="查询结果"):
        self.text = text
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments)))
        return {"content": [{"text": self.text}]}


def _capture_langchain_tools(monkeypatch, agent, schema):
    """把 create_agent 换成「只把工具列表递出来」，返回其中的 StructuredTool。"""
    captured = {}

    def fake_create_agent(model, tools, system_prompt=None):
        captured["tools"] = tools
        return SimpleNamespace(astream_events=None)

    monkeypatch.setattr("langchain.agents.create_agent", fake_create_agent)
    agent._get_chat_model = lambda: None
    agent._build_react_agent([{
        "name": "search_books",
        "description": "Search the library",
        "inputSchema": schema,
    }])
    return captured["tools"]


def test_agent_uses_configurable_recursion_limit():
    assert assistant_agent_module.AGENT_RECURSION_LIMIT == 40
    assert assistant_agent_module.MAX_TOOL_CALLS_PER_TURN == 12


def test_repeated_tool_call_replays_previous_result(monkeypatch):
    agent = AIAssistantMCPAgent()
    client = _RecordingMCPClient()
    agent.mcp_client = client
    tools = _capture_langchain_tools(monkeypatch, agent, {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    })

    first = asyncio.run(tools[0].coroutine(name="三体"))
    second = asyncio.run(tools[0].coroutine(name="三体"))

    assert first == "查询结果"
    assert second == "该工具已使用相同参数调用过，请勿重复调用。上一次的结果如下：\n查询结果"
    assert client.calls == [("search_books", {"name": "三体"})]


def test_tool_calls_per_turn_are_capped(monkeypatch):
    monkeypatch.setattr(assistant_agent_module, "MAX_TOOL_CALLS_PER_TURN", 2)
    agent = AIAssistantMCPAgent()
    client = _RecordingMCPClient()
    agent.mcp_client = client
    tools = _capture_langchain_tools(monkeypatch, agent, {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    })

    results = [asyncio.run(tools[0].coroutine(name=term)) for term in ("a", "b", "c")]

    assert results[:2] == ["查询结果", "查询结果"]
    assert results[2].startswith("本轮工具调用次数已达上限")
    assert len(client.calls) == 2


def test_tool_error_is_reported_to_the_model():
    assert AIAssistantMCPAgent._tool_result_text({"error": "工具未登录"}) == "工具调用失败：工具未登录"
    # 有正文时仍以正文为准
    assert AIAssistantMCPAgent._tool_result_text({
        "content": [{"text": "正文"}],
        "error": "附带错误",
    }) == "正文"


def test_recursion_error_returns_partial_answer_instead_of_error_event():
    class _RecursionGraph:
        async def astream_events(self, input_data, config, version):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "run-1",
                "data": {"chunk": SimpleNamespace(content="已查到一部分。")},
            }
            from langgraph.errors import GraphRecursionError

            raise GraphRecursionError("recursion limit reached")

    agent = AIAssistantMCPAgent()
    agent.mcp_client = _FakeMCPClient()
    agent._build_react_agent = lambda selected_tools: _RecursionGraph()

    events = asyncio.run(_collect_events(agent.process_user_input("查询《三体》")))

    # 产品行为：流式片段整段拼成一条 content，并在递归上限时追加友好提示。
    assert events[0]["type"] == "content"
    assert "已查到一部分。" in events[0]["content"]
    assert events[-1]["type"] == "content"
    assert "推理步数已达上限" in events[-1]["content"]
    assert not [event for event in events if event["type"] == "error"]


def test_non_streaming_model_output_is_still_returned():
    class _NonStreamingGraph:
        async def astream_events(self, input_data, config, version):
            yield {
                "event": "on_chat_model_end",
                "run_id": "run-1",
                "data": {"output": SimpleNamespace(content="完整回答。")},
            }

    agent = AIAssistantMCPAgent()
    agent.mcp_client = _FakeMCPClient()
    agent._build_react_agent = lambda selected_tools: _NonStreamingGraph()

    events = asyncio.run(_collect_events(agent.process_user_input("查询《三体》")))

    assert events == [{"type": "content", "content": "完整回答。"}]


def test_mcp_tool_listing_normalizes_snake_case_schema():
    client = MCPStreamClient("http://localhost/mcp", "")
    client._send_request = AsyncMock(return_value={
        "result": {"tools": [{"name": "search_books", "input_schema": {"type": "object"}}, "junk"]},
    })

    tools = asyncio.run(client.list_tools())

    assert tools == [{"name": "search_books", "inputSchema": {"type": "object"}}]


def test_assistant_http_chat_accumulates_text_and_injects_history():
    """HTTP 降级接口应注入历史、累积 content 事件为纯文本返回。"""
    import asyncio
    from unittest import mock

    from webserver.handlers.assistant import AssistantChatHandler

    class FakeAgent:
        def __init__(self, cookies=None):
            self.conversation_history = []
            self.injected = None

        async def initialize(self):
            pass

        async def process_user_input(self, content):
            yield {"type": "status", "content": "调用工具"}
            yield {"type": "content", "content": "回答:" + content}

        async def close(self):
            pass

    written = {}
    instances = []

    def factory(cookies=None):
        a = FakeAgent(cookies)
        instances.append(a)
        return a

    with mock.patch("webserver.assistant.ai_assistant_agent.AIAssistantMCPAgent", factory):
        h = AssistantChatHandler.__new__(AssistantChatHandler)
        h.current_user = b"1"
        h.get_json_body = lambda: {
            "content": "你好",
            "history": [{"role": "user", "content": "旧Q"},
                        {"role": "assistant", "content": "旧A"}],
        }
        h.request = mock.Mock()
        h.request.cookies = {}
        h._headers = {}
        h.set_header = lambda k, v: h._headers.__setitem__(k, v)
        h.write = lambda v: written.setdefault("rsp", v)
        h.finish = lambda: None
        h._is_same_site_origin = lambda o: False
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AssistantChatHandler.post(h))
        loop.close()

    rsp = written["rsp"]
    assert rsp["err"] == "ok"
    assert rsp["text"] == "回答:你好"
    assert rsp["statuses"] == ["调用工具"]
    assert instances[0].conversation_history == [
        {"role": "user", "content": "旧Q"},
        {"role": "assistant", "content": "旧A"},
    ]
