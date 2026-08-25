"""断线自动重试 + 风控介入（intervene）处理的回归测试。

场景来自 2026-08-25 日志：
- 14:37:11 上游 output_sensitive 风控介入被当成 502 掐断流（不应重试，应正常收尾附介入文案）
- 流式传输中途断掉后，未输出内容可整体重发，已输出一半应走同会话续话
"""

import json
import logging
from types import SimpleNamespace

import pytest

from glm2api.services.glm_client import GLMWebClient, UpstreamAPIError


class _Lease:
    ticket = 0

    def release(self):
        pass


class _Queue:
    def acquire(self, key):
        return _Lease()


def _scripted_client(scripts, retry_max=1):
    """构造只替换网络层的 GLMWebClient：_iter_sse_events 按 scripts 顺序逐个脚本吐事件，
    脚本里出现 Exception 实例时抛出。返回 (client, 状态记录)。"""
    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.retry")
    client.config = SimpleNamespace(
        glm_auto_continue=True,
        glm_auto_continue_max=2,
        glm_stream_retry_max=retry_max,
        debug_dump_all=False,
    )
    state = {"open_chat_calls": 0, "continue_calls": 0, "deleted": []}

    client._resolve_tools = lambda payload: (None, None)
    client.request_queue = _Queue()
    client._get_preferred_account_index = lambda ticket: None

    def _fake_response():
        return SimpleNamespace(close=lambda: None)

    def _open_chat_stream(payload, preferred_account_index=None):
        state["open_chat_calls"] += 1
        return _fake_response(), "asst-1"

    def _open_continuation_stream(**kwargs):
        state["continue_calls"] += 1
        state["last_continue_conversation_id"] = kwargs["conversation_id"]
        return _fake_response()

    iters = iter(scripts)

    def _iter_sse_events(response):
        for item in next(iters):
            if isinstance(item, Exception):
                raise item
            yield item

    client._open_chat_stream = _open_chat_stream
    client._open_continuation_stream = _open_continuation_stream
    client._iter_sse_events = _iter_sse_events
    client.delete_conversation = lambda cid, assistant_id=None: state["deleted"].append(cid)
    return client, state


def _collect(client, payload):
    return [chunk.decode("utf-8") for chunk in client.stream_chat_completion(payload)]


PAYLOAD = {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}], "stream": True}


def test_stream_retry_full_resend_when_nothing_sent():
    """断线时尚未输出任何内容 → 整体重发原始请求，客户端拿到完整答案。"""
    err = UpstreamAPIError(status_code=502, message="GLM stream request error", payload={})
    scripts = [
        [err],
        [
            {"conversation_id": "c2", "status": "init", "parts": [
                {"logic_id": "1", "role": "assistant", "content": [{"type": "text", "text": "完整答案"}]}
            ]},
            {"conversation_id": "c2", "status": "finish", "parts": []},
        ],
    ]
    client, state = _scripted_client(scripts)
    out = _collect(client, PAYLOAD)
    assert state["open_chat_calls"] == 2
    assert state["continue_calls"] == 0
    joined = "".join(out)
    assert "完整答案" in joined
    assert "[DONE]" in out[-1]


def test_stream_retry_continues_when_partial_content_sent():
    """断线时已输出一部分 → 同一上游会话续话，续文拼进同一条流。"""
    err = UpstreamAPIError(status_code=502, message="GLM stream request error", payload={})
    scripts = [
        [
            {"conversation_id": "c1", "status": "init", "parts": [
                {"logic_id": "1", "role": "assistant", "content": [{"type": "text", "text": "前半段"}]}
            ]},
            err,
        ],
        [
            {"conversation_id": "c1", "status": "init", "parts": [
                {"logic_id": "2", "role": "assistant", "content": [{"type": "text", "text": "后半段。"}]}
            ]},
            {"conversation_id": "c1", "status": "finish", "parts": []},
        ],
    ]
    client, state = _scripted_client(scripts)
    out = _collect(client, PAYLOAD)
    assert state["open_chat_calls"] == 1
    assert state["continue_calls"] == 1
    assert state["last_continue_conversation_id"] == "c1"
    joined = "".join(out)
    assert "前半段" in joined
    assert "后半段" in joined
    assert "[DONE]" in out[-1]


def test_stream_retry_exhaustion_raises_original_error():
    """重试次数用尽 → 抛出原错误，客户端收到 502（而不是假装完成）。"""
    err = UpstreamAPIError(status_code=502, message="GLM stream request error", payload={})
    client, state = _scripted_client([[err], [err]], retry_max=1)
    gen = client.stream_chat_completion(PAYLOAD)
    with pytest.raises(UpstreamAPIError):
        list(gen)
    assert state["open_chat_calls"] == 2


def test_intervene_is_graceful_not_error():
    """风控介入（output_sensitive/REJECT）不是传输错误：正常收尾并附介入文案，不重试。"""
    scripts = [
        [
            {"conversation_id": "c1", "status": "init", "parts": [
                {"logic_id": "1", "role": "assistant", "content": [{"type": "think", "think": "思考中"}]}
            ]},
            {
                "conversation_id": "c1",
                "status": "intervene",
                "last_error": {
                    "intervene_type": "output_sensitive",
                    "intervene_text": "非常抱歉，我目前无法提供你需要的具体信息",
                    "risk_level": "REJECT",
                },
                "parts": [
                    {"logic_id": "1", "role": "assistant", "status": "intervene", "content": []}
                ],
            },
        ],
    ]
    client, state = _scripted_client(scripts)
    out = _collect(client, PAYLOAD)
    assert state["open_chat_calls"] == 1
    assert state["continue_calls"] == 0
    joined = "".join(out)
    assert "非常抱歉" in joined
    assert "[DONE]" in out[-1]


def test_degraded_answer_reset_after_full_resend():
    """整体重发前 accumulator.reset() 必须清干净（conversation_id/思考/解析器）。"""
    from glm2api.services.translator import GLMEventAccumulator

    acc = GLMEventAccumulator(model="glm-5.3")
    acc.consume_event({
        "conversation_id": "old",
        "status": "init",
        "parts": [{"logic_id": "1", "role": "assistant", "content": [{"type": "think", "think": "x"}]}],
    })
    assert acc.conversation_id == "old"
    assert acc.has_any_content()
    acc.reset()
    assert acc.conversation_id == ""
    assert not acc.has_any_content()
    assert acc.degraded_answer() == (False, "")
