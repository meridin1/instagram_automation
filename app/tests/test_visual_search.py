import pytest

from app.api.routes.instagram import _extract_message_events
from app.services.response_service import build_response
from app.services.intent import IntentResult
from app.services.visual_search_service import cosine_similarity_normalized, _public_https_url


def test_extract_image_url_and_keep_accompanying_text():
    payload = {
        "entry": [{"messaging": [{
            "sender": {"id": "customer-1"},
            "recipient": {"id": "business-1"},
            "message": {
                "mid": "mid-1",
                "text": "ee type kurti ningal vilkkunundo?",
                "attachments": [{"type": "image", "payload": {"url": "https://lookaside.fbsbx.com/photo.jpg"}}],
            },
        }]}]
    }
    events = _extract_message_events(payload)
    assert len(events) == 1
    assert events[0]["text"] == "ee type kurti ningal vilkkunundo?"
    assert events[0]["image_url"] == "https://lookaside.fbsbx.com/photo.jpg"
    assert events[0]["has_image"] is True


def test_attachment_only_image_still_has_internal_marker_and_url():
    payload = {
        "entry": [{"messaging": [{
            "sender": {"id": "customer-1"},
            "recipient": {"id": "business-1"},
            "message": {"mid": "mid-2", "attachments": [{"type": "image", "payload": {"url": "https://lookaside.fbsbx.com/photo.jpg"}}]},
        }]}]
    }
    event = _extract_message_events(payload)[0]
    assert event["text"] == "[instagram_attachment:image]"
    assert event["image_url"].endswith("photo.jpg")


def test_cosine_similarity_for_normalized_vectors():
    assert cosine_similarity_normalized([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity_normalized([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity_normalized([1.0], [1.0, 0.0]) == -1.0


def test_reject_non_https_and_private_ip_urls():
    assert not _public_https_url("http://example.com/image.jpg")
    assert not _public_https_url("https://127.0.0.1/image.jpg")
    assert not _public_https_url("https://example.com/image.jpg", meta_only=True)


@pytest.mark.asyncio
async def test_image_only_response_uses_visual_catalogue_candidates():
    intent = IntentResult(intent="unknown", confidence=0.4, source="rules", entities={})
    reply, status = await build_response(
        "unused-client", intent, None, "[instagram_attachment:image]",
        visual_candidates=[{
            "name": "Floral Kurti", "price": 1299, "sale_price": None,
            "visual_similarity": 0.83, "product_url": "https://shop.example/kurti",
        }],
        has_image=True,
    )
    assert status == "automated"
    assert "Floral Kurti" in reply
    assert "1299" in reply
    assert "shop.example/kurti" in reply
