
import hashlib
import hmac
import logging
from typing import Any

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class InstagramService:
    """Instagram Graph API operations for Meridin."""

    DEFAULT_TIMEOUT = 20.0

    def _url(self, path: str, config: dict) -> str:
        """Build a URL using the configured Graph API base and version."""
        base = str(config.get("graph_base_url") or "").rstrip("/")
        version = str(config.get("graph_version") or "").strip("/")

        if not base or not version:
            raise HTTPException(
                status_code=503,
                detail="Instagram Graph API configuration is missing.",
            )

        return f"{base}/{version}/{path.lstrip('/')}"

    @staticmethod
    def _validate_config(config: dict | None) -> dict:
        config = config or {}

        if not config.get("graph_base_url") or not config.get("graph_version"):
            raise HTTPException(
                status_code=503,
                detail="Instagram Graph API configuration is missing.",
            )

        return config

    @staticmethod
    def _read_json(response: httpx.Response, operation: str) -> dict[str, Any]:
        """Validate an API response and return its JSON object."""
        if response.is_error:
            # Graph API errors are useful for debugging. Do not include
            # request headers or access tokens in logs or error messages.
            error_body = response.text[:1000]

            logger.error(
                "Instagram API request failed: operation=%s status=%s "
                "response=%s",
                operation,
                response.status_code,
                error_body,
            )

            raise HTTPException(
                status_code=502,
                detail={
                    "message": f"Instagram {operation} failed.",
                    "instagram_status": response.status_code,
                    "instagram_error": error_body,
                },
            )

        try:
            result = response.json()
        except ValueError as exc:
            logger.error(
                "Instagram API returned invalid JSON: operation=%s status=%s",
                operation,
                response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="Instagram returned an invalid API response.",
            ) from exc

        if not isinstance(result, dict):
            raise HTTPException(
                status_code=502,
                detail="Instagram returned an unexpected API response.",
            )

        return result

    async def subscribe_messages(
        self,
        ig_user_id: str,
        access_token: str,
        config: dict | None = None,
    ) -> dict[str, Any]:
        """
        Subscribe the connected Instagram account to messaging webhooks.

        This uses /me/subscribed_apps for the configured Instagram Login
        integration. ig_user_id remains in the method signature for
        compatibility with existing route callers.
        """
        config = self._validate_config(config)

        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Instagram account access token is missing.",
            )

        url = self._url("me/subscribed_apps", config)
        fields = "messages,messaging_postbacks"

        logger.info(
            "Instagram subscription requested: account_id=%s fields=%s",
            ig_user_id,
            fields,
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.DEFAULT_TIMEOUT
            ) as client:
                response = await client.post(
                    url,
                    data={
                        "subscribed_fields": fields,
                        "access_token": access_token,
                    },
                )

            result = self._read_json(response, "webhook subscription")

            logger.info(
                "Instagram subscription API succeeded: account_id=%s "
                "http_status=%s",
                ig_user_id,
                response.status_code,
            )

            return result

        except httpx.TimeoutException as exc:
            logger.exception(
                "Instagram subscription request timed out: account_id=%s",
                ig_user_id,
            )
            raise HTTPException(
                status_code=504,
                detail="Instagram subscription request timed out.",
            ) from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Instagram subscription network error: account_id=%s",
                ig_user_id,
            )
            raise HTTPException(
                status_code=502,
                detail="Could not connect to the Instagram API.",
            ) from exc

    async def get_subscribed_apps(
        self,
        access_token: str,
        config: dict | None = None,
    ) -> dict[str, Any]:
        """
        Attempt to inspect the connected account's subscribed apps.

        Confirm this GET operation is supported by the Graph API product and
        version configured for your app. It does not change any subscriptions.
        """
        config = self._validate_config(config)

        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Instagram account access token is missing.",
            )

        url = self._url("me/subscribed_apps", config)

        try:
            async with httpx.AsyncClient(
                timeout=self.DEFAULT_TIMEOUT
            ) as client:
                response = await client.get(
                    url,
                    params={"access_token": access_token},
                )

            result = self._read_json(response, "subscription inspection")

            logger.info(
                "Instagram subscription inspection succeeded: http_status=%s",
                response.status_code,
            )

            return result

        except httpx.TimeoutException as exc:
            logger.exception("Instagram subscription inspection timed out")
            raise HTTPException(
                status_code=504,
                detail="Instagram subscription inspection timed out.",
            ) from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Instagram subscription inspection network error"
            )
            raise HTTPException(
                status_code=502,
                detail="Could not connect to the Instagram API.",
            ) from exc

    async def send_text(
        self,
        ig_user_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        config: dict | None = None,
    ) -> dict[str, Any]:
        """Send a text DM through the configured Instagram Graph API."""
        config = self._validate_config(config)

        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Instagram account access token is missing.",
            )

        if not ig_user_id or not recipient_id:
            raise HTTPException(
                status_code=400,
                detail="Instagram account ID and recipient ID are required.",
            )

        if not text or not text.strip():
            raise HTTPException(
                status_code=400,
                detail="Message text cannot be empty.",
            )

        url = self._url(f"{ig_user_id}/messages", config)

        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text.strip()},
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                )

            result = self._read_json(response, "message sending")

            logger.info(
                "Instagram message API succeeded: account_id=%s "
                "http_status=%s",
                ig_user_id,
                response.status_code,
            )

            return result

        except httpx.TimeoutException as exc:
            logger.exception(
                "Instagram message request timed out: account_id=%s",
                ig_user_id,
            )
            raise HTTPException(
                status_code=504,
                detail="Instagram message request timed out.",
            ) from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Instagram message network error: account_id=%s",
                ig_user_id,
            )
            raise HTTPException(
                status_code=502,
                detail="Could not connect to the Instagram API.",
            ) from exc

    @staticmethod
    def verify_signature(
        raw_body: bytes,
        signature: str | None,
        app_secret: str | None = None,
    ) -> bool:
        """
        Verify Meta's X-Hub-Signature-256 header.

        Always pass the exact raw request body and the correct platform
        App Secret. Do not parse and re-serialize the JSON before verification.
        """
        if not app_secret or not signature:
            return False

        if not signature.startswith("sha256="):
            return False

        supplied_digest = signature[len("sha256="):].strip()

        if len(supplied_digest) != 64:
            return False

        try:
            bytes.fromhex(supplied_digest)
        except ValueError:
            return False

        expected_digest = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(
            supplied_digest.lower(),
            expected_digest,
        )
