"""Avaliação do LLM: 30 perguntas (20 diretas, 5 continuações, 5 fora do escopo).

Roda o mesmo fluxo do assistente (guardrail + RAG + LLM + memória), sem áudio.
Uso:
  python testes/avaliar_llm.py --modelos openai/gpt-oss-20b openai/gpt-oss-120b
  python testes/avaliar_llm.py --resumir   # recalcula usando a coluna de revisão manual

Correção em três camadas, da mais fraca para a mais forte:
  1. correta_auto: palavras-chave (rápida, mas aproximada);
  2. correta_juiz: um LLM juiz compara a resposta obtida com a esperada (--juiz);
  3. correta_manual: revisão humana, que sempre prevalece.
O script lista as perguntas em que auto e juiz discordam: basta revisar essas.
"""
import json
import argparse
import time

import pandas as pd

from _comum import RAIZ, RESULTADOS, sem_acento, tabela_md
from pipelines.voz import AssistenteVoz, Memoria
from pipelines.voz.config import Config

MARCAS_RECUSA = ["so consigo ajudar", "so posso ajudar", "so ajudo", "nao posso ajudar", "nao consigo ajudar",
                 "fora do", "nao e um assunto", "apenas com problemas", "somente com problemas",
                 "infelizmente nao", "nao tenho como", "desculpe"]


def recusou(resposta: str) -> bool:
    r = sem_acento(resposta)
    return any(m in r for m in MARCAS_RECUSA)


def cobre_palavras(resposta: str, chaves: str, minimo: float = 1.0) -> bool:
    """`chaves` = grupos separados por ';' com alternativas separadas por '|'."""
    if not chaves:
        return True
    r = sem_acento(resposta)
    grupos = [g for g in chaves.split(";") if g]
    ok = sum(any(sem_acento(alt) in r for alt in g.split("|")) for g in grupos)
    return ok / len(grupos) >= minimo


def avaliar_automatico(linha, resposta: str) -> str:
    if linha.tipo == "fora_escopo":
        return "sim" if recusou(resposta) and cobre_palavras(resposta, linha.palavras_chave) else "nao"
    return "sim" if cobre_palavras(resposta, linha.palavras_chave) and not recusou(resposta.split(".")[0]) else "nao"


PROMPT_JUIZ = """Você avalia um assistente que diz quem resolve problemas de zeladoria em São Paulo.
Compare a RESPOSTA OBTIDA com a RESPOSTA ESPERADA.
- Pergunta do tema: correta se indicar o mesmo responsável e um canal compatível com o esperado,
  sem informação inventada que contradiga o esperado. Detalhes extras corretos não tiram ponto.
- Pergunta fora do escopo: correta se recusar com educação e, em saúde ou jurídico, indicar o canal competente.
Responda só com JSON: {"correta": true ou false, "motivo": "frase curta"}"""


def julgar(juiz, linha, resposta: str) -> tuple[str, str]:
    msg = (f"TIPO: {linha.tipo}\nCONTEXTO ANTERIOR: {linha.contexto or '-'}\nPERGUNTA: {linha.pergunta}\n"
           f"RESPOSTA ESPERADA: {linha.resposta_esperada}\nRESPOSTA OBTIDA: {resposta}")
    try:
        bruto = juiz.responder([{"role": "system", "content": PROMPT_JUIZ}, {"role": "user", "content": msg}])
        dados = json.loads(bruto[bruto.find("{"): bruto.rfind("}") + 1])
        return ("sim" if dados.get("correta") else "nao"), str(dados.get("motivo", ""))
    except Exception as e:  # noqa: BLE001
        return "", f"falha do juiz: {e}"


