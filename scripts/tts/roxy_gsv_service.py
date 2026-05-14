from __future__ import annotations

import io
import os
import sys
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field


# ── Path setup ────────────────────────────────────────────────────────────────
# WORKSPACE_ROOT is derived from the script location (two levels up from this file)
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_ROOT = Path(os.environ["ROXY_GSV_DEPLOY_ROOT"]) if "ROXY_GSV_DEPLOY_ROOT" in os.environ else WORKSPACE_ROOT / "artifacts" / "gpt-sovits-roxy"
GPT_SOVITS_ROOT = DEPLOY_ROOT / "GPT-SoVITS"
OUTPUT_ROOT = DEPLOY_ROOT / "outputs"

# ── Model / audio config (env-driven, no hardcoded fallbacks) ───────────────
def _get_weights(key: str, label: str) -> Path:
    path = Path(os.environ[key])
    if not path.exists():
        raise RuntimeError(f"{label} not found: {path} (set {key} env var)")
    return path


DEFAULT_T2S_WEIGHTS = _get_weights("ROXY_GSV_T2S_WEIGHTS", "T2S weights")
DEFAULT_VITS_WEIGHTS = _get_weights("ROXY_GSV_VITS_WEIGHTS", "VITS weights")
DEFAULT_REF_AUDIO = _get_weights("ROXY_GSV_REF_AUDIO", "Reference audio")

DEFAULT_PROMPT_LANG = os.environ.get("ROXY_GSV_PROMPT_LANG", "ja")
DEFAULT_TEXT_LANG = os.environ.get("ROXY_GSV_TEXT_LANG", "zh")
DEFAULT_HOST = os.environ.get("ROXY_GSV_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ROXY_GSV_PORT", "9881"))


def _stem_to_prompt_text(audio_path: Path) -> str:
    return unicodedata.normalize("NFC", audio_path.stem)


def _require_path(path: Path, label: str) -> Path:
    if not path.exists():
        raise RuntimeError(f"{label} not found: {path}")
    return path


_require_path(GPT_SOVITS_ROOT, "GPT-SoVITS root")

os.chdir(GPT_SOVITS_ROOT)
sys.path.insert(0, str(GPT_SOVITS_ROOT))
sys.path.insert(0, str(GPT_SOVITS_ROOT / "GPT_SoVITS"))

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config  # noqa: E402


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    text_lang: str = Field(default=DEFAULT_TEXT_LANG)
    ref_audio_path: str | None = None
    prompt_text: str | None = None
    prompt_lang: str = Field(default=DEFAULT_PROMPT_LANG)
    top_k: int = 15
    top_p: float = 1.0
    temperature: float = 1.0
    text_split_method: str = "cut5"
    batch_size: int = 1
    batch_threshold: float = 0.75
    split_bucket: bool = True
    speed_factor: float = 1.0
    fragment_interval: float = 0.3
    seed: int = -1
    parallel_infer: bool = True
    repetition_penalty: float = 1.35
    media_type: str = "wav"


class TTSFileRequest(TTSRequest):
    output_path: str | None = None


def build_tts() -> TTS:
    config = TTS_Config(
        {
            "custom": {
                "device": "cpu",
                "is_half": False,
                "version": "v2ProPlus",
                "t2s_weights_path": str(DEFAULT_T2S_WEIGHTS),
                "vits_weights_path": str(DEFAULT_VITS_WEIGHTS),
                "bert_base_path": str(
                    GPT_SOVITS_ROOT / "GPT_SoVITS" / "pretrained_models" / "chinese-roberta-wwm-ext-large"
                ),
                "cnhuhbert_base_path": str(
                    GPT_SOVITS_ROOT / "GPT_SoVITS" / "pretrained_models" / "chinese-hubert-base"
                ),
            }
        }
    )
    return TTS(config)


APP = FastAPI(title="Roxy GPT-SoVITS Local TTS", version="1.0.0")
TTS_PIPELINE = build_tts()
TTS_LOCK = threading.Lock()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def build_payload(req: TTSRequest) -> dict:
    ref_audio_path = Path(req.ref_audio_path) if req.ref_audio_path else DEFAULT_REF_AUDIO
    _require_path(ref_audio_path, "Reference audio")
    prompt_text = req.prompt_text or _stem_to_prompt_text(ref_audio_path)
    return {
        "text": req.text,
        "text_lang": req.text_lang,
        "ref_audio_path": str(ref_audio_path),
        "prompt_lang": req.prompt_lang,
        "prompt_text": prompt_text,
        "top_k": req.top_k,
        "top_p": req.top_p,
        "temperature": req.temperature,
        "text_split_method": req.text_split_method,
        "batch_size": req.batch_size,
        "batch_threshold": req.batch_threshold,
        "split_bucket": req.split_bucket,
        "speed_factor": req.speed_factor,
        "fragment_interval": req.fragment_interval,
        "seed": req.seed,
        "parallel_infer": req.parallel_infer,
        "repetition_penalty": req.repetition_penalty,
        "media_type": req.media_type,
    }


def synthesize(req: TTSRequest) -> tuple[int, np.ndarray, dict]:
    payload = build_payload(req)
    try:
        with TTS_LOCK:
            sr, audio = next(TTS_PIPELINE.run(payload))
    except StopIteration as exc:
        raise HTTPException(status_code=500, detail="TTS returned no audio") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return sr, audio, payload


@APP.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "device": "cpu",
        "model_version": "v2ProPlus",
        "default_ref_audio": str(DEFAULT_REF_AUDIO),
        "default_prompt_lang": DEFAULT_PROMPT_LANG,
        "default_text_lang": DEFAULT_TEXT_LANG,
    }


@APP.post("/tts")
def tts(req: TTSRequest) -> Response:
    sr, audio, _ = synthesize(req)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    return Response(content=buf.getvalue(), media_type="audio/wav")


@APP.post("/tts/file")
def tts_to_file(req: TTSFileRequest) -> dict:
    sr, audio, payload = synthesize(req)
    if req.output_path:
        output_path = Path(req.output_path).expanduser()
    else:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_ROOT / f"roxy-{ts}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), audio, sr, format="WAV")
    duration_seconds = float(len(audio) / sr)
    return {
        "ok": True,
        "output_path": str(output_path),
        "sample_rate": sr,
        "duration_seconds": round(duration_seconds, 3),
        "ref_audio_path": payload["ref_audio_path"],
        "prompt_text": payload["prompt_text"],
        "text_lang": payload["text_lang"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(APP, host=DEFAULT_HOST, port=DEFAULT_PORT)