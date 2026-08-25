import json
import logging

import pytest

from glm2api.services.glm_client import GLMWebClient, UpstreamAPIError, is_server_side_tool_error_part


def _fake_client():
    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.glm")
    return client


def _all_tools_error_event():
    return {
        "id": "6a8c700ef3b0c1e26a565a28",
        "conversation_id": "6a8c700ef3b0c1e26a565a27",
        "status": "init",
        "last_error": {},
        "parts": [
            {
                "id": "part1",
                "role": "tool",
                "status": "error",
                "model": "all-tools",
                "meta_data": {"show_type": "mc_tool_result2"},
                "content": [
                    {
                        "type": "tool_result",
                        "tool_calls": {"id": "call_1", "name": "todowrite", "arguments": "{}"},
                    }
                ],
            }
        ],
    }


def test_is_server_side_tool_error_part():
    assert is_server_side_tool_error_part({"role": "tool", "model": "all-tools", "status": "error"})
    assert is_server_side_tool_error_part(
        {"role": "tool", "status": "error", "meta_data": {"show_type": "mc_tool_result2"}}
    )
    # Normal assistant parts with error status are NOT server-side tool errors.
    assert not is_server_side_tool_error_part({"role": "assistant", "model": "moe_5", "status": "error"})
    assert not is_server_side_tool_error_part({"role": "tool", "model": "moe_5", "status": "error"})


def test_raise_for_event_error_ignores_all_tools_part_error():
    GLMWebClient._raise_for_event_error(_fake_client(), _all_tools_error_event(), stream=True)


def test_raise_for_event_error_still_raises_on_real_upstream_error():
    event = _all_tools_error_event()
    event["last_error"] = {"error_code": "X", "err_msg": "内容安全拦截"}
    with pytest.raises(UpstreamAPIError):
        GLMWebClient._raise_for_event_error(_fake_client(), event, stream=True)


def test_raise_for_event_error_still_raises_on_event_status_error_without_payload():
    event = {"status": "error", "last_error": {}, "parts": [{"role": "assistant", "status": "error"}]}
    with pytest.raises(UpstreamAPIError):
        GLMWebClient._raise_for_event_error(_fake_client(), event, stream=True)


def test_raise_for_event_error_ignores_event_status_error_when_only_all_tools_failed():
    event = _all_tools_error_event()
    event["status"] = "error"
    GLMWebClient._raise_for_event_error(_fake_client(), event, stream=True)


def _fake_continue_client(auto_continue=True, max_rounds=2):
    from types import SimpleNamespace

    from glm2api.services.translator import GLMEventAccumulator

    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.glm.continue")
    client.config = SimpleNamespace(glm_auto_continue=auto_continue, glm_auto_continue_max=max_rounds)
    return client


def _degraded_accumulator(conversation_id="conv_1"):
    from glm2api.services.translator import GLMEventAccumulator

    acc = GLMEventAccumulator(model="glm-5.3")
    acc.consume_event(
        {
            "conversation_id": conversation_id,
            "status": "finish",
            "parts": [{"logic_id": "1", "role": "assistant", "content": [{"type": "think", "think": "发现了一些"}]}],
        }
    )
    return acc


def test_should_auto_continue_flags_degraded_answer():
    client = _fake_continue_client()
    acc = _degraded_accumulator()
    degraded, reason = acc.degraded_answer()
    assert degraded and reason
    assert (
        client._should_auto_continue(
            accumulator=acc, finished="stop", degraded=degraded, degrade_reason=reason, continue_count=0
        )
        is True
    )


def test_should_auto_continue_stops_at_max():
    client = _fake_continue_client(max_rounds=1)
    acc = _degraded_accumulator()
    assert (
        client._should_auto_continue(
            accumulator=acc, finished="stop", degraded=True, degrade_reason="x", continue_count=1
        )
        is False
    )


