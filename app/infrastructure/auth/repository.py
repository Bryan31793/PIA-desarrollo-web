import os
from datetime import datetime

from redis import Redis, WatchError


class RefreshTokenRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def _access_key(token_id: str) -> str:
        return f"auth:access:{token_id}"

    @staticmethod
    def _refresh_key(token_id: str) -> str:
        return f"auth:refresh:{token_id}"

    def add_pair(
        self,
        access_token_id: str,
        access_expires_at: datetime,
        refresh_token_id: str,
        refresh_expires_at: datetime,
    ) -> None:
        # Redis elimina cada registro al vencer; la pareja se registra junta.
        with self._client.pipeline(transaction=True) as pipe:
            pipe.set(
                self._access_key(access_token_id),
                "1",
                pxat=int(access_expires_at.timestamp() * 1000),
            )
            pipe.set(
                self._refresh_key(refresh_token_id),
                access_token_id,
                pxat=int(refresh_expires_at.timestamp() * 1000),
            )
            pipe.execute()

    def consume_refresh(self, token_id: str) -> bool:
        refresh_key = self._refresh_key(token_id)
        with self._client.pipeline() as pipe:
            while True:
                try:
                    # WATCH evita el doble consumo incluso entre procesos.
                    pipe.watch(refresh_key)
                    access_token_id = pipe.get(refresh_key)
                    if access_token_id is None:
                        return False
                    if isinstance(access_token_id, bytes):
                        access_token_id = access_token_id.decode("utf-8")

                    pipe.multi()
                    pipe.delete(refresh_key, self._access_key(access_token_id))
                    pipe.execute()
                    return True
                except WatchError:
                    # Otra petición consumió el refresh o este expiró.
                    continue

    def is_access_token_active(self, token_id: str) -> bool:
        return bool(self._client.exists(self._access_key(token_id)))


refresh_token_repository = RefreshTokenRepository(
    Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
)