"""Cliente de LLM sem chamar a API de verdade."""
from types import SimpleNamespace

import pytest

from pipelines.voz.llm import ClienteLLM, ModeloIndisponivel


def _cliente(modelo, resposta="ok", erro=None):
    c = ClienteLLM("https://exemplo/v1", "chave", modelo)
    chamadas = []

    def create(**kw):
        chamadas.append(kw)
        if erro:
            raise erro
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=resposta))])

    c.cliente = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return c, chamadas


def test_gpt_oss_usa_pouco_raciocinio_e_folga_de_tokens():
    c, chamadas = _cliente("openai/gpt-oss-120b")
    c.responder([{"role": "user", "content": "oi"}])
    assert chamadas[0]["extra_body"] == {"reasoning_effort": "low"} and chamadas[0]["max_tokens"] >= 1024


def test_modelo_comum_sem_parametros_extras():
    c, chamadas = _cliente("qwen2.5:7b")
    c.responder([{"role": "user", "content": "oi"}])
    assert chamadas[0]["extra_body"] is None and chamadas[0]["max_tokens"] == 300


def test_remove_bloco_de_raciocinio():
    c, _ = _cliente("qwen3", "<think>pensando</think> Quem resolve é a Sabesp.")
    assert c.responder([]) == "Quem resolve é a Sabesp."


def test_modelo_descontinuado_vira_erro_claro():
    c, _ = _cliente("llama-3.3-70b-versatile", erro=RuntimeError("model_decommissioned: has been decommissioned"))
    with pytest.raises(ModeloIndisponivel, match="console.groq.com"):
        c.responder([])
