import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import create_db_and_tables, settings
from app.controllers import (
    auth_controller,
    me_controller,
    organisation_controller,
    task_controller,
    team_controller,
)
from app.exceptions.exception import AppError

logging.basicConfig(level=logging.INFO)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.AUTO_CREATE_TABLES:
        create_db_and_tables()
    yield


app = FastAPI(title="TaskBoard", description="Team task boards for multiple organisations.", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, error: AppError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.message, "code": error.code})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, error: RequestValidationError):
    fields: dict[str, str] = {}
    for item in error.errors():
        location = [str(part) for part in item["loc"] if part not in ("body", "query", "path")]
        message = str(item["msg"]).removeprefix("Value error, ").removeprefix("value is not a valid email address: ")
        if "email" in location and not message.startswith("Enter"):
            message = "Enter a valid email address. " + message[0].upper() + message[1:]
        fields.setdefault(location[-1] if location else "request", message)
    first = next(iter(fields.values()), "The request was not valid.")
    return JSONResponse(status_code=422, content={"detail": first, "code": "validation_error", "fields": fields})


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


app.include_router(auth_controller.router)
app.include_router(me_controller.router)
app.include_router(organisation_controller.create_router)
app.include_router(organisation_controller.router)
app.include_router(team_controller.router)
app.include_router(task_controller.router)

# In production the built React app is served by FastAPI itself (one origin, no CORS needed).
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found", "code": "not_found"})
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
