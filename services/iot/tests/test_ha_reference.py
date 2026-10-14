"""Pure parsing tests for the Home Assistant reference library (no network, no database)."""
import pytest

from services.iot import ha_reference as R

DOC = """---
title: Imou
description: Integrate Imou smart devices into Home Assistant.
ha_category:
  - Camera
  - Sensor
ha_iot_class: Cloud Polling
ha_config_flow: true
---

{% include integrations/config_flow.md %}

Use the **App ID** from the Imou Open Platform. {{ site.x }}
"""


def test_docs_front_matter_and_liquid_are_handled():
    meta, body = R.clean_docs_markdown(DOC)
    assert meta["title"] == "Imou" and meta["ha_category"] == ["Camera", "Sensor"] and meta["ha_iot_class"] == "Cloud Polling"
    assert "{%" not in body and "{{" not in body and "App ID" in body


def test_cooked_html_keeps_code_and_lists():
    text = R.cooked_to_text("<p>Try this</p><pre><code>light:\n  - platform: x</code></pre><ul><li>one</li><li>two</li></ul>")
    assert "```\nlight:\n  - platform: x\n```" in text and "- one" in text and "- two" in text


def test_topic_doc_prefers_accepted_answer_and_omits_authors():
    topic = {"id": 7, "slug": "imou-offline", "title": "Imou offline", "tags": ["camera"], "posts_count": 3,
             "accepted_answer": {"post_number": 3},
             "post_stream": {"posts": [
                 {"post_number": 1, "cooked": "<p>My camera is offline</p>", "username": "alice"},
                 {"post_number": 2, "cooked": "<p>Same here</p>", "username": "bob"},
                 {"post_number": 3, "cooked": "<p>Check the region</p>", "username": "carol"}]}}
    doc = R._topic_doc(topic)
    assert doc["doc_key"] == "community:7" and doc["url"].endswith("/t/imou-offline/7")
    assert "Accepted answer\nCheck the region" in doc["body"] and "Resolved: yes" in doc["body"]
    assert not any(name in doc["body"] for name in ("alice", "bob", "carol"))


def test_topic_doc_is_bounded_and_empty_topics_skipped():
    big = {"id": 1, "title": "t", "post_stream": {"posts": [{"post_number": 1, "cooked": "<p>" + "x" * 50000 + "</p>"}]}}
    assert len(R._topic_doc(big)["body"]) < R.MAX_TOPIC_BODY + 300
    assert R._topic_doc({"id": 2, "title": "t", "post_stream": {"posts": []}}) is None


def test_integration_id_is_validated_before_any_request():
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(R.fetch_integration("../../etc/passwd"))


def test_topic_tags_may_be_objects():
    topic = {"id": 3, "title": "t", "tags": [{"id": 1, "name": "zha"}, "matter"],
             "post_stream": {"posts": [{"post_number": 1, "cooked": "<p>q</p>"}]}}
    assert "Tags: zha, matter" in R._topic_doc(topic)["body"]
