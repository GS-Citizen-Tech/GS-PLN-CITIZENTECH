"""Formato de saída de POST /voz/conversar, conforme CONTRATOS.md (seção H).

Modelos Pydantic para a API do Ian validar a resposta. Uso na rota:

    from pipelines.voz.contrato import conversar
    saida = conversar(caminho_audio, historico_json)   # -> VozConversarSaida
"""
import base64
import json
import os

from pydantic import BaseModel, Field

from .assistente import AssistenteVoz
from .memoria import memoria_de_historico, historico_de_memoria


class Fonte(BaseModel):
    titulo: str
    url: str | None = None
    trecho: str | None = None
    score: float | None = Field(None, description="Similaridade do RAG (0 a 1). Campo extra proposto na revisão do contrato G.")


class RespostaAssistente(BaseModel):  # mesmo formato de POST /assistente/perguntar (seção G)
    resposta: str
    fontes: list[Fonte] = []
    sem_fonte: bool
    fora_do_tema: bool
    modelo: str


class Latencias(BaseModel):
    stt_ms: float
    llm_ms: float
    tts_ms: float
    total_ate_fala_ms: float
    guardrail_ms: float = 0.0
    rag_ms: float = 0.0
    adaptacao_ms: float = 0.0


class VozConversarSaida(BaseModel):
    transcricao: str
    resposta: RespostaAssistente
    texto_falado: str
    audio_base64: str | None  # null -> o front usa a voz do navegador
    latencias: Latencias
    guardrail: dict | None = Field(None, description="GuardrailResultado (seção B), para o front mostrar a tela de emergência.")
    historico: list[dict] = Field(default_factory=list, description="Histórico atualizado para a próxima chamada.")


_ASSISTENTE: AssistenteVoz | None = None


def _assistente() -> AssistenteVoz:
    global _ASSISTENTE
    if _ASSISTENTE is None:
        _ASSISTENTE = AssistenteVoz()
        _ASSISTENTE.aquecer()
    return _ASSISTENTE


def conversar(caminho_audio: str, historico_json: str | None = None,
              assistente: AssistenteVoz | None = None) -> VozConversarSaida:
    a = assistente or _assistente()
    historico = json.loads(historico_json) if historico_json else []
    mem = memoria_de_historico(historico, a.cfg.memoria_turnos)
    r = a.processar_audio(caminho_audio, mem, apagar_audio=True)

    audio_b64 = None
    if r.audio_resposta:
        with open(r.audio_resposta, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        os.remove(r.audio_resposta)

    lat = {f"{k}_ms": round(v * 1000, 1) for k, v in r.latencias.items()}
    lat["total_ate_fala_ms"] = lat.pop("total_ate_fala_ms")
    modelo = " + ".join(x for x in (getattr(a._llm, "nome", ""), "MiniLM-L12 multilíngue") if x)

    return VozConversarSaida(
        transcricao=r.transcricao,
        resposta=RespostaAssistente(resposta=r.resposta_texto, fontes=[Fonte(**f) for f in r.fontes],
                                    sem_fonte=r.sem_fonte, fora_do_tema=r.fora_do_tema, modelo=modelo),
        texto_falado=r.resposta_falada,
        audio_base64=audio_b64,
        latencias=Latencias(**lat),
        guardrail=r.guardrail,
        historico=historico_de_memoria(mem),
    )
