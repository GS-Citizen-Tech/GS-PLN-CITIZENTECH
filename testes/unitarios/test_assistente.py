"""Fluxo do orquestrador com componentes falsos (não precisa de GPU nem de internet)."""
import os
import tempfile
from pathlib import Path

from pipelines.voz import AssistenteVoz, Memoria
from pipelines.voz.config import Config


class FakeSTT:
    nome = "fake"
    def __init__(self, texto=""): self.texto = texto
    def transcrever(self, caminho): return self.texto


class FakeLLM:
    nome = "fake"
    def __init__(self): self.chamadas = 0
    def responder(self, mensagens):
        self.chamadas += 1
        return "Quem resolve é a Prefeitura, pelo SP156."


class FakeTTS:
    nome = "fake"
    def sintetizar(self, texto, saida=None):
        f = tempfile.NamedTemporaryFile(delete=False, suffix=".wav"); f.close(); return f.name


class FakeRAG:
    def buscar(self, pergunta, anterior=""): return []


def novo(stt_texto=""):
    cfg = Config()
    cfg.log_latencia = Path(tempfile.mkdtemp()) / "lat.csv"
    llm = FakeLLM()
    return AssistenteVoz(cfg, stt=FakeSTT(stt_texto), llm=llm, tts=FakeTTS(), rag=FakeRAG()), llm, cfg


def test_audio_apagado_apos_transcricao():
    a, _, _ = novo("tem um buraco na rua")
    caminho = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    a.processar_audio(caminho, Memoria())
    assert not os.path.exists(caminho)


def test_nivel3_separa_resposta_do_llm():
    a, _, _ = novo()
    r = a.processar_texto("tem um fio soltando faísca", Memoria())
    assert r.resposta_texto.startswith("Primeiro, não chegue perto")
    assert r.resposta_llm == "Quem resolve é a Prefeitura, pelo SP156."


def test_nivel1_nao_chama_llm_nem_guarda_memoria():
    a, llm, _ = novo()
    mem = Memoria()
    r = a.processar_texto("estou sentindo cheiro de gás", mem)
    assert llm.chamadas == 0 and len(mem) == 0 and r.resposta_llm == ""


def test_violencia_domestica_sem_audio():
    a, _, _ = novo()
    r = a.processar_texto("meu marido me bate", Memoria())
    assert r.audio_resposta is None


def test_log_de_latencia_sem_texto():
    a, _, cfg = novo()
    a.processar_texto("a lixeira da praça está quebrada", Memoria())
    conteudo = cfg.log_latencia.read_text(encoding="utf-8")
    assert "lixeira" not in conteudo and "total_ate_fala" in conteudo
