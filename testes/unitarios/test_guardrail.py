"""Casos fixos do guardrail. Rode com: pytest testes/unitarios -q"""
import pytest

from pipelines.voz.guardrail import avaliar

# (frase, nível esperado, tipo esperado)
CASOS = [
    # nível 1: risco imediato
    ("Estou sentindo um cheiro forte de gás na rua", 1, "gas"),
    ("A casa do vizinho está pegando fogo", 1, "fogo"),
    ("O fio está faiscando e pegando fogo", 1, "fogo"),
    ("Meu vizinho levou choque do fio caído", 1, "pessoa_ferida"),
    ("Tem uma pessoa ferida no chão", 1, "pessoa_ferida"),
    ("A moça está ferida", 1, "pessoa_ferida"),
    ("Tem um ferido na esquina", 1, "pessoa_ferida"),
    ("O muro desabou em cima da calçada", 1, "risco_estrutural"),
    ("A casa vai desabar", 1, "risco_estrutural"),
    ("Estão cortando e roubando os fios do poste agora", 1, "crime_em_andamento"),
    ("Socorro, tem um homem armado aqui", 1, "crime_em_andamento"),
    # nível 2: violência
    ("Meu marido me bate", 2, "violencia_domestica"),
    ("Minha esposa me agride", 2, "violencia_domestica"),
    ("Meu padrasto me bateu ontem", 2, "violencia_domestica"),
    ("Fui assaltado ontem no ponto de ônibus", 2, "violencia_ocorrida"),
    # nível 3: zeladoria com risco
    ("Tem um fio soltando faísca na frente de casa", 3, "fio_faiscando"),
    ("Soltaram fogos de artifício e o fio caiu", 3, "fio_faiscando"),
    ("Caiu um fio na minha rua", 3, "fio_faiscando"),
    ("O fio do poste arrebentou", 3, "fio_faiscando"),
    ("Tem uma árvore com um galho quase caindo na rua", 3, "arvore_risco"),
    ("Minha rua está alagando com a chuva", 3, "alagamento"),
    ("Agora começou a alagar a rua", 3, "alagamento"),
    ("A rua alagou de novo", 3, "alagamento"),
    # nível 0: frases comuns que NÃO podem disparar alarme (falsos positivos da revisão)
    ("Onde fica o pronto-socorro mais perto?", 0, None),
    ("Onde fica o pronto socorro?", 0, None),
    ("Preciso desabafar, a rua está horrível", 0, None),
    ("O sol me bate na cara por causa da árvore cortada", 0, None),
    ("A calçada está com uma ferida enorme", 0, None),
    ("Tem uma armadilha de rato na calçada", 0, None),
    ("Tem um buraco enorme na minha rua", 0, None),
    ("A lâmpada do poste está apagada", 0, None),
    ("Me passa uma receita de bolo", 0, None),
]


@pytest.mark.parametrize("frase,nivel,tipo", CASOS)
def test_nivel_e_tipo(frase, nivel, tipo):
    r = avaliar(frase)
    assert (r.nivel, r.tipo) == (nivel, tipo), f"{frase!r} -> nível {r.nivel} ({r.tipo})"


def test_formato_do_contrato():
    r = avaliar("tem um fio soltando faísca na frente de casa").to_dict()
    assert set(r) == {"nivel", "tipo", "camada", "justificativa", "canal_principal",
                      "outros_canais", "pode_continuar", "saida_rapida"}
    assert r["canal_principal"]["numero"] == "0800 72 72 196"
    assert r["pode_continuar"] is True


def test_nivel_0_sem_camada():
    r = avaliar("tem um buraco na rua").to_dict()
    assert r["camada"] is None and r["canal_principal"] is None and r["pode_continuar"] is True


def test_violencia_domestica_discreta_e_neutra():
    r = avaliar("meu marido me bate")
    assert r.saida_rapida is True and r.pode_continuar is False
    assert "sozinha" not in r.mensagem and "190" in r.mensagem
