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
