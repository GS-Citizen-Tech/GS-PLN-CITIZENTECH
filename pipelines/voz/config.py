"""Configuração central, lida de variáveis de ambiente (.env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAIZ = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    # STT
    stt_modelo: str = field(default_factory=lambda: os.getenv("STT_MODELO", "small"))
    stt_device: str = field(default_factory=lambda: os.getenv("STT_DEVICE", "auto"))
    # LLM: qualquer endpoint compatível com a API da OpenAI (Groq, Gemini, Ollama)
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_modelo: str = field(default_factory=lambda: os.getenv("LLM_MODELO", "openai/gpt-oss-120b"))
    llm_temperatura: float = 0.2
    llm_max_tokens: int = 300
    # TTS
    tts_motor: str = field(default_factory=lambda: os.getenv("TTS_MOTOR", "piper"))  # piper | edge
    piper_voz: str = field(default_factory=lambda: os.getenv("PIPER_VOZ", str(RAIZ / "modelos/piper/pt_BR-faber-medium.onnx")))
    edge_voz: str = field(default_factory=lambda: os.getenv("EDGE_VOZ", "pt-BR-FranciscaNeural"))
    # RAG
    rag_modelo: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    rag_top_k: int = 3
    rag_limiar: float = 0.40
    base_dir: Path = RAIZ / "base_conhecimento"
    # Memória e logs
    memoria_turnos: int = 6
    log_latencia: Path = RAIZ / "logs" / "latencia.csv"
