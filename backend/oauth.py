import jwt

SCOPES = ["mcp:service", "mcp:tools", "mcp:resources"]


class OAuthContext:
    def __init__(self, scope: str | None):
        self.scope = scope

    @property
    def can_act_for_user(self) -> bool:
        return self.scope == "user"


class OAuthVerifier:
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
        if not self._resource_ok(claims):
            return None
        scope = claims.get("scope") or ""
        scopes = set(scope.split())
        if scopes & {"mcp:tools", "mcp:resources"}:
            return OAuthContext("user")
        if "mcp:service" in scopes:
            return OAuthContext("service")
        if cf_mode:
            return OAuthContext("user")
        return None

    def _resource_ok(self, claims: dict) -> bool:
        claimed = claims.get("resource")
        if claimed is None:
            return not self._settings.oauth_require_resource
        return claimed == self.canonical_uri()

    def _decode(self, token: str) -> dict | None:
        issuer = self._settings.oauth_issuer
        audience = self._settings.oauth_audience
        try:
            client = jwt.PyJWKClient(self._jwks_url())
            signing_key = client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience or None,
                issuer=issuer,
                options={"verify_aud": bool(audience)},
            )
        except jwt.PyJWTError:
            return None
        except Exception:
            return None

    def _jwks_url(self) -> str:
        if self._settings.oauth_jwks_url:
            return self._settings.oauth_jwks_url
        return f"{self._settings.oauth_issuer.rstrip('/')}/.well-known/jwks.json"