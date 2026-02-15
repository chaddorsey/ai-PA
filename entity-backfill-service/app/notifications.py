import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from app.checkpoint import CheckpointDB

logger = logging.getLogger(__name__)

VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:backfill@example.com")


class NotificationManager:
    def __init__(self, db: CheckpointDB):
        self.db = db
        self._vapid_keys: dict = {}

    async def initialize(self):
        existing = await self._load_vapid_keys()
        if existing:
            self._vapid_keys = existing
        else:
            self._vapid_keys = self._generate_vapid_keys()
            await self._save_vapid_keys(self._vapid_keys)

    def _generate_vapid_keys(self) -> dict:
        from cryptography.hazmat.primitives.asymmetric import ec

        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        # Public key: uncompressed point, base64url no padding
        pk_bytes = public_key.public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        public_key_b64 = (
            base64.urlsafe_b64encode(pk_bytes).rstrip(b"=").decode("utf-8")
        )

        # Private key: raw 32-byte D value, base64url no padding
        raw_d = private_key.private_numbers().private_value.to_bytes(32, "big")
        private_key_b64 = (
            base64.urlsafe_b64encode(raw_d).rstrip(b"=").decode("utf-8")
        )

        return {
            "public_key": public_key_b64,
            "private_key": private_key_b64,
        }

    async def _load_vapid_keys(self) -> Optional[dict]:
        async with self.db._db.cursor() as cur:
            await cur.execute(
                "SELECT public_key, private_key FROM vapid_keys WHERE id=1"
            )
            row = await cur.fetchone()
            if row:
                return {
                    "public_key": row["public_key"],
                    "private_key": row["private_key"],
                }
            return None

    async def _save_vapid_keys(self, keys: dict):
        await self.db._db.execute(
            "INSERT OR REPLACE INTO vapid_keys (id, public_key, private_key) VALUES (1, ?, ?)",
            (keys["public_key"], keys["private_key"]),
        )
        await self.db._db.commit()

    async def get_vapid_keys(self) -> dict:
        return self._vapid_keys

    async def add_subscription(self, subscription: dict):
        now = datetime.now(timezone.utc).isoformat()
        await self.db._db.execute(
            "INSERT INTO push_subscriptions (subscription_json, created_at) VALUES (?, ?)",
            (json.dumps(subscription), now),
        )
        await self.db._db.commit()

    async def get_subscriptions(self) -> List[dict]:
        async with self.db._db.cursor() as cur:
            await cur.execute(
                "SELECT id, subscription_json, created_at FROM push_subscriptions"
            )
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def send_notification(self, title: str, body: str, url: str = "/"):
        subs = await self.get_subscriptions()
        if not subs:
            logger.debug("No push subscribers, skipping notification")
            return

        payload = json.dumps({"title": title, "body": body, "url": url})
        failed_ids = []

        for sub in subs:
            sub_info = json.loads(sub["subscription_json"])
            try:
                webpush(
                    subscription_info=sub_info,
                    data=payload,
                    vapid_private_key=self._vapid_keys["private_key"],
                    vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
                )
            except WebPushException as e:
                logger.warning(f"Push failed for subscription {sub['id']}: {e}")
                if "410" in str(e) or "404" in str(e):
                    failed_ids.append(sub["id"])
            except Exception as e:
                logger.error(f"Unexpected push error: {e}")

        for sid in failed_ids:
            await self.db._db.execute(
                "DELETE FROM push_subscriptions WHERE id=?", (sid,)
            )
        if failed_ids:
            await self.db._db.commit()
