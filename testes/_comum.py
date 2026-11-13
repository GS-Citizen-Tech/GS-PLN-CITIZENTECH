"""Funções compartilhadas pelos scripts de avaliação."""
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RESULTADOS = RAIZ / "testes" / "resultados"
RESULTADOS.mkdir(parents=True, exist_ok=True)

try:
    from num2words import num2words
except ImportError:
    num2words = None


def normalizar_wer(texto: str) -> str:
    """Normalização para o WER: minúsculas, números por extenso, sem pontuação.

    Mantém acentos (está x esta é erro real). Separa letras de números
    ("SP156" -> "sp 156") e escreve números por extenso, para não punir o
    Whisper por escrever "156" quando a referência diz "cento e cinquenta e seis".
    """
    t = texto.lower()
    t = re.sub(r"(?<=[a-zà-ú])(?=\d)|(?<=\d)(?=[a-zà-ú])", " ", t)
    if num2words:
        t = re.sub(r"\d+", lambda m: num2words(int(m.group()), lang="pt_BR"), t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tabela_md(df) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".3f")
    except ImportError:
        return df.to_string(index=False)


EXTENSOES_AUDIO = (".wav", ".m4a", ".mp3", ".ogg", ".opus", ".webm", ".aac", ".flac", ".3gp")


def localizar_audio(pasta: Path, nome: str) -> Path | None:
    """Acha o áudio pelo nome, aceitando qualquer extensão comum de celular.

    Ex.: o manifesto diz stt_01.wav, mas o grupo gravou stt_01.m4a -> encontra.
    """
    exato = pasta / nome
    if exato.exists():
        return exato
    base = Path(nome).stem
    for ext in EXTENSOES_AUDIO:
        for candidato in (pasta / f"{base}{ext}", pasta / f"{base}{ext.upper()}"):
            if candidato.exists():
                return candidato
    return None
