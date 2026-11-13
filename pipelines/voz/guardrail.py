"""Guardrail de segurança por regras (camada 1 do PRD, seção 4.2).

Roda ANTES do LLM e funciona sem internet. A saída segue o GuardrailResultado
de CONTRATOS.md (seção B). Se o Ian já tiver o módulo oficial de regras, basta
trocar a função `avaliar` por ele.

Níveis: 0 sem risco · 1 risco imediato · 2 violência sem risco imediato · 3 zeladoria com risco
"""
import re
import unicodedata
from dataclasses import dataclass, field, asdict

CANAIS = {
    "policia": {"nome": "Polícia Militar", "numero": "190", "quando": "Crime acontecendo, pessoa em perigo"},
    "samu": {"nome": "SAMU", "numero": "192", "quando": "Pessoa ferida ou passando mal"},
    "bombeiros": {"nome": "Bombeiros", "numero": "193", "quando": "Fogo, resgate"},
    "defesa_civil": {"nome": "Defesa Civil", "numero": "199", "quando": "Desabamento, alagamento, risco estrutural"},
    "mulher": {"nome": "Central de Atendimento à Mulher", "numero": "180", "quando": "Violência contra a mulher"},
    "direitos_humanos": {"nome": "Disque Direitos Humanos", "numero": "100",
                         "quando": "Violência contra crianças, idosos, pessoas com deficiência e outras violações"},
    "enel": {"nome": "Emergência Enel", "numero": "0800 72 72 196", "quando": "Fio caído ou faiscando, poste com risco"},
    "comgas": {"nome": "Emergência Comgás", "numero": "0800 011 0197", "quando": "Cheiro ou vazamento de gás"},
    "delegacia": {"nome": "Delegacia Eletrônica", "numero": None, "quando": "Boletim de ocorrência de crime que já aconteceu"},
}


@dataclass
class ResultadoGuardrail:
    nivel: int
    tipo: str | None = None
    camada: str | None = None
    justificativa: str | None = None
    canal_principal: dict | None = None
    outros_canais: list[dict] = field(default_factory=list)
    pode_continuar: bool = True
    saida_rapida: bool = False
    mensagem: str = ""  # uso interno da voz (o que é falado); não faz parte do contrato

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("mensagem")
        return d


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


# (padrão sem acento, tipo, canal principal, outros canais, mensagem falada[, discreto])
NIVEL_1 = [
    (r"cheiro (forte )?de gas|vazamento de gas|vazando gas", "gas", "comgas", ["bombeiros"],
     "Isso pode ser perigoso. Afaste-se do local, não acenda fogo e não mexa em interruptores. "
     "Ligue agora para a emergência da Comgás no 0800 011 0197. Se tiver fogo, ligue 193 para os Bombeiros."),
    (r"pegando fogo|incendio|\bfogo\b|explos|fumaca preta", "fogo", "bombeiros", ["samu"],
     "Afaste-se do local e ligue agora para os Bombeiros no 193."),
    (r"levou (um )?choque|tomou (um )?choque|eletrocut|sangrando|desmaiou|desmaiad|inconsciente|"
     r"nao (esta )?respira|atropel|passando mal|\bferidos?\b|(ficou|saiu|foi|esta|estao) ferid|"
     r"(alguem|pessoa|crianca|vizinh[oa]|gente|idos[oa]|moc[oa]|senhor[a]?) (\w+ ){0,3}ferid",
     "pessoa_ferida", "samu", ["bombeiros"],
     "Se alguém está ferido ou passando mal, ligue agora para o SAMU no 192. Não toque na pessoa se ela ainda estiver encostada em um fio."),
    (r"\bdesab(ou|ando|amento|ar|aram|aria)\b|soterr|arrastad[oa] pela (agua|enxurrada)|casa (esta )?caindo|morro (esta )?deslizando|deslizamento",
     "risco_estrutural", "bombeiros", ["defesa_civil"],
     "Saia do local se puder e ligue agora para os Bombeiros no 193 ou para a Defesa Civil no 199."),
    (r"(roubando|furtando|cortando|levando) (os |o )?(fio|cabo)s?|assalto (acontecendo|agora)|"
     r"tiroteio|com uma arma|\barmad[oa]s?\b|me ameacando|(?<!pronto-)(?<!pronto )\bsocorro\b",
     "crime_em_andamento", "policia", [],
     "Fique em um lugar seguro e ligue agora para a Polícia Militar no 190."),
]

