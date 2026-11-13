"""Avaliação do TTS: 10 respostas sintetizadas, notas de 1 a 5 dadas por 3+ pessoas.

  python testes/avaliar_tts.py gerar --motores piper edge
      -> áudios em testes/tts/audios/ e o formulário testes/tts/formulario_avaliacao.html

Mande o formulário (um único arquivo .html) para cada avaliador pelo WhatsApp ou e-mail.
Ele abre no navegador do celular, sem instalar nada e sem internet. Os áudios aparecem
com códigos neutros (A01, A02...), então ninguém sabe qual motor gerou cada um.
No fim, o avaliador toca em "Gerar minhas notas" e manda de volta o texto que aparece.
Salve cada resposta como testes/tts/notas/avaliador_1.csv, avaliador_2.csv...

  python testes/avaliar_tts.py resumir
"""
import argparse
import base64
import html
import io
import json
import random
import time

import pandas as pd

from _comum import RAIZ, RESULTADOS, tabela_md
from pipelines.voz.adaptacao_fala import adaptar_para_fala
from pipelines.voz.config import Config
from pipelines.voz.tts import criar_sintetizador

PASTA = RAIZ / "testes" / "tts"
NOTAS = PASTA / "notas"


def gerar(motores):
    cfg = Config()
    frases = pd.read_csv(PASTA / "frases_tts.csv")
    audios, tempos = [], []
    for motor in motores:
        tts = criar_sintetizador(motor, cfg.piper_voz, cfg.edge_voz)
        ext = ".wav" if motor == "piper" else ".mp3"
        for _, f in frases.iterrows():
            texto = adaptar_para_fala(f.texto)
            saida = PASTA / "audios" / f"{motor}_{int(f.id):02d}{ext}"
            t0 = time.perf_counter()
            tts.sintetizar(texto, str(saida))
            tempos.append({"motor": motor, "id": f.id, "tempo_s": time.perf_counter() - t0})
            audios.append({"audio": saida.name, "motor": motor, "id_frase": int(f.id), "texto_falado": texto})
            print(f"{saida.name}: {texto}")
    pd.DataFrame(tempos).to_csv(RESULTADOS / "tts_tempos.csv", index=False)

    # Códigos neutros em ordem embaralhada: a avaliação fica cega.
    random.seed(42)
    random.shuffle(audios)
    for i, a in enumerate(audios, 1):
        a["codigo"] = f"A{i:02d}"
    pd.DataFrame(audios).to_csv(PASTA / "gabarito_audios.csv", index=False)
    (PASTA / "formulario_avaliacao.html").write_text(_formulario(audios), encoding="utf-8")
    NOTAS.mkdir(exist_ok=True)
    print(f"\nFormulário pronto: {PASTA / 'formulario_avaliacao.html'}")
    print("Envie esse arquivo para 3 pessoas. As respostas vão em testes/tts/notas/avaliador_N.csv")


