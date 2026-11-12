# Hack_ts---Python
O back-end da aplicação.

## IA generativa (Amazon Bedrock) — opcional

Copie `.env.example` para `.env` e defina `LLM_PROVIDER=bedrock` (padrão `nenhum`). As credenciais vêm do
ambiente ou de `AWS_PROFILE`, nunca do repositório.

- `/api/perguntar`: o modelo redige a resposta só com as seções citadas, na ordem do perfil lida de
  `docs/requisitos/PESQUISA-LEGAL-DESIGN-UX-WRITING.md`. A síntese é descartada (volta a extrativa, com aviso)
  se citar fonte fora das recuperadas, tiver afirmação sem fonte ou número que não esteja nos trechos.
- `/api/relatorio`: seção "Síntese executiva" no topo, cada item com `fonte`; itens não ancorados são descartados.
- `/api/saude`: campo `ia` (`provedor`, `modelo`, `disponivel`).
