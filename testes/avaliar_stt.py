"""Avaliação do STT: WER (jiwer) em 20 áudios, comparando tamanhos do Whisper.

Uso:  python testes/avaliar_stt.py --modelos small medium
Saídas em testes/resultados/: stt_detalhado.csv, stt_resumo.csv, stt_vies.csv
"""
import argparse
import time

import jiwer
import pandas as pd

from _comum import RAIZ, RESULTADOS, localizar_audio, normalizar_wer, tabela_md
from pipelines.voz.stt import TranscritorWhisper

PASTA = RAIZ / "testes" / "stt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", nargs="+", default=["small", "medium"])
    ap.add_argument("--device", default="auto")
    ap.add_argument("--sem-prompt", action="store_true", help="desliga o vocabulário do domínio no Whisper")
    args = ap.parse_args()

    manifesto = pd.read_csv(PASTA / "manifesto.csv").fillna("")
    manifesto["caminho"] = [localizar_audio(PASTA / "audios", a) for a in manifesto.arquivo]
    faltando = list(manifesto[manifesto.caminho.isna()].arquivo)
    if faltando:
        print(f"Atenção: {len(faltando)} áudio(s) não encontrados e serão ignorados: {faltando}")
        manifesto = manifesto[~manifesto.arquivo.isin(faltando)]
    if manifesto.empty:
        raise SystemExit("Nenhum áudio encontrado em testes/stt/audios. Veja testes/stt/COMO_GRAVAR.md")

    linhas = []
    for nome in args.modelos:
        print(f"\n=== Whisper {nome} ===")
        stt = TranscritorWhisper(nome, args.device, usar_prompt_dominio=not args.sem_prompt)
        stt.transcrever(str(manifesto.caminho.iloc[0]))  # aquecimento, fora da medição
        for _, r in manifesto.iterrows():
            t0 = time.perf_counter()
            hip, dur = stt.transcrever_detalhado(str(r.caminho))
            tempo = time.perf_counter() - t0
            ref_n, hip_n = normalizar_wer(r.referencia), normalizar_wer(hip)
            wer = jiwer.wer(ref_n, hip_n) if hip_n else 1.0
            linhas.append({"modelo": nome, "arquivo": r.arquivo, "falante": r.falante, "ruido": r.ruido,
                           "referencia": r.referencia, "transcricao": hip, "wer": wer,
                           "tempo_s": tempo, "duracao_audio_s": dur, "rtf": tempo / dur if dur else None})
            print(f"{r.arquivo}  WER={wer:.2f}  {tempo:.2f}s  -> {hip}")

    det = pd.DataFrame(linhas)
    det.to_csv(RESULTADOS / "stt_detalhado.csv", index=False)

    def wer_corpus(g):  # WER agregado (soma dos erros / soma das palavras), mais justo que a média simples
        return jiwer.wer([normalizar_wer(x) for x in g.referencia], [normalizar_wer(x) or "-" for x in g.transcricao])

    resumo = det.groupby("modelo").apply(lambda g: pd.Series({
        "WER_geral": wer_corpus(g),
        "WER_sem_ruido": wer_corpus(g[g.ruido == "nao"]),
        "WER_com_ruido": wer_corpus(g[g.ruido == "sim"]) if (g.ruido == "sim").any() else None,
        "tempo_medio_s": g.tempo_s.mean(),
        "RTF_medio": g.rtf.mean(),
    })).reset_index()
    resumo.to_csv(RESULTADOS / "stt_resumo.csv", index=False)

    vies = det.groupby(["modelo", "falante"]).apply(lambda g: pd.Series({
        "n_audios": len(g), "WER": wer_corpus(g)})).reset_index()
    perfis = manifesto[manifesto.perfil_voz != ""].set_index("falante").perfil_voz
    vies["perfil_voz"] = vies.falante.map(perfis).fillna("")
    vies.to_csv(RESULTADOS / "stt_vies.csv", index=False)

    print("\n## Resumo por modelo\n" + tabela_md(resumo))
    print("\n## WER por falante (análise de viés)\n" + tabela_md(vies))


if __name__ == "__main__":
    main()
