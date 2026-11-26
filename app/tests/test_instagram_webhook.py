import hashlib
import hmac

from app.api.routes.instagram import _extract_message_events, hmac_compare_tokens
from app.services.instagram_service import InstagramService


def test_extracts_inbound_text_message():
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "customer-1"},
                "recipient": {"id": "business-1"},
                "timestamp": 1730000000000,
                "message": {"mid": "mid-in-1", "text": "Is this kurti available?"},
            }]
        }]
    }

    events = _extract_message_events(payload)

    assert len(events) == 1
    assert events[0]["sender_id"] == "customer-1"
    assert events[0]["recipient_id"] == "business-1"
    assert events[0]["is_echo"] is False
    assert events[0]["text"] == "Is this kurti available?"


def test_extracts_business_echo_instead_of_discarding_it():
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "business-1"},
                "recipient": {"id": "customer-1"},
                "timestamp": 1730000000000,
                "message": {
                    "mid": "mid-echo-1",
                    "text": "Yes, XL is available.",
                    "is_echo": True,
                },
            }]
        }]
    }

    events = _extract_message_events(payload)

    assert len(events) == 1
    assert events[0]["sender_id"] == "business-1"
    assert events[0]["recipient_id"] == "customer-1"
    assert events[0]["is_echo"] is True
    assert events[0]["text"] == "Yes, XL is available."


def test_extracts_attachment_only_message():
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "customer-1"},
                "recipient": {"id": "business-1"},
                "message": {
                    "mid": "mid-image-1",
                    "attachments": [{
                        "type": "image",
                        "payload": {"url": "https://example.com/image.jpg"},
                    }],
                },
            }]
        }]
    }

    events = _extract_message_events(payload)

    assert len(events) == 1
    assert events[0]["text"] == "[instagram_attachment:image]"
    assert events[0]["image_url"] == "https://example.com/image.jpg"


def test_webhook_verify_token_uses_constant_time_comparison_semantics():
    assert hmac_compare_tokens("token-value", "token-value")
    assert not hmac_compare_tokens("wrong", "token-value")
    assert not hmac_compare_tokens(None, "token-value")


def test_instagram_signature_validation():
    body = b'{"object":"instagram","entry":[]}'
    secret = "test-app-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert InstagramService.verify_signature(body, f"sha256={digest}", secret)
    assert not InstagramService.verify_signature(body, f"sha256={digest}", "wrong-secret")
    assert not InstagramService.verify_signature(body, "invalid", secret)


def test_extracts_self_authored_business_message():
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "business-1"},
                "recipient": {"id": "customer-1"},
                "message": {"mid": "mid-self-1", "text": "We have this in blue.", "is_self": True},
            }]
        }]
    }

    events = _extract_message_events(payload)

    assert len(events) == 1
    assert events[0]["is_echo"] is True



def test_extracts_story_reply_context():
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "customer-1"},
                "recipient": {"id": "business-1"},
                "message": {
                    "mid": "mid-story-1",
                    "text": "Is this available?",
                    "reply_to": {
                        "story": {
                            "id": "story-media-123",
                            "url": "https://example.com/story.jpg",
                        }
                    },
                },
            }]
        }]
    }

    events = _extract_message_events(payload)

    assert len(events) == 1
    assert events[0]["source_type"] == "story_reply"
    assert events[0]["source_id"] == "story-media-123"
    assert events[0]["source_url"] == "https://example.com/story.jpg"
    assert events[0]["text"] == "Is this available?"


def test_extracts_shared_instagram_post_context():
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "customer-1"},
                "recipient": {"id": "business-1"},
                "message": {
                    "mid": "mid-post-1",
                    "attachments": [{
                        "type": "ig_post",
                        "payload": {
                            "id": "post-media-456",
                            "url": "https://example.com/post.jpg",
                        },
                    }],
                },
            }]
        }]
    }

    events = _extract_message_events(payload)

    assert len(events) == 1
    assert events[0]["source_type"] == "shared_post"
    assert events[0]["source_id"] == "post-media-456"
    assert events[0]["text"] == "[instagram_attachment:post]"