NIVEL_2 = [
    (r"violencia domestica|(meu|minha) (marido|esposa|mulher|companheir[oa]|namorad[oa]|ex|pai|mae|padrasto|madrasta) "
     r"(\w+ )?(me )?(bate|bateu|agride|agrediu|espanca|ameaca)|(ele|ela) me (bate|bateu|agride|espanca)|"
     r"me espanca|apanho (do|da|em casa)", "violencia_domestica", "policia", ["mulher", "direitos_humanos"],
     "Sinto muito que você esteja passando por isso. Você não precisa enfrentar isso sem ajuda. "
     "Se estiver em perigo agora, ligue 190. Mulheres também podem ligar para o 180, de graça e em sigilo.", True),
    (r"fui assaltad|me assaltaram|me roubaram|roubaram (meu|minha)|fui agredid", "violencia_ocorrida", "delegacia", ["policia"],
     "Sinto muito pelo que aconteceu. Você pode registrar o boletim de ocorrência pela Delegacia Eletrônica da Polícia Civil, pela internet. "
     "Se ainda estiver em perigo, ligue 190.", False),
    (r"maus.tratos|abuso (contra|de) (crianca|idos)|abusando d", "violacao_direitos", "direitos_humanos", ["policia"],
     "Isso é muito sério. Você pode denunciar de graça e sem se identificar pelo Disque 100. Se houver perigo agora, ligue 190.", True),
]

NIVEL_3 = [
    # D24: fio faiscando -> Enel como canal principal, Bombeiros em outros_canais. Se houver fogo ou
    # pessoa ferida, as regras do nível 1 (verificadas antes) disparam primeiro e mandam para 193/192.
    (r"faisc|fios? (de (luz|energia|alta tensao) |do poste )?(caido|caidos|caiu|cairam|no chao|solto|partido|"
     r"arrebent|rompid)|(caiu|cairam|arrebentou) (um |o |os )?fio", "fio_faiscando", "enel", ["bombeiros"],
     "Primeiro, não chegue perto do fio. A emergência da Enel é 0800 72 72 196."),
    (r"(arvore|galho)\s(\w+\s){0,3}(caindo|cair|tombando|despencando)", "arvore_risco", "defesa_civil", ["bombeiros"],
     "Se a árvore estiver prestes a cair, afaste as pessoas e ligue para a Defesa Civil no 199."),
    (r"\balag(a|am|ar|ou|aram|ando|ado|ada|ados|adas)\b|enchente|agua entrando", "alagamento", "defesa_civil", ["bombeiros"],
     "Se houver risco para pessoas ou casas, ligue para a Defesa Civil no 199."),
]


def _resultado(nivel, m, tipo, principal, outros, msg, discreto=False):
    return ResultadoGuardrail(
        nivel=nivel, tipo=tipo, camada="regras",
        justificativa=f"Termo de risco encontrado: '{m.group(0)}'",
        canal_principal=CANAIS[principal], outros_canais=[CANAIS[c] for c in outros],
        pode_continuar=nivel == 3, saida_rapida=discreto, mensagem=msg)


def avaliar(texto: str) -> ResultadoGuardrail:
    t = normalizar(texto)
    for nivel, regras in ((1, NIVEL_1), (2, NIVEL_2), (3, NIVEL_3)):
        for regra in regras:
            m = re.search(regra[0], t)
            if m:
                return _resultado(nivel, m, *regra[1:])
    return ResultadoGuardrail(0)
