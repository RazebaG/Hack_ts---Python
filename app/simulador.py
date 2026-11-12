"""Serviço do Simulador de Cenários "E se?" (Issue #8, Adendo v0.2).

Implementa os endpoints:
- GET /api/regras: lista regras configuradas para simulação
- POST /api/simular: simula alterações hipotéticas nas regras

Cenários suportados:
1. ferias_antecedencia_dias (P0): Antecedência mínima de férias 45 → 30 (NG_111 §4.5).
   - Linha do tempo calculada para o início de gozo de 05/05/2027 (NG_111 Anexo C / PX_1111-001).
   - Conflito interno com emissão do aviso D-35 (NG_111 §4.5.3).
   - Trechos vigentes que citam 45 dias / D-45 para revisão: NG_111 v3, PX_1111-001, FM_1111-001 v2, TB_1111-001 e FL_1111-001.
2. alcada_gerente_max (P0/P1 aprovado 12/11): Alçada de gerente R$ 18.000 → 20.000 (NT_2026-018 Anexo F).
   - Impacto muda_aprovador no contrato CTR_2026-012 (R$ 18.250 deixa de exigir diretor).

Todas as regras e impactos são determinísticos, sem IA e baseados exclusivamente no acervo.
"""

from datetime import date, timedelta
from typing import List, Optional, Union
from fastapi import HTTPException

from app.models import (
    Fonte,
    RegraSimulacao,
    MarcoLinhaTempo,
    ImpactoSimulacao,
    SimulacaoRequest,
    SimulacaoResponse,
)
from app.acervo import AcervoRepository, get_acervo
from app.taxonomia import derivar_camada


REGRAS_DISPONIVEIS = {"ferias_antecedencia_dias", "alcada_gerente_max"}


