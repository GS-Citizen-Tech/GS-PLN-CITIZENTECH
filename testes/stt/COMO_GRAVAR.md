# Como gravar os 20 áudios do teste de STT

1. Cada linha de `manifesto.csv` é um áudio. Grave a frase da coluna `referencia` exatamente como está escrita, com fala natural.
2. Três vozes diferentes (A, B e C). Para a análise de viés ficar interessante, varie gênero e idade (por exemplo, uma pessoa com 60 anos ou mais). Preencha a coluna `perfil_voz` na primeira linha de cada falante.
3. Áudios 16 a 20 com ruído de fundo real: rua, TV ligada, ventilador, cozinha. Anote o tipo de ruído no relatório.
4. Salve em `testes/stt/audios/` com o nome da coluna `arquivo`. A extensão pode ser a do gravador do celular (`.m4a`, `.mp3`, `.ogg`, `.wav`...): o script acha `stt_01.m4a` mesmo que o manifesto diga `stt_01.wav`.
5. Peça consentimento por escrito de quem gravar (os áudios vão para o repositório). Use o modelo em `relatorio/termo_consentimento_gravacao.md`.

Roteiro pronto para imprimir ou mandar no WhatsApp: `ROTEIRO_POR_PESSOA.md`.

Depois rode: `python testes/avaliar_stt.py --modelos small medium`
