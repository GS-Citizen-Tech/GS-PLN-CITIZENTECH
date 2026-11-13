"""Calibração do limiar do RAG com as 30 perguntas do teste do LLM.

Para cada limiar, mede:
  - cobertura: % das perguntas do tema que recuperam pelo menos um documento;
  - vazamento: % das perguntas fora do escopo que recuperam algum documento.
Sugere o maior limiar que mantém a cobertura em pelo menos 95%.

Uso: python testes/calibrar_rag.py
"""
import numpy as np
import pandas as pd

from _comum import RAIZ, RESULTADOS, tabela_md
from pipelines.voz.config import Config
from pipelines.voz.rag import BaseConhecimento


def main():
    cfg = Config()
    base = BaseConhecimento(cfg.base_dir, cfg.rag_modelo, top_k=cfg.rag_top_k, limiar=0.0)
    perguntas = pd.read_csv(RAIZ / "testes" / "llm" / "perguntas.csv").fillna("")

    linhas = []
    for _, p in perguntas.iterrows():
        res = base.buscar(p.pergunta, p.contexto)
        top = res[0] if res else (None, 0.0)
        linhas.append({"id": p.id, "tipo": p.tipo, "pergunta": p.pergunta,
                       "melhor_doc": top[0].titulo if top[0] else "", "melhor_score": round(top[1], 3)})
    det = pd.DataFrame(linhas)
    det.to_csv(RESULTADOS / "rag_scores.csv", index=False)

    no_tema = det[det.tipo != "fora_escopo"].melhor_score
    fora = det[det.tipo == "fora_escopo"].melhor_score
    tabela = []
    for lim in np.arange(0.20, 0.65, 0.05):
        tabela.append({"limiar": round(lim, 2), "cobertura_no_tema_%": 100 * (no_tema >= lim).mean(),
                       "vazamento_fora_escopo_%": 100 * (fora >= lim).mean()})
    tab = pd.DataFrame(tabela)
    tab.to_csv(RESULTADOS / "rag_calibracao.csv", index=False)

    ok = tab[tab["cobertura_no_tema_%"] >= 95]
    sugerido = ok.limiar.max() if not ok.empty else tab.limiar.min()
    print(tabela_md(det[["id", "tipo", "melhor_doc", "melhor_score"]]))
    print("\n" + tabela_md(tab))
    print(f"\nLimiar sugerido: {sugerido:.2f} (atual: {cfg.rag_limiar}). "
          f"Se mudar, altere `rag_limiar` em pipelines/voz/config.py e registre no relatório.")
    print("Lembrete: recusar fora do escopo é papel do system prompt; o limiar só evita contexto irrelevante.")


if __name__ == "__main__":
    main()
