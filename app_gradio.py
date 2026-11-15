"""Interface do assistente de voz (demonstração da disciplina 08).

Rode com:  python app_gradio.py          (local)
           python app_gradio.py --share  (Colab: gera link público temporário)
Para proteger o link público com senha, defina APP_USUARIO e APP_SENHA no ambiente.
"""
import argparse
import os

import gradio as gr

from pipelines.voz import AssistenteVoz, Memoria
from pipelines.voz.adaptacao_fala import adaptar_para_fala
from pipelines.voz.config import Config

CFG = Config()
ASSISTENTE = AssistenteVoz(CFG)
HOST_LLM = CFG.llm_base_url.split("/")[2]
LLM_LOCAL = HOST_LLM.startswith(("localhost", "127.0.0.1"))
TTS_NUVEM = CFG.tts_motor == "edge"
CONTATO = os.getenv("CONTATO_GRUPO", "(e-mail do grupo)")

TEXTO_CONSENTIMENTO = f"""
### Antes de começar
Este assistente **escuta sua voz** para entender o seu pedido.

- Sua voz é transcrita **neste computador** e o arquivo de áudio é **apagado logo depois** da transcrição.
- {"O texto da sua pergunta também é processado neste computador." if LLM_LOCAL else f"O **texto** da sua pergunta é enviado ao serviço de inteligência artificial `{HOST_LLM}` para gerar a resposta."}
- {"O **texto da resposta** é enviado ao serviço de voz da Microsoft para virar áudio." if TTS_NUVEM else "A resposta é transformada em voz **neste computador**."}
- A conversa fica guardada só enquanto esta página estiver aberta. Ao clicar em **Nova conversa** ou fechar a página, ela é apagada.
- Guardamos apenas os **tempos de resposta** de cada etapa, sem texto e sem áudio.
- Não fale dados pessoais como CPF, RG ou telefone.
- Você pode desistir a qualquer momento fechando a página. Dúvidas ou pedidos de exclusão: {CONTATO}.
- Em emergência, **ligue direto**: 190 Polícia, 192 SAMU, 193 Bombeiros, 199 Defesa Civil.
"""

# Versão para ser ouvida: frases simples, na mesma ordem do texto escrito.
AVISO_FALADO = (
    "Antes de começar, um aviso. Este assistente escuta a sua voz para entender o seu pedido. "
    "A sua voz é transformada em texto neste computador, e a gravação é apagada logo em seguida. "
    + ("O texto da pergunta também fica neste computador. " if LLM_LOCAL
       else "O texto da sua pergunta é enviado a um serviço de inteligência artificial pela internet. ")
    + ("O texto da resposta é enviado ao serviço de voz da Microsoft. " if TTS_NUVEM else "")
    + "A conversa é apagada quando você fecha a página. Não fale CPF, RG nem telefone. "
    "Em emergência, ligue direto: 190 para a Polícia, 192 para o SAMU, 193 para os Bombeiros. "
    "Se concordar, toque no botão Concordo e começar."
)
_audio_aviso: str | None = None


def ouvir_aviso():
    global _audio_aviso
    if _audio_aviso is None or not os.path.exists(_audio_aviso):
        _audio_aviso = ASSISTENTE.tts.sintetizar(adaptar_para_fala(AVISO_FALADO, max_frases=20))
    return _audio_aviso


def nova_memoria():
    return Memoria(CFG.memoria_turnos)


def aceitar():
    # O consentimento é guardado no servidor (gr.State): sem ele, nenhuma função processa voz.
    return gr.update(visible=False), gr.update(visible=True), True


def _formatar_fontes(fontes):
    if not fontes:
        return "_Sem fonte da base para esta resposta._"
    return "**Fontes:**\n" + "\n".join(f"- [{f['titulo']}]({f['url']})" for f in fontes)


def _turno(resultado, historico):
    historico = historico + [
        {"role": "user", "content": resultado.transcricao or "(não entendi o áudio)"},
        {"role": "assistant", "content": resultado.resposta_texto},
    ]
    lat = {k: f"{v:.2f} s" for k, v in resultado.latencias.items()}
    g = resultado.guardrail
    if g.get("nivel"):
        lat["guardrail_nivel"] = g["nivel"]
        canal = g.get("canal_principal") or {}
        gr.Warning(f"Atenção: {canal.get('nome', '')} {canal.get('numero') or ''}".strip())
    return historico, resultado.audio_resposta, _formatar_fontes(resultado.fontes), lat


def _sem_consentimento(caminho=None):
    if caminho:  # áudio que chegou sem consentimento é apagado sem ser processado
        try:
            os.remove(caminho)
        except OSError:
            pass
    raise gr.Error("Para usar o assistente, primeiro aceite o aviso de privacidade.")


def nivel_audio(caminho) -> dict | None:
    """Mede só números do sinal (duração, volume, % de silêncio), sem guardar voz nem texto.

    Serve para avisar quando o microfone escolhido não está captando nada.
    """
    try:
        import av
        import numpy as np

        partes, taxa = [], 16000
        with av.open(caminho) as c:
            reamostrar = av.AudioResampler(format="flt", layout="mono", rate=taxa)
            for quadro in c.decode(audio=0):
                for q in reamostrar.resample(quadro):
                    partes.append(q.to_ndarray().ravel())
        x = np.concatenate(partes) if partes else np.zeros(1, dtype=np.float32)
        rms = float(np.sqrt(np.mean(x ** 2)))
        return {"duracao_s": round(len(x) / taxa, 2),
                "volume_dbfs": round(float(20 * np.log10(rms)) if rms > 0 else -120.0, 1),
                "silencio_%": round(100 * float(np.mean(np.abs(x) < 1e-4)), 1)}
    except Exception:  # noqa: BLE001 - a medição nunca pode impedir a resposta
        return None


