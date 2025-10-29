# src/main.py
# this module contains the main FastAPI application setup


###### IMPORT TOOLS ######
# global imports
from contextlib import asynccontextmanager
import asyncio
import uvloop
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi_limiter import FastAPILimiter
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware

# local imports
from src.routers import api_router
from src.config import get_settings
from src.infrastructure.resources import (
    resources,
    benchmark_token_middleware
)
from src.infrastructure import metrics
from src.logs.log_config import (
    validation_exception_handler,
    http_exception_handler,
)


###### LIFESPAN ######
@asynccontextmanager
async def lifespan(_: FastAPI):
    '''Manage application lifespan: start and stop resources.'''
    await resources.start()
    await FastAPILimiter.init(
        resources.redis,
        prefix=getattr(get_settings(), "RATE_LIMIT_PREFIX", "fapi-limiter"),
    )
    try:
        yield
    finally:
        await resources.stop()


###### USE UVLOOP AS EVENT LOOP ######
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


###### CREATE APP ######
app = FastAPI(lifespan=lifespan)


###### CORS ######
allow_credentials = True
origins = get_settings().CORS_ORIGINS
if allow_credentials and "*" in origins:
    origins = [o for o in origins if o != "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

###### EXCEPTION HANDLERS ######
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

##### STATIC FILES ######
app.mount("/static", StaticFiles(directory=get_settings().STATIC_DIR), name="static")

###### METRICS ######
app.middleware("http")(metrics.http_metrics_middleware)

###### BENCHMARK TOKEN ######
app.add_middleware(
    BaseHTTPMiddleware,
    dispatch=benchmark_token_middleware,
)

###### INCLUDE ROUTERS ######
app.include_router(api_router)

###### ROOT REDIRECT######
@app.get("/", include_in_schema=False)
async def root():
    '''Redirect root to docs in debug mode, else return status ok.'''
    if get_settings().DEBUG:
        return RedirectResponse(url="/docs", status_code=302)
    return {"status": "ok"}


###### RUN APP ######
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=get_settings().API_HOST,
        port=int(get_settings().API_PORT),
        reload=bool(get_settings().DEBUG),
        reload_dirs=["src"] if get_settings().DEBUG else None,
        factory=False,
    )
