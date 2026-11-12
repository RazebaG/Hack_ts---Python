# PRD — Assistente do Arquivo Central de Normas (ACME, dados sintéticos)

> **Hipótese de trabalho (reversível):** o material do desafio é um acervo sintético de normas da ACME (catálogo + 14 documentos de Férias, Inovação/Ideias em Campo e Locação de coworking). Construímos um assistente que responde dúvidas sobre essas normas **com citação**, usando a **versão vigente**, e que diz claramente quando algo **não consta nas fontes**. O Lead confirma ou ajusta o recorte com o enunciado oficial.

## Usuário e dor
Empregado, gestor, GGC/GFI/GCO precisam de respostas rápidas e confiáveis sobre prazos, alçadas, valores e passos. Hoje precisam ler NG + PX + TB + FM e ainda separar versão vigente de substituída.

## Cena da demo (60 s)
1. Pergunta: "Até quando preciso pedir férias que começam em 05/05/2027?" → resposta "21/03/2027 (D-45)" citando **PX_1111-001 v1.0.0, Anexo D**.
2. Pergunta sobre regra que mudou entre versões → resposta usa **NG_111 v3.0.0** e avisa que a v2.0.0 foi substituída.
3. Pergunta fora das fontes ("Uma mesma pessoa pode elaborar, revisar e aprovar?") → "Não consta nas fontes", sem inventar.
4. Decodificar `PX_1130-001` → tipo, norma vinculada (NG_1130), série, vigência.

## Requisitos P0
- Ingestão do acervo em `data/acervo/` → documentos estruturados (código, título, tipo, versão, fase, vigência/aprovação, vinculado_a/referência, elaborado/aprovado por, seções).
- Busca com citação (documento, versão, seção, trecho), preferindo **Vigente**; versões substituídas só com aviso.
- Abstenção: sem evidência suficiente → `consta=false`.
- Frontend: tela de pergunta com citações clicáveis, catálogo e leitor de documento, decodificador de código.
- Avaliação automática com perguntas das seções "Perguntas frequentes" do acervo (meta: ≥ 80% corretas com citação certa; 100% das perguntas "não consta" abstidas).

## P1 / P2
- P1: resposta por perfil (empregado/gestor/GGC), jornadas de referência, calculadora de marcos D-n.
- P2: LLM para redação da resposta (opcional por variável de ambiente; sem chave → resposta extrativa).

## Fora do escopo
Dados reais, autenticação, deploy pago.
