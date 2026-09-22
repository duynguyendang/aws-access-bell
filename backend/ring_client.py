import httpx

DEFAULT_RING_API_BASE = "https://api.amazonvision.com"
DEFAULT_RING_OAUTH = "https://oauth.ring.com"


class RingAPIError(RuntimeError):
    pass


class RingClient:
    def __init__(
        self,
        token: str = "",
        base_url: str = DEFAULT_RING_API_BASE,
        oauth_url: str = DEFAULT_RING_OAUTH,
    ):
        self._token = token
        self._base = base_url.rstrip("/")
        self._oauth = oauth_url.rstrip("/")
        self._http = httpx.Client(timeout=10.0)

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def devices(self) -> dict:
        response = self._http.get(
            f"{self._base}/v1/devices",
            headers=self._headers(),
            params={"include": "status,capabilities"},
        )
        response.raise_for_status()
        return response.json()

    def me(self) -> dict:
        response = self._http.get(f"{self._base}/v1/users/me", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def event_history(self, device_id: str, limit: int = 20) -> list[dict]:
        response = self._http.get(
            f"{self._base}/v1/history/devices/{device_id}/events",
            headers=self._headers(),
            params={"limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data") or data.get("events") or []
        return []