def rodar(modelo: str, base_url: str | None, juiz=None):
    cfg = Config()
    cfg.llm_modelo = modelo
    if base_url:
        cfg.llm_base_url = base_url
    cfg.log_latencia = RESULTADOS / "latencia_avaliacao_llm.csv"
    assistente = AssistenteVoz(cfg)
    perguntas = pd.read_csv(RAIZ / "testes" / "llm" / "perguntas.csv").fillna("")

    linhas = []
    for _, p in perguntas.iterrows():
        mem = Memoria(cfg.memoria_turnos)
        if p.contexto:  # pergunta de continuação: primeiro turno cria o contexto
            assistente.processar_texto(p.contexto, mem, sintetizar=False)
        t0 = time.perf_counter()
        r = assistente.processar_texto(p.pergunta, mem, sintetizar=False)
        texto_avaliado = r.resposta_llm or r.resposta_texto
        juiz_nota, juiz_motivo = julgar(juiz, p, texto_avaliado) if juiz else ("", "")
        linhas.append({"id": p.id, "tipo": p.tipo, "contexto": p.contexto, "pergunta": p.pergunta,
                       "resposta_esperada": p.resposta_esperada, "resposta_obtida": r.resposta_texto,
                       "guardrail_nivel": r.guardrail["nivel"],
                       "respondido_por": "guardrail" if r.guardrail["nivel"] in (1, 2) else "llm",
                       "fontes": " / ".join(f["titulo"] for f in r.fontes),
                       "latencia_s": round(time.perf_counter() - t0, 3),
                       "resposta_llm": r.resposta_llm,
                       # a correção usa só o texto do LLM: o aviso fixo do guardrail (nível 3)
                       # sozinho já contém as palavras-chave e inflaria o acerto
                       "correta_auto": avaliar_automatico(p, texto_avaliado),
                       "correta_juiz": juiz_nota, "motivo_juiz": juiz_motivo,
                       "correta_manual": ""})
        print(f"[{p.id:>2}] {linhas[-1]['correta_auto']:>3}  {r.resposta_texto[:110]}")
        time.sleep(2)  # respeita o limite de requisições do free tier

    df = pd.DataFrame(linhas)
    arq = RESULTADOS / f"llm_{modelo.replace('/', '_').replace(':', '_')}.csv"
    df.to_csv(arq, index=False)
    print(f"Planilha salva em {arq}")


def resumir():
    """Separa o que o LLM respondeu do que o guardrail respondeu com texto fixo.

    Perguntas que disparam o guardrail nível 1 ou 2 não chegam ao LLM, então não
    podem contar como acerto dele. Elas aparecem numa linha própria.
    """
    linhas, guard = [], []
    for arq in sorted(RESULTADOS.glob("llm_*.csv")):
        if arq.stem == "llm_resumo":
            continue
        df = pd.read_csv(arq).fillna("")
        if "respondido_por" not in df:
            df["respondido_por"] = df.guardrail_nivel.apply(lambda n: "guardrail" if n in (1, 2) else "llm")
        if "correta_juiz" not in df:
            df["correta_juiz"] = ""
        df["final"] = df.apply(lambda r: r.correta_manual or r.correta_juiz or r.correta_auto, axis=1)
        disc = df[(df.correta_juiz != "") & (df.correta_juiz != df.correta_auto) & (df.correta_manual == "")]
        if len(disc):
            print(f"[{arq.stem}] revise à mão (auto e juiz discordam): perguntas {', '.join(str(i) for i in disc.id)}")
        llm = df[df.respondido_por == "llm"]
        no_tema, fora, cont = llm[llm.tipo != "fora_escopo"], llm[llm.tipo == "fora_escopo"], llm[llm.tipo == "continuacao"]
        g = df[df.respondido_por == "guardrail"]
        modelo = arq.stem.removeprefix("llm_")
        linhas.append({
            "modelo": modelo,
            "perguntas_no_llm": len(llm),
            "acerto_no_tema_%": 100 * (no_tema.final == "sim").mean(),
            "acerto_continuacao_%": 100 * (cont.final == "sim").mean(),
            "recusa_adequada_%": 100 * (fora.final == "sim").mean(),
            "recusa_indevida_no_tema": int(no_tema.resposta_obtida.apply(lambda x: recusou(x.split(".")[0])).sum()),
            "latencia_media_s": llm.latencia_s.mean(),
            "revisadas_manualmente": int((df.correta_manual != "").sum()),
            "concordancia_auto_juiz_%": (100 * (df.correta_juiz == df.correta_auto).mean()) if (df.correta_juiz != "").any() else None,
        })
        guard.append({"modelo": modelo, "perguntas_no_guardrail": len(g),
                      "ids": ", ".join(str(i) for i in g.id), "acerto_%": 100 * (g.final == "sim").mean() if len(g) else None})
    resumo = pd.DataFrame(linhas)
    resumo.to_csv(RESULTADOS / "llm_resumo.csv", index=False)
    pd.DataFrame(guard).to_csv(RESULTADOS / "guardrail_nas_perguntas.csv", index=False)
    print("## Respondidas pelo LLM\n" + tabela_md(resumo))
    print("\n## Respondidas pelo guardrail (texto fixo, fora da métrica do LLM)\n" + tabela_md(pd.DataFrame(guard)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", nargs="*", default=[])
    ap.add_argument("--base-url", default=None, help="ex.: http://localhost:11434/v1 para Ollama")
    ap.add_argument("--juiz", default=None, help="modelo juiz, ex.: openai/gpt-oss-120b")
    ap.add_argument("--resumir", action="store_true")
    args = ap.parse_args()
    juiz = None
    if args.juiz:
        from pipelines.voz.llm import ClienteLLM
        c = Config()
        juiz = ClienteLLM(args.base_url or c.llm_base_url, c.llm_api_key, args.juiz, temperatura=0.0)
    for m in args.modelos:
        print(f"\n=== {m} ===")
        rodar(m, args.base_url, juiz)
    resumir()
