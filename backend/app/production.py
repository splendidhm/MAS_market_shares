import base64
import hmac
import os

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.main import app

password = os.environ["MAS_PASSWORD"]
if not 4 <= len(password) <= 16 or not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
    raise RuntimeError("Set MAS_PASSWORD to 4-16 characters and provide a PostgreSQL DATABASE_URL")
credential = base64.b64encode(("mas:" + password).encode())


@app.middleware("http")
async def private_access(request, call_next):
    if request.url.path != "/api/health":
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "basic" or not hmac.compare_digest(token.encode(), credential):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="MAS"'})
        origin = request.headers.get("origin")
        if origin and origin != "https://" + request.headers.get("host", ""):
            return Response(status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Frame-Options"] = "DENY"
    return response


app.mount("/", StaticFiles(directory=os.getenv("MAS_STATIC_DIR", "public"), html=True))
