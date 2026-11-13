"""Registro de latência por etapa. Grava só tempos, nunca texto ou áudio."""
import csv
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ETAPAS = ["stt", "guardrail", "rag", "llm", "adaptacao", "tts"]


class Cronometro:
    def __init__(self):
        self.tempos: dict[str, float] = {}
        self._inicio = time.perf_counter()

    @contextmanager
    def etapa(self, nome: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.tempos[nome] = self.tempos.get(nome, 0.0) + time.perf_counter() - t0

    def total(self) -> float:
        """Tempo da chegada da pergunta até o áudio da resposta estar pronto para tocar."""
        return time.perf_counter() - self._inicio

    def resumo(self) -> dict:
        dados = {e: round(self.tempos.get(e, 0.0), 3) for e in ETAPAS}
        dados["total_ate_fala"] = round(self.total(), 3)
        return dados


def registrar(caminho: Path, resumo: dict, extras: dict | None = None) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linha = {"momento": datetime.now().isoformat(timespec="seconds"), "turno": uuid.uuid4().hex[:8], **resumo, **(extras or {})}
    novo = not caminho.exists()
    with caminho.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linha))
        if novo:
            w.writeheader()
        w.writerow(linha)