def _formulario(audios) -> str:
    itens = []
    for a in audios:
        caminho = PASTA / "audios" / a["audio"]
        mime = "audio/wav" if caminho.suffix == ".wav" else "audio/mpeg"
        b64 = base64.b64encode(caminho.read_bytes()).decode()
        notas = lambda campo: "".join(  # noqa: E731
            f'<label><input type="radio" name="{a["codigo"]}_{campo}" value="{n}">{n}</label>' for n in range(1, 6))
        itens.append(f"""
<section class="item" data-codigo="{a['codigo']}">
  <h2>Áudio {a['codigo']}</h2>
  <audio controls preload="none" src="data:{mime};base64,{b64}"></audio>
  <p class="pergunta">Naturalidade: parece uma pessoa falando?</p><div class="notas">{notas('nat')}</div>
  <p class="pergunta">Clareza: dá para entender tudo, inclusive os números?</p><div class="notas">{notas('cla')}</div>
</section>""")
    codigos = json.dumps([a["codigo"] for a in audios])
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Avaliação de voz · Quem Resolve?</title>
<style>
:root {{ --fundo:#fff; --texto:#1b1b1b; --borda:#d0d0d0; --destaque:#0b5cad; color-scheme: light dark; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fundo:#141414; --texto:#eee; --borda:#444; --destaque:#6aa8ff; }} }}
body {{ font-family: system-ui, sans-serif; background:var(--fundo); color:var(--texto); max-width:640px; margin:auto; padding:16px; font-size:18px; }}
.item {{ border:1px solid var(--borda); border-radius:12px; padding:12px 16px; margin:16px 0; }}
audio {{ width:100%; }}
.notas {{ display:flex; justify-content:space-between; }}
.notas label {{ display:flex; flex-direction:column; align-items:center; padding:8px; }}
.notas input {{ width:28px; height:28px; }}
button {{ font-size:18px; padding:14px; width:100%; border-radius:10px; border:none; background:var(--destaque); color:#fff; margin-top:8px; }}
select, textarea {{ font-size:18px; width:100%; }}
textarea {{ height:180px; }}
.aviso {{ color:#c0392b; }}
</style></head><body>
<h1>Avaliação de voz</h1>
<p>Ouça cada áudio (pode usar fone) e dê duas notas de 1 a 5. <b>1</b> = muito ruim, <b>5</b> = excelente.
Não existe resposta certa: vale a sua impressão.</p>
<label>Quem é você? <select id="avaliador"><option value="">escolha</option>
<option>Avaliador 1</option><option>Avaliador 2</option><option>Avaliador 3</option>
<option>Avaliador 4</option><option>Avaliador 5</option></select></label>
<label>Comentário geral (opcional) <textarea id="comentario" style="height:70px"></textarea></label>
{''.join(itens)}
<button onclick="gerar()">Gerar minhas notas</button>
<p id="msg" class="aviso"></p>
<textarea id="saida" readonly placeholder="As notas aparecem aqui."></textarea>
<button onclick="copiar()">Copiar notas</button>
<p>Depois de copiar, cole numa mensagem e envie para o grupo.</p>
<script>
const CODIGOS = {codigos};
function valor(nome) {{ const m = document.querySelector('input[name="' + nome + '"]:checked'); return m ? m.value : ""; }}
function gerar() {{
  const av = document.getElementById("avaliador").value;
  const msg = document.getElementById("msg");
  if (!av) {{ msg.textContent = "Escolha quem você é no topo da página."; return; }}
  const faltam = CODIGOS.filter(c => !valor(c + "_nat") || !valor(c + "_cla"));
  if (faltam.length) {{ msg.textContent = "Faltam notas nos áudios: " + faltam.join(", "); return; }}
  msg.textContent = "";
  const com = document.getElementById("comentario").value.replace(/[\\n,;]/g, " ");
  const linhas = ["avaliador,codigo,naturalidade_1a5,clareza_1a5,comentario"];
  CODIGOS.forEach((c, i) => linhas.push([av, c, valor(c + "_nat"), valor(c + "_cla"), i === 0 ? com : ""].join(",")));
  const s = document.getElementById("saida"); s.value = linhas.join("\\n"); s.focus(); s.select();
}}
function copiar() {{
  const s = document.getElementById("saida"); if (!s.value) gerar(); s.select();
  try {{ navigator.clipboard.writeText(s.value); }} catch (e) {{ document.execCommand("copy"); }}
}}
</script></body></html>"""


def _ler_notas() -> pd.DataFrame:
    partes = []
    for arq in sorted(NOTAS.glob("*")) if NOTAS.exists() else []:
        if arq.suffix.lower() in (".csv", ".txt"):
            texto = arq.read_text(encoding="utf-8").strip()
            inicio = texto.find("avaliador,codigo")  # tolera texto colado com sobra no início
            partes.append(pd.read_csv(io.StringIO(texto[inicio:] if inicio >= 0 else texto)))
    if not partes:
        raise SystemExit("Nenhuma nota em testes/tts/notas/. Salve as respostas como avaliador_1.csv, avaliador_2.csv...")
    return pd.concat(partes, ignore_index=True)


def resumir():
    av = _ler_notas()
    gab = pd.read_csv(PASTA / "gabarito_audios.csv")
    av = av.merge(gab[["codigo", "motor", "id_frase"]], on="codigo", how="left")
    av = av.dropna(subset=["naturalidade_1a5", "clareza_1a5"])
    av.to_csv(RESULTADOS / "tts_notas_consolidadas.csv", index=False)
    resumo = av.groupby("motor").agg(
        avaliacoes=("codigo", "count"), avaliadores=("avaliador", "nunique"),
        naturalidade_media=("naturalidade_1a5", "mean"), naturalidade_dp=("naturalidade_1a5", "std"),
        clareza_media=("clareza_1a5", "mean"), clareza_dp=("clareza_1a5", "std")).reset_index()
    tempos_arq = RESULTADOS / "tts_tempos.csv"
    if tempos_arq.exists():
        tempos = pd.read_csv(tempos_arq).groupby("motor").tempo_s.mean().rename("tempo_sintese_medio_s")
        resumo = resumo.merge(tempos, on="motor", how="left")
    resumo.to_csv(RESULTADOS / "tts_resumo.csv", index=False)
    por_frase = av.groupby(["motor", "id_frase"])[["naturalidade_1a5", "clareza_1a5"]].mean().reset_index()
    pior = por_frase.sort_values("clareza_1a5").head(3)
    print(tabela_md(resumo))
    print(f"\nAvaliadores: {av.avaliador.nunique()} · O enunciado pede pelo menos 3.")
    print("\nFrases com menor clareza (vale comentar no relatório):\n" + tabela_md(pior))
    comentarios = av[av.comentario.fillna("").astype(str).str.strip() != ""][["avaliador", "comentario"]]
    if not comentarios.empty:
        print("\nComentários:\n" + tabela_md(comentarios))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar")
    g.add_argument("--motores", nargs="+", default=["piper", "edge"])
    sub.add_parser("resumir")
    args = ap.parse_args()
    gerar(args.motores) if args.cmd == "gerar" else resumir()