AVISO_MIC_MUDO = ("A gravação chegou sem som. Confira o microfone escolhido no botão ao lado de "
                  "\"Gravar\" e se ele não está mudo no Windows.")


def responder_audio(caminho, historico, memoria, consentiu):
    if not consentiu:
        _sem_consentimento(caminho)
    if not caminho or not os.path.exists(caminho):  # nada gravado, ou áudio já processado e apagado
        return gr.update(), historico, gr.update(), gr.update(), gr.update(), memoria
    memoria = memoria or nova_memoria()
    nivel = nivel_audio(caminho)
    print(f"[áudio recebido] {nivel}", flush=True)  # só números, sem voz e sem texto
    if nivel and (nivel["volume_dbfs"] < -50 or nivel["silencio_%"] > 85):
        gr.Warning(AVISO_MIC_MUDO)
    r = ASSISTENTE.processar_audio(caminho, memoria, apagar_audio=True)
    h, audio, fontes, lat = _turno(r, historico)
    return None, h, audio, fontes, lat, memoria


def responder_texto(texto, historico, memoria, consentiu):
    if not consentiu:
        _sem_consentimento()
    if not texto or not texto.strip():
        return "", historico, None, gr.update(), gr.update(), memoria
    memoria = memoria or nova_memoria()
    r = ASSISTENTE.processar_texto(texto, memoria)
    h, audio, fontes, lat = _turno(r, historico)
    return "", h, audio, fontes, lat, memoria


def limpar():
    return [], None, "", {}, nova_memoria()


CSS = ".gradio-container {font-size: 18px} button {min-height: 52px}"
SEM_API = dict(api_name=False, show_api=False)  # nada fica exposto como API no link público

with gr.Blocks(title="Quem Resolve? Assistente de voz", css=CSS, delete_cache=(300, 600)) as demo:
    gr.Markdown("# Quem Resolve? 🔊\nFale qual problema você viu na rua e eu digo quem resolve e como pedir ajuda.")
    consentiu = gr.State(False)

    with gr.Column(visible=True) as tela_consentimento:
        gr.Markdown(TEXTO_CONSENTIMENTO)
        btn_ouvir = gr.Button("🔊 Ouvir o aviso")
        audio_aviso = gr.Audio(label="Aviso em áudio", autoplay=True, type="filepath", interactive=False)
        btn_aceitar = gr.Button("Concordo e começar", variant="primary")

    with gr.Column(visible=False) as tela_principal:
        memoria = gr.State(None)
        with gr.Row():
            with gr.Column(scale=1):
                # Sem a onda animada durante a gravação: em alguns navegadores/placas de vídeo
                # ela congela a página e a captura do microfone para (gravação sai em silêncio).
                entrada = gr.Audio(sources=["microphone", "upload"], type="filepath",
                                   waveform_options=gr.WaveformOptions(show_recording_waveform=False),
                                   label="1) Escolha o microfone no botão à direita · 2) Aperte Gravar, fale e pare · ou envie um arquivo de áudio")
                status = gr.Markdown("Ao parar a gravação (ou enviar um arquivo), a resposta chega sozinha. Não precisa apertar mais nada.")
                texto = gr.Textbox(label="Ou escreva aqui (opcional)", placeholder="Ex.: tem um buraco na minha rua")
                saida_audio = gr.Audio(label="Resposta falada", autoplay=True, type="filepath", interactive=False)
                btn_limpar = gr.Button("Nova conversa (apaga o histórico)")
            with gr.Column(scale=1):
                chat = gr.Chatbot(type="messages", label="Conversa em texto", height=420)
                fontes = gr.Markdown()
                latencia = gr.JSON(label="Latência deste turno (segundos)")

    btn_ouvir.click(ouvir_aviso, None, audio_aviso, **SEM_API)
    btn_aceitar.click(aceitar, None, [tela_consentimento, tela_principal, consentiu], **SEM_API)
    saidas = [entrada, chat, saida_audio, fontes, latencia, memoria]
    entradas_audio = [entrada, chat, memoria, consentiu]
    # Gravação pelo microfone dispara stop_recording; arquivo enviado dispara upload. Cada caminho processa uma vez.
    for evento in (entrada.stop_recording, entrada.upload):
        evento(lambda: "⏳ **Processando seu áudio…** a resposta aparece ao lado em alguns segundos.",
               None, status, queue=False, **SEM_API
               ).then(responder_audio, entradas_audio, saidas, **SEM_API
               ).then(lambda: "✅ Pronto. Para falar de novo, aperte **Gravar**.", None, status, **SEM_API)
    texto.submit(responder_texto, [texto, chat, memoria, consentiu],
                 [texto, chat, saida_audio, fontes, latencia, memoria], **SEM_API)
    btn_limpar.click(limpar, None, [chat, saida_audio, fontes, latencia, memoria], **SEM_API)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--share", action="store_true", help="gera link público (Colab)")
    args = ap.parse_args()
    print("Carregando e aquecendo os modelos...")
    ASSISTENTE.aquecer()
    usuario, senha = os.getenv("APP_USUARIO"), os.getenv("APP_SENHA")
    demo.queue().launch(share=args.share, show_api=False,
                        auth=(usuario, senha) if usuario and senha else None,
                        auth_message="Quem Resolve? Digite o usuário e a senha do grupo.")
