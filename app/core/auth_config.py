import os

JWT_ISSUER = "refresh-token-example"
JWT_AUDIENCE = "protected-api"
JWT_ALGORITHM = "HS256"

#load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
JWT_SECRET = os.getenv("JWT_SECRET", "")
if len(JWT_SECRET.encode("utf-8")) < 32:
    raise RuntimeError("JWT_SECRET must be set to at least 32 bytes")