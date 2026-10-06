import logging
import jwt

logger = logging.getLogger("accessbell.oauth")

SCOPES = ["mcp:service", "mcp:tools", "mcp:resources"]


class OAuthContext:
    def __init__(self, scope: str | None):
        self.scope = scope

    @property
    def can_act_for_user(self) -> bool:
        return self.scope == "user"


class OAuthVerifier:
    _jwk_clients: dict[str, jwt.PyJWKClient] = {}

    def __init__(self, settings):
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self._settings.oauth_issuer)

    def canonical_uri(self) -> str:
        return self._settings.mcp_resource

    def protected_resource_metadata(self) -> dict:
        return {
            "resource": self.canonical_uri(),
            "authorization_servers": [self._settings.oauth_issuer] if self.enabled else [],
            "scopes_supported": list(SCOPES),
            "bearer_methods_supported": ["header"],
        }

    def authenticate(self, authorization: str, cf_access_jwt: str = "") -> OAuthContext | None:
        if not self.enabled:
            return None
        header = (authorization or "").strip()
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        cf_mode = False
        if not token and cf_access_jwt and self._settings.cf_access_jwt_enabled:
            token = cf_access_jwt.strip()
            cf_mode = True
        if not token:
            return None
        claims = self._decode(token)
        if claims is None:
            return None
        if not self._token_use_ok(claims):
            return None
        if not self._resource_ok(claims):
            return None
        raw_scopes = claims.get("scope") or ""
        prefix = (self._settings.oauth_scope_prefix or "").rstrip("/")
        scopes = set()
        for s in raw_scopes.split():
            clean = s.split("/", 1)[-1] if prefix and s.startswith(prefix) else s
            scopes.add(clean)
        if scopes & {"mcp:tools", "mcp:resources"}:
            return OAuthContext("user")
        if "mcp:service" in scopes:
            return OAuthContext("service")
        if cf_mode:
            return OAuthContext("user")
        return None

    def _token_use_ok(self, claims: dict) -> bool:
        token_use = claims.get("token_use")
        if token_use and token_use not in {"access", "id"}:
            return False
        return True

    def _resource_ok(self, claims: dict) -> bool:
        claimed = claims.get("resource")
        if claimed is None:
            return not self._settings.oauth_require_resource
        return claimed == self.canonical_uri()

    def _decode(self, token: str) -> dict | None:
        issuer = self._settings.oauth_issuer
        audience = self._settings.oauth_audience
        allowed_client_ids = {cid.strip() for cid in self._settings.oauth_client_ids.split(",") if cid.strip()}
        jwks_url = self._jwks_url()
        client = self._jwk_clients.get(jwks_url)
        if client is None:
            client = jwt.PyJWKClient(jwks_url)
            self._jwk_clients[jwks_url] = client
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            # Cognito access tokens do not have 'aud', but have 'client_id'
            options = {"verify_aud": False} if not audience else {"verify_aud": False}
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=issuer,
                options=options,
            )
            if audience:
                aud = payload.get("aud")
                client_id = payload.get("client_id")
                aud_list = [aud] if isinstance(aud, str) else (aud or [])
                if audience not in aud_list and client_id != audience and client_id not in allowed_client_ids:
                    return None
            return payload
        except jwt.PyJWTError as exc:
            logger.debug("JWT decode failed: %s", exc)
            return None
        except Exception as exc:
            logger.debug("Token validation failed: %s", exc)
            return None

    def _jwks_url(self) -> str:
        if self._settings.oauth_jwks_url:
            return self._settings.oauth_jwks_url
        return f"{self._settings.oauth_issuer.rstrip('/')}/.well-known/jwks.json"