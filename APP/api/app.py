from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from APP.dto import ChatRequest, ChatResponse, ModelInfo, TraceInfo
from APP.service import get_chat_service
from harness.models.types import AgentRunResult

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


router = APIRouter(prefix="", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Run chat request")
async def chat(request: ChatRequest) -> ChatResponse:
    service = get_chat_service()
    try:
        result: AgentRunResult = await service.run_chat(request.message, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"API Error: {str(exc)}") from exc

    return ChatResponse(
        text=result.text,
        trace=TraceInfo(
            steps=result.trace.steps,
            tool_calls=result.trace.tool_calls,
            errors=result.trace.errors,
        ),
    )


@router.get("/models", response_model=list[ModelInfo], summary="List available models")
async def list_models() -> list[ModelInfo]:
    service = get_chat_service()
    return [ModelInfo(**item) for item in service.list_models()]


@router.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_chat_service()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="My Deer Flow API",
        description="Application API layer for deer-flow business endpoints.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/swagger",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app