def test_should_auto_continue_respects_disabled_switch():
    client = _fake_continue_client(auto_continue=False)
    acc = _degraded_accumulator()
    assert (
        client._should_auto_continue(
            accumulator=acc, finished="stop", degraded=True, degrade_reason="x", continue_count=0
        )
        is False
    )


def test_should_auto_continue_never_continues_intervene():
    client = _fake_continue_client()
    acc = _degraded_accumulator()
    assert (
        client._should_auto_continue(
            accumulator=acc, finished="intervene", degraded=True, degrade_reason="x", continue_count=0
        )
        is False
    )


def test_should_auto_continue_ignores_clean_answer():
    client = _fake_continue_client()
    acc = _degraded_accumulator(conversation_id="")
    acc._cached_full_text = "正常回答。"
    assert (
        client._should_auto_continue(
            accumulator=acc, finished="stop", degraded=False, degrade_reason="", continue_count=0
        )
        is False
    )


# ---------- vision 上传引用合并 ----------

def test_merge_uploaded_refs_single_image():
    messages = [{"role": "user", "content": [{"type": "text", "text": "User: 图里有几支铅笔？"}]}]
    refs = [
        {
            "type": "image",
            "image": [{"image_id": "fid123", "image_url": "https://t1.chatglm.cn/file/fid123.png"}],
        }
    ]
    GLMWebClient._merge_uploaded_refs(messages, refs)
    content = messages[0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["image"] == refs[0]["image"]
    assert content[0]["text"] == "User: 图里有几支铅笔？"


def test_merge_uploaded_refs_multi_image_text_last():
    messages = [{"role": "user", "content": [{"type": "text", "text": "prompt"}]}]
    refs = [
        {"type": "image", "image": [{"image_id": "a", "image_url": "u1"}]},
        {"type": "image", "image": [{"image_id": "b", "image_url": "u2"}]},
    ]
    GLMWebClient._merge_uploaded_refs(messages, refs)
    content = messages[0]["content"]
    assert [p["type"] for p in content] == ["image", "image"]
    assert content[0]["text"] == "prompt" and content[1].get("text") is None


def test_merge_uploaded_refs_string_content():
    messages = [{"role": "user", "content": "hello"}]
    refs = [{"type": "image", "image": [{"image_id": "a", "image_url": "u"}]}]
    GLMWebClient._merge_uploaded_refs(messages, refs)
    content = messages[0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["text"] == "hello"


def test_merge_uploaded_refs_no_refs_keeps_message():
    messages = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
    out = GLMWebClient._merge_uploaded_refs(messages, [])
    assert out is messages or out[0]["content"][0]["text"] == "x"


def test_upload_file_reference_uses_file_id(monkeypatch):
    import json as _json
    import urllib.request as _ur

    client = _fake_client()
    client.config = type(
        "Cfg",
        (),
        {
            "glm_base_url": "https://chatglm.cn",
            "request_timeout": 10,
            "debug_dump_all": False,
        },
    )()
    client.auth = type(
        "Auth",
        (),
        {
            "get_browser_headers": staticmethod(lambda app_fr="default": {"Content-Type": "application/json"}),
            "read_json_response": staticmethod(lambda resp: {
                "result": {
                    "file_id": "fid999",
                    "file_url": "https://t1.chatglm.cn/file/fid999.png",
                }
            }),
        },
    )()

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResp()

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(_ur, "urlopen", fake_urlopen)
    monkeypatch.setattr(client, "_call_with_account_failover", lambda tag, fn, **kw: _FakeFailoverCtx(lambda: _FakeResp()))

    class _FakeFailoverCtx:
        def __init__(self, fn):
            self._fn = fn

        def __enter__(self):
            return self._fn()

        def __exit__(self, *a):
            return False

    ref = client._upload_file_reference("data:image/png;base64,aGVsbG8=", is_image=True)
    assert ref is not None
    assert ref["type"] == "image"
    assert ref["image"][0]["image_id"] == "fid999"
    assert ref["image"][0]["image_url"] == "https://t1.chatglm.cn/file/fid999.png"
