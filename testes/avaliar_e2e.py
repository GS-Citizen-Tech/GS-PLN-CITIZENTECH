"""Avaliação ponta a ponta: 10 conversas de 3 turnos, latência por etapa.

  python testes/avaliar_e2e.py

O enunciado não exige voz humana neste teste (só no de STT e no vídeo). Por isso,
quando não há áudio gravado para um turno, a fala do "cidadão" é gerada com vozes
sintéticas diferentes (alternando masculina e feminina) e o turno é marcado como
"sintetico" na planilha. Se o grupo gravar algum áudio em testes/e2e/audios/, ele é
usado no lugar. O relatório deve informar quantos turnos foram de cada tipo.
"""
import argparse
import shutil
import tempfile

import pandas as pd

from _comum import RAIZ, RESULTADOS, localizar_audio, tabela_md
from pipelines.voz import AssistenteVoz, Memoria
from pipelines.voz.config import Config
from pipelines.voz.latencia import ETAPAS

PASTA = RAIZ / "testes" / "e2e"
VOZES_CIDADAO = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"]


class VozCidadao:
    """Gera a fala do cidadão. Tenta o edge-tts (2 vozes); sem internet, usa o Piper."""

    def __init__(self, cfg: Config):
        from pipelines.voz.tts import SintetizadorEdge, SintetizadorPiper
        self.edge = [SintetizadorEdge(v) for v in VOZES_CIDADAO]
        self.piper = None
        self._cfg, self._piper_cls = cfg, SintetizadorPiper

    def falar(self, texto: str, conversa: int) -> tuple[str, str]:
        voz = self.edge[conversa % len(self.edge)]
        try:
            return voz.sintetizar(texto), voz.nome
        except Exception:  # noqa: BLE001 - sem acesso ao serviço da Microsoft
            self.piper = self.piper or self._piper_cls(self._cfg.piper_voz)
            return self.piper.sintetizar(texto), self.piper.nome


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-gravados", action="store_true", help="ignora turnos sem áudio gravado")
    args = ap.parse_args()

    cfg = Config()
    cfg.log_latencia = RESULTADOS / "latencia_e2e_log.csv"
    assistente = AssistenteVoz(cfg)
    assistente.aquecer()  # carrega e roda uma inferência de cada modelo: o 1º turno não sai inflado
    voz = None if args.so_gravados else VozCidadao(cfg)

    roteiro = pd.read_csv(PASTA / "conversas.csv")
    linhas = []
    for conversa, turnos in roteiro.groupby("conversa"):
        mem = Memoria(cfg.memoria_turnos)
        for _, t in turnos.sort_values("turno").iterrows():
            original = localizar_audio(PASTA / "audios", t.arquivo_audio)
            if original is not None:
                entrada, voz_usada = "gravado", "humana"
                tmp = tempfile.NamedTemporaryFile(suffix=original.suffix, delete=False).name
                shutil.copy(original, tmp)  # a cópia é apagada pelo assistente; o original fica para a entrega
            elif voz:
                entrada = "sintetico"
                tmp, voz_usada = voz.falar(t.texto_roteiro, int(conversa))
            else:
                continue
            r = assistente.processar_audio(tmp, mem, apagar_audio=True)
            linhas.append({"conversa": conversa, "turno": t.turno, "entrada": entrada, "voz": voz_usada,
                           "roteiro": t.texto_roteiro, "transcricao": r.transcricao, "resposta": r.resposta_texto,
                           "guardrail_nivel": r.guardrail["nivel"], **r.latencias})
            print(f"C{conversa}T{t.turno} [{entrada}] {r.latencias['total_ate_fala']:.2f}s | "
                  f"{r.transcricao} -> {r.resposta_texto[:70]}")

    det = pd.DataFrame(linhas)
    if det.empty:
        raise SystemExit("Nenhum turno processado.")
    det.to_csv(RESULTADOS / "e2e_detalhado.csv", index=False)
    cols = ETAPAS + ["total_ate_fala"]
    resumo = pd.DataFrame({"etapa": cols, "media_s": [det[c].mean() for c in cols],
                           "mediana_s": [det[c].median() for c in cols], "p95_s": [det[c].quantile(0.95) for c in cols],
                           "max_s": [det[c].max() for c in cols]})
    resumo.to_csv(RESULTADOS / "e2e_resumo.csv", index=False)
    n_grav = int((det.entrada == "gravado").sum())
    print(f"\n{det.conversa.nunique()} conversas, {len(det)} turnos ({n_grav} gravados, {len(det) - n_grav} sintéticos)")
    print(tabela_md(resumo))


if __name__ == "__main__":
    main()
