"""Assistente de voz do Quem Resolve? (disciplina 08 - PLN).

Fluxo: microfone -> STT -> guardrail -> RAG -> LLM -> adaptação para fala -> TTS.
Cada etapa é um módulo separado e pode ser trocada sem mexer nas outras.
"""
from .assistente import AssistenteVoz, RespostaTurno
from .memoria import Memoria

__all__ = ["AssistenteVoz", "RespostaTurno", "Memoria"]
