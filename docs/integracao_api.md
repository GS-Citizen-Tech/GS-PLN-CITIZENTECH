# Integração com a API (CONTRATOS.md v0.1)

O módulo de voz já devolve o formato da seção **H** (`POST /voz/conversar`), validado com Pydantic em
`pipelines/voz/contrato.py`. O guardrail devolve o `GuardrailResultado` da seção **B**.

## Rota sugerida para o Ian (routers/voz.py)

```python
import shutil, tempfile
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pipelines.voz.contrato import VozConversarSaida, conversar

router = APIRouter()
FORMATOS = {"audio/webm", "audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3"}
LIMITE_BYTES = 5 * 1024 * 1024  # ~1 min de áudio comprimido

@router.post("/voz/conversar", response_model=VozConversarSaida)
async def voz_conversar(audio: UploadFile = File(...), historico: str | None = Form(None)):
    if audio.content_type not in FORMATOS:
        raise HTTPException(415, "Formato de áudio não aceito")
    sufixo = Path(audio.filename or "a.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=sufixo, delete=False) as tmp:
        shutil.copyfileobj(audio.file, tmp)
    if Path(tmp.name).stat().st_size > LIMITE_BYTES:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(413, "Áudio muito longo")
    return conversar(tmp.name, historico)   # o arquivo é apagado logo após a transcrição
```

Para o mock (RNF13), a rota pode devolver um `VozConversarSaida` fixo enquanto `/health` marca `"voz": "mock"`.

## Respostas do parceiro aos pontos em aberto do CONTRATOS.md

1. **RAG (G):** o formato de `fontes` atende. Proposta: incluir o campo opcional `score` (similaridade de 0 a 1), usado
   na avaliação por componente. A voz já envia esse campo.
2. **Voz (H):** manter `audio_base64`. As respostas têm poucas frases, então o áudio é pequeno e o front toca direto,
   sem uma segunda requisição e sem guardar arquivo no servidor (melhor para a LGPD). Limite de 1 minuto está bom.
   Proposta de dois campos extras na saída: `guardrail` (para o front abrir a tela de emergência) e `historico`
   atualizado (o front devolve na próxima chamada, então a API fica sem estado). Em `latencias`, além de
   `stt_ms`, `llm_ms`, `tts_ms` e `total_ate_fala_ms`, vão `guardrail_ms`, `rag_ms` e `adaptacao_ms`.
4. **Guardrail (B):** concordo com os tipos. Lista usada nas regras da voz: `gas`, `fogo`, `pessoa_ferida`,
   `risco_estrutural`, `crime_em_andamento` (nível 1); `violencia_domestica`, `violencia_ocorrida`,
   `violacao_direitos` (nível 2); `fio_faiscando`, `arvore_risco`, `alagamento` (nível 3).
   **Decisão D24 (fio faiscando):** canal principal = emergência da Enel (0800 72 72 196), Bombeiros 193 em
   `outros_canais`. Motivo: a orientação oficial (SP Regula, citada no PRD) manda fio soltando faísca para a Enel, e a
   própria Enel atende fio partido 24 horas. Os Bombeiros entram como principal só quando há fogo, e o SAMU quando há
   alguém ferido: nesses casos o guardrail sobe para o nível 1 (`fogo` ou `pessoa_ferida`), que é verificado antes.
   Sugestão: trocar o exemplo da seção B do CONTRATOS.md para a Enel e subir a versão para 0.2.
   Em `violencia_ocorrida`, o canal principal é a Delegacia Eletrônica, que não tem número (`numero: null`).
5. **Base (A):** os IDs de `base_conhecimento/quem_resolve.json` foram alinhados ao contrato (`buraco`, `fio_telecom`...).
   Esse JSON pode ser a fonte de `GET /categorias`; faltam só `responsavel_id`, `palavras` e `classes_visao`.

Na voz, em violência doméstica (`saida_rapida: true`) o `audio_base64` volta `null` de propósito: a resposta não é falada em voz alta.
