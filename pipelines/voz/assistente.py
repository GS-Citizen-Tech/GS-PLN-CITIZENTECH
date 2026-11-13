"""Orquestrador: liga os módulos em sequência a cada turno da conversa."""
import os
from dataclasses import dataclass, field

from . import guardrail as guardrail_mod
from .adaptacao_fala import adaptar_para_fala
from .config import Config
from .latencia import Cronometro, registrar
from .memoria import Memoria
from .prompts import montar_mensagens

MSG_NAO_OUVI = "Desculpe, não consegui entender o áudio. Pode falar de novo, um pouco mais perto do microfone?"
MARCAS_RECUSA = ["so consigo ajudar", "so posso ajudar", "so ajudo", "nao posso ajudar", "nao consigo ajudar",
                 "fora do", "nao e um assunto", "apenas com problemas", "somente com problemas",
                 "infelizmente nao", "nao tenho como"]


def parece_recusa(texto: str) -> bool:
    t = guardrail_mod.normalizar(texto)
    return any(m in t for m in MARCAS_RECUSA)


MSG_ERRO_LLM = "Desculpe, estou com um problema para responder agora. Enquanto isso, você pode ligar para o SP156 no 156."


@dataclass
class RespostaTurno:
    transcricao: str
    resposta_texto: str
    resposta_falada: str
    audio_resposta: str | None
    fontes: list[dict] = field(default_factory=list)
    latencias: dict = field(default_factory=dict)
    guardrail: dict = field(default_factory=dict)
    resposta_llm: str = ""  # só o que o LLM gerou, sem o aviso do guardrail (usado na avaliação)
    sem_fonte: bool = False
    fora_do_tema: bool = False


class AssistenteVoz:
    """Os componentes são criados sob demanda e podem ser injetados (útil nos testes)."""

    def __init__(self, cfg: Config | None = None, stt=None, llm=None, tts=None, rag=None, registrar_log: bool = True):
        self.cfg = cfg or Config()
        self._stt, self._llm, self._tts, self._rag = stt, llm, tts, rag
        self.registrar_log = registrar_log

    # ---------- componentes (lazy) ----------
    @property
    def stt(self):
        if self._stt is None:
            from .stt import TranscritorWhisper
            self._stt = TranscritorWhisper(self.cfg.stt_modelo, self.cfg.stt_device)
        return self._stt

    @property
    def llm(self):
        if self._llm is None:
            from .llm import ClienteLLM
            c = self.cfg
            self._llm = ClienteLLM(c.llm_base_url, c.llm_api_key, c.llm_modelo, c.llm_temperatura, c.llm_max_tokens)
        return self._llm

    @property
    def tts(self):
        if self._tts is None:
            from .tts import criar_sintetizador
            self._tts = criar_sintetizador(self.cfg.tts_motor, self.cfg.piper_voz, self.cfg.edge_voz)
        return self._tts

    @property
    def rag(self):
        if self._rag is None:
            from .rag import BaseConhecimento
            c = self.cfg
            self._rag = BaseConhecimento(c.base_dir, c.rag_modelo, c.rag_top_k, c.rag_limiar)
        return self._rag

    def aquecer(self) -> None:
        """Carrega os modelos E roda uma inferência de cada um.

        Na GPU, a primeira inferência é bem mais lenta que as seguintes. Sem isso,
        o 1º turno de cada sessão inflaria a média de latência. O LLM não é
        chamado aqui para não gastar a cota da API.
        """
        _ = self.llm
        audio = self.tts.sintetizar("Olá, tudo bem? Tem um buraco na minha rua.")
        try:
            self.stt.transcrever(audio)
        finally:
            try:
                os.remove(audio)
            except OSError:
                pass
        self.rag.buscar("buraco na rua")

    # ---------- fluxo ----------
    def processar_audio(self, caminho_audio: str, memoria: Memoria, apagar_audio: bool = True,
                        sintetizar: bool = True) -> RespostaTurno:
        crono = Cronometro()
        try:
            with crono.etapa("stt"):
                texto = self.stt.transcrever(caminho_audio)
        finally:
            if apagar_audio:  # LGPD: retenção mínima, o áudio some logo após a transcrição
                try:
                    os.remove(caminho_audio)
                except OSError:
                    pass
        return self.processar_texto(texto, memoria, crono, sintetizar)

    def processar_texto(self, texto: str, memoria: Memoria, crono: Cronometro | None = None,
                        sintetizar: bool = True) -> RespostaTurno:
        crono = crono or Cronometro()
        texto = (texto or "").strip()
        fontes = []
        resposta_llm = ""

        with crono.etapa("guardrail"):
            g = guardrail_mod.avaliar(texto) if texto else guardrail_mod.ResultadoGuardrail(0)

        if not texto:
            resposta = MSG_NAO_OUVI
        elif g.nivel in (1, 2):
            # Emergência ou violência: resposta fixa, sem LLM e sem guardar nada na memória.
            resposta = g.mensagem
        else:
            with crono.etapa("rag"):
                fontes = self.rag.buscar(texto, memoria.ultima_pergunta())
            mensagens = montar_mensagens(memoria.mensagens(), fontes, texto)
            with crono.etapa("llm"):
                try:
                    resposta = self.llm.responder(mensagens)
                except Exception as e:  # noqa: BLE001 - caminho seguro se a API cair
                    from .llm import ModeloIndisponivel
                    if isinstance(e, ModeloIndisponivel):
                        raise  # erro de configuração: tem que aparecer, não pode virar resposta genérica
                    print(f"[LLM] erro: {e}")
                    resposta = MSG_ERRO_LLM
            resposta_llm = resposta
            if g.nivel == 3:
                resposta = f"{g.mensagem} {resposta}"
            memoria.adicionar("user", texto)
            memoria.adicionar("assistant", resposta)

        with crono.etapa("adaptacao"):
            falada = adaptar_para_fala(resposta)

        audio = None
        # Em violência doméstica a resposta NÃO é falada em voz alta (discrição, PRD 4.2).
        if sintetizar and not g.saida_rapida:
            with crono.etapa("tts"):
                audio = self.tts.sintetizar(falada)

        lat = crono.resumo()
        if self.registrar_log:
            registrar(self.cfg.log_latencia, lat, {
                "stt_modelo": getattr(self._stt, "nome", ""), "llm_modelo": getattr(self._llm, "nome", ""),
                "tts_motor": getattr(self._tts, "nome", ""), "guardrail_nivel": g.nivel})

        return RespostaTurno(
            transcricao=texto,
            resposta_texto=resposta,
            resposta_falada=falada,
            audio_resposta=audio,
            fontes=[{"titulo": f"{d.fonte} - {d.titulo}", "url": d.fonte_url, "trecho": d.texto[:300], "score": round(s, 3)}
                    for d, s in fontes],
            latencias=lat,
            guardrail=g.to_dict(),
            resposta_llm=resposta_llm,
            sem_fonte=g.nivel in (0, 3) and bool(texto) and not fontes,
            fora_do_tema=g.nivel in (0, 3) and bool(texto) and parece_recusa(resposta),
        )


def processar_turno(caminho_audio: str, historico_json: str | None = None) -> dict:
    """Ponto de entrada para a rota POST /voz/conversar (formato de CONTRATOS.md, seção H)."""
    from .contrato import conversar
    return conversar(caminho_audio, historico_json).model_dump()
