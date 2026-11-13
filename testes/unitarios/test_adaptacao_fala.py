"""Casos fixos da adaptação para fala. Rode com: pytest testes/unitarios -q"""
import pytest

from pipelines.voz.adaptacao_fala import adaptar_para_fala

CASOS = [
    ("**Quem resolve:** a Enel 😊", "Quem resolve: a Enel."),
    ("Ligue 0800 72 72 196", "Ligue zero oitocentos, sete dois, sete dois, um nove meia."),
    ("Em perigo, ligue 190 ou 193.", "Em perigo, ligue um nove zero ou um nove três."),
    ("Registre no SP156 pelo 156.", "Registre no ésse pê cento e cinquenta e seis pelo um cinco meia."),
    ("A SP Regula fiscaliza a coleta.", "A ésse pê Regula fiscaliza a coleta."),
    ("Moro em SP.", "Moro em São Paulo."),
    ("A CET cuida do semáforo.", "A cê é tê cuida do semáforo."),
    ("Em 19/11/2026.", "Em dezenove de novembro de dois mil e vinte e seis."),
    ("Lei 13.709/2018.", "Lei treze mil, setecentos e nove, de dois mil e dezoito."),
    ("Custa R$ 50,00, 30% a mais.", "Custa cinquenta reais, trinta por cento a mais."),
    ("Atende 24 horas.", "Atende vinte e quatro horas."),
    ("Veja no site https://sp156.prefeitura.sp.gov.br.", "Veja no site oficial."),
    ("- Primeiro item\n- Segundo item", "Primeiro item. Segundo item."),
]


@pytest.mark.parametrize("entrada,esperado", CASOS)
def test_adaptacao(entrada, esperado):
    assert adaptar_para_fala(entrada) == esperado


def test_sem_markdown_nem_emoji():
    saida = adaptar_para_fala("## Título\n**negrito** e `código` 🚨✅")
    assert not any(c in saida for c in "#*`") and "🚨" not in saida


def test_limita_numero_de_frases():
    texto = " ".join(f"Frase {i}." for i in range(1, 10))
    assert adaptar_para_fala(texto, max_frases=3).count(".") == 3


# ---- Casos da 2ª revisão: frases longas reais da base de conhecimento ----
import json
import re
from pathlib import Path

BASE = json.loads((Path(__file__).resolve().parents[2] / "base_conhecimento" / "quem_resolve.json").read_text(encoding="utf-8"))
TELEFONE = re.compile(r"0800(?:[\s.-]*\d{2,4}){2,3}|\(?\d{2}\)?\s\d{4,5}[\s-]\d{4}")


@pytest.mark.parametrize("item", BASE, ids=[i["id"] for i in BASE])
def test_telefones_da_base_nunca_quebram(item):
    """Cada telefone falado tem que aparecer inteiro, sem ponto no meio, na resposta adaptada."""
    texto = item["como_acionar"] + " " + item["seguranca"]
    saida = adaptar_para_fala(texto, max_frases=20)
    for tel in TELEFONE.findall(texto):
        assert adaptar_para_fala(tel).rstrip(".") in saida, f"telefone {tel!r} quebrado em: {saida}"


@pytest.mark.parametrize("item", BASE, ids=[i["id"] for i in BASE])
def test_textos_da_base_sem_lixo(item):
    saida = adaptar_para_fala(item["como_acionar"], max_frases=20)
    assert "site o site" not in saida and "\x01" not in saida and "\x02" not in saida and "\x03" not in saida
    for nome in ("Sabesp", "Enel", "Comgás", "Prefeitura", "WhatsApp"):
        if nome in item["como_acionar"]:
            assert nome in saida, f"{nome} perdeu a maiúscula: {saida}"


def test_ou_site():
    assert adaptar_para_fala("Use o app ou site sp156.prefeitura.sp.gov.br.") == "Use o app ou site oficial."