class SimuladorService:
    def __init__(self, acervo: Optional[AcervoRepository] = None):
        self.acervo = acervo or get_acervo()

    def listar_regras(self) -> List[RegraSimulacao]:
        """Retorna a lista de regras paramétricas disponíveis para simulação."""
        regra_ferias = RegraSimulacao(
            id="ferias_antecedencia_dias",
            rotulo="Antecedência mínima para pedir férias",
            valor=45,
            unidade="dias",
            fonte=Fonte(
                codigo="NG_111",
                versao="3.0.0",
                secao="4.5.1",
                trecho="Solicitação: até 45 dias antes.",
                camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
            ),
        )

        regra_alcada = RegraSimulacao(
            id="alcada_gerente_max",
            rotulo="Alçada máxima para aprovação de contratação por gerente",
            valor=18000,
            unidade="BRL",
            fonte=Fonte(
                codigo="NT_2026-018",
                versao="1.0.0",
                secao="Anexo F",
                trecho="Até R$ 18.000,00: Gerente",
                camada=derivar_camada("NT_2026-018", tipo_nome="Nota Técnica"),
            ),
        )

        return [regra_ferias, regra_alcada]

    def simular(self, req: SimulacaoRequest) -> SimulacaoResponse:
        """Executa simulação de impacto para a regra informada."""
        if req.regra not in REGRAS_DISPONIVEIS:
            raise HTTPException(
                status_code=404,
                detail=f"Regra '{req.regra}' não encontrada. Regras disponíveis: {sorted(REGRAS_DISPONIVEIS)}",
            )

        if req.regra == "ferias_antecedencia_dias":
            return self._simular_ferias(req)
        elif req.regra == "alcada_gerente_max":
            return self._simular_alcada(req)
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Regra '{req.regra}' não suportada.",
            )

    def _simular_ferias(self, req: SimulacaoRequest) -> SimulacaoResponse:
        """Simula alteração no prazo de antecedência mínima de férias (P0)."""
        if not (1 <= req.novo_valor <= 90):
            raise HTTPException(
                status_code=422,
                detail="Para a regra 'ferias_antecedencia_dias', o novo_valor deve estar entre 1 e 90 dias.",
            )

        novo_dias: Union[int, float] = int(req.novo_valor) if req.novo_valor == int(req.novo_valor) else req.novo_valor
        cenario = req.cenario or "Exemplo NG_111 Anexo C / PX_1111-001: férias a partir de 05/05/2027"

        # Marco base do exemplo de aplicação: início de gozo em 05/05/2027 (quarta-feira)
        data_gozo = date(2027, 5, 5)

        # 1. Marco Solicitação (4.5.1)
        data_antes_solic = data_gozo - timedelta(days=45)
        data_depois_solic = data_gozo - timedelta(days=int(novo_dias))
        muda_solic = (data_antes_solic != data_depois_solic)

        marco_solic = MarcoLinhaTempo(
            marco="Solicitação",
            antes=data_antes_solic.isoformat(),
            depois=data_depois_solic.isoformat(),
            muda=muda_solic,
            fonte=Fonte(
                codigo="NG_111",
                versao="3.0.0",
                secao="4.5.1",
                trecho="Solicitação: até 45 dias antes.",
                camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
            ),
        )

        # 2. Marco Emissão do aviso pela GGC (4.5.3) - fixo em D-35
        data_aviso = data_gozo - timedelta(days=35)
        marco_aviso = MarcoLinhaTempo(
            marco="Aviso da GGC (D-35)",
            antes=data_aviso.isoformat(),
            depois=data_aviso.isoformat(),
            muda=False,
            fonte=Fonte(
                codigo="NG_111",
                versao="3.0.0",
                secao="4.5.3",
                trecho="Emissão do aviso pela GGC: até 35 dias antes.",
                camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
            ),
        )

        # 3. Marco Assinatura do aviso pelo empregado (4.5.4) - nunca depois de D-30
        data_assinatura = data_gozo - timedelta(days=30)
        marco_assinatura = MarcoLinhaTempo(
            marco="Assinatura do aviso",
            antes=data_assinatura.isoformat(),
            depois=data_assinatura.isoformat(),
            muda=False,
            fonte=Fonte(
                codigo="NG_111",
                versao="3.0.0",
                secao="4.5.4",
                trecho="Assinatura do aviso pelo empregado: até 5 dias úteis depois do recebimento e nunca depois de 30 dias antes do início de gozo.",
                camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
            ),
        )

        # 4. Marco Pagamento (4.5.5) - D-3 com antecipação se cair em fim de semana
        # 05/05/2027 - 3 dias = 02/05/2027 (domingo) -> antecipa para 30/04/2027 (sexta-feira)
        marco_pagamento = MarcoLinhaTempo(
            marco="Pagamento",
            antes="2027-04-30",
            depois="2027-04-30",
            muda=False,
            fonte=Fonte(
                codigo="NG_111",
                versao="3.0.0",
                secao="4.5.5",
                trecho="Pagamento: até 3 dias corridos antes; se esse dia for sábado, domingo ou feriado, o pagamento é antecipado para o dia útil anterior.",
                camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
            ),
        )

        linha_do_tempo = [marco_solic, marco_aviso, marco_assinatura, marco_pagamento]

        impactos: List[ImpactoSimulacao] = []
        resumo: List[str] = []

        if novo_dias == 45:
            resumo = ["Nenhuma alteração nos prazos ou documentos vigentes."]
        else:
            depois_fmt = data_depois_solic.strftime("%d/%m/%Y")
            resumo.append(f"A solicitação passa para D-{novo_dias} ({depois_fmt} no exemplo).")

            # Conflito interno: se novo_dias < 35, o aviso D-35 deveria ser emitido antes do término do prazo de solicitação
            if novo_dias < 35:
                impactos.append(
                    ImpactoSimulacao(
                        tipo="conflito_interno",
                        descricao=f"O aviso D-35 ficaria antes do fim do prazo de solicitação (D-{novo_dias}).",
                        fontes=[
                            Fonte(
                                codigo="NG_111",
                                versao="3.0.0",
                                secao="4.5.3",
                                trecho="Emissão do aviso pela GGC: até 35 dias antes.",
                                camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
                            )
                        ],
                    )
                )
                resumo.append("O D-35 do aviso fica incompatível.")

            # Documentos vigentes que citam 45 dias / D-45 e exigiriam revisão
            revisar_docs = [
                ImpactoSimulacao(
                    tipo="revisar_documento",
                    codigo="NG_111",
                    versao="3.0.0",
                    descricao="Estabelece a antecedência de 45 dias para solicitação de férias",
                    fontes=[
                        Fonte(
                            codigo="NG_111",
                            versao="3.0.0",
                            secao="4.5.1",
                            trecho="Solicitação: até 45 dias antes.",
                            camada=derivar_camada("NG_111", tipo_nome="Norma Geral"),
                        )
                    ],
                ),
                ImpactoSimulacao(
                    tipo="revisar_documento",
                    codigo="PX_1111-001",
                    versao="1.0.0",
                    descricao="Cita o marco D-45",
                    fontes=[
                        Fonte(
                            codigo="PX_1111-001",
                            versao="1.0.0",
                            secao="8.2",
                            trecho="Solicitar (marco D-45).",
                            camada=derivar_camada("PX_1111-001", tipo_nome="Procedimento", vinculado_a="NG_111"),
                        )
                    ],
                ),
                ImpactoSimulacao(
                    tipo="revisar_documento",
                    codigo="FM_1111-001",
                    versao="2.0.0",
                    descricao="Exige declaração de ciência de que a solicitação exige 45 dias de antecedência",
                    fontes=[
                        Fonte(
                            codigo="FM_1111-001",
                            versao="2.0.0",
                            secao="Bloco D",
                            trecho="Declaro ter ciência de que a solicitação exige 45 dias de antecedência.",
                            camada=derivar_camada("FM_1111-001", tipo_nome="Formulário", vinculado_a="NG_111"),
                        )
                    ],
                ),
                ImpactoSimulacao(
                    tipo="revisar_documento",
                    codigo="TB_1111-001",
                    versao="1.0.0",
                    descricao="Quadro de prazos estipula solicitação até D-45",
                    fontes=[
                        Fonte(
                            codigo="TB_1111-001",
                            versao="1.0.0",
                            secao="Tabela 2",
                            trecho="Solicitação | Empregado | até D-45 | NG_111 4.5.1",
                            camada=derivar_camada("TB_1111-001", tipo_nome="Tabela", vinculado_a="NG_111"),
                        )
                    ],
                ),
                ImpactoSimulacao(
                    tipo="revisar_documento",
                    codigo="FL_1111-001",
                    versao="1.0.0",
                    descricao="Fluxograma estipula solicitação no Portal Raiz até D-45",
                    fontes=[
                        Fonte(
                            codigo="FL_1111-001",
                            versao="1.0.0",
                            secao="1",
                            trecho="C --> D[Empregado solicita no Portal Raiz - até D-45]",
                            camada=derivar_camada("FL_1111-001", tipo_nome="Fluxograma", vinculado_a="PX_1111-001"),
                        )
                    ],
                ),
            ]
            impactos.extend(revisar_docs)
            resumo.append("Documentos vigentes que citam 45 dias exigiriam revisão.")

        return SimulacaoResponse(
            regra="ferias_antecedencia_dias",
            valor_atual=45,
            novo_valor=novo_dias,
            unidade="dias",
            cenario=cenario,
            linha_do_tempo=linha_do_tempo,
            impactos=impactos,
            resumo=resumo,
            aviso="Simulação hipotética: não altera os documentos.",
        )

    def _simular_alcada(self, req: SimulacaoRequest) -> SimulacaoResponse:
        """Simula alteração no limite de alçada do gerente (R$ 18.000 → 20.000)."""
        novo_valor: Union[int, float] = int(req.novo_valor) if req.novo_valor == int(req.novo_valor) else req.novo_valor
        cenario = req.cenario or "Contratação direta de coworking CTR_2026-012 (R$ 18.250,00)"

        impactos: List[ImpactoSimulacao] = []
        resumo: List[str] = []

        if novo_valor == 18000:
            resumo = ["Nenhuma alteração na alçada ou nos aprovadores do acervo."]
        else:
            # O contrato de coworking CTR_2026-012 tem valor global de R$ 18.250,00
            if novo_valor >= 18250:
                impactos.append(
                    ImpactoSimulacao(
                        tipo="muda_aprovador",
                        codigo="CTR_2026-012",
                        versao="1.0.0",
                        descricao="O contrato CTR_2026-012 (R$ 18.250,00) passa a ficar dentro da alçada do gerente e deixa de exigir aprovação do diretor (DIRAF).",
                        antes="Diretor (DIRAF)",
                        depois="Gerente",
                        fontes=[
                            Fonte(
                                codigo="NT_2026-018",
                                versao="1.0.0",
                                secao="10",
                                trecho="O valor global de R$ 18.250,00 supera a alçada de gerente (R$ 18.000,00) e fica na alçada de diretor (até R$ 120.000,00), conforme a NG_012; por isso a DIRAF aprova.",
                                camada=derivar_camada("NT_2026-018", tipo_nome="Nota Técnica"),
                            ),
                            Fonte(
                                codigo="CTR_2026-012",
                                versao="1.0.0",
                                secao="Cláusula Sétima",
                                trecho="O aluguel mensal é de R$ 3.650,00, perfazendo o valor global de R$ 18.250,00 para os 5 meses de vigência.",
                                camada=derivar_camada("CTR_2026-012", tipo_nome="Contrato"),
                            ),
                        ],
                    )
                )
                resumo.append("O contrato CTR_2026-012 (R$ 18.250,00) passa a ficar dentro da nova alçada do gerente.")
                resumo.append("A contratação deixa de exigir aprovação do diretor da DIRAF.")
            else:
                resumo.append("O contrato CTR_2026-012 (R$ 18.250,00) continua superando o limite do gerente e ainda exige diretor.")

        return SimulacaoResponse(
            regra="alcada_gerente_max",
            valor_atual=18000,
            novo_valor=novo_valor,
            unidade="BRL",
            cenario=cenario,
            linha_do_tempo=[],
            impactos=impactos,
            resumo=resumo,
            aviso="Simulação hipotética: não altera os documentos.",
        )
