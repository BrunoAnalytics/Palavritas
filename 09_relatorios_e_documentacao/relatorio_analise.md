# Relatório de Análise — Case Palavritas (the news)

**Destinatário:** Head de Produto & Growth  
**Autor:** Analista de Dados Produto & Growth  
**Data:** 25 de Junho de 2026  
**Objetivo:** Compreender os fatores que determinam o engajamento e o retorno dos usuários no jogo Palavritas e propor ações práticas baseadas em dados para alavancar a retenção.

---

## Executivo Summary (Resumo para Decisão)
Nossa análise identificou que a retenção de longo prazo (D30) do Palavritas é fortemente impulsionada pela **criação de um hábito diário atrelado à leitura matinal da newsletter**. 
- Jogar no período da **manhã (06h - 11h)** eleva a retenção D30 de **29,35% para 37,58%** (+8,23 pp).
- Abrir a newsletter no mesmo dia antes de jogar eleva a retenção D30 para **37,83%** (um ganho de +7,29 pp).
- Palavras desafiadoras (taxa de vitória < 50%) não frustram os usuários. Pelo contrário: elas **aumentam a taxa de retorno no dia seguinte de 21,92% para 23,04%** (validação estatística confirmada).

A estratégia de growth deve focar em **antecipar e canalizar o acesso matinal do leitor** através de incentivos da newsletter e do controle dinâmico da dificuldade do jogo.

---

## Entrega 1 — Limpeza e Diagnóstico de Dados

Ao analisar o dataset original obtido diretamente do Google Sheets, identificamos algumas imperfeições que precisaram ser corrigidas antes do início das análises para evitar viés:

1. **Sessões Duplicadas (`session_id`):** 
   - *Problema:* A tabela `palavritas_sessions` continha **1.198 IDs de sessão duplicados**.
   - *Decisão:* Ordenamos as sessões duplicadas pelo número de tentativas de forma decrescente para capturar o estado final do jogo e mantivemos apenas a primeira ocorrência (`drop_duplicates` por `session_id`). Isso reduziu o tamanho das sessões de 41.157 para **39.959 linhas únicas**.
2. **Inconsistências em Dispositivos (`device`):** 
   - *Problema:* O campo continha variações de casing para os mesmos sistemas (`ios`, `iOS`, `IOS`, `android`, `Android`, `ANDROID`).
   - *Decisão:* Padronizamos todos os registros estritamente para `iOS` e `Android`.
3. **Erros de Codificação de Texto (Encoding):**
   - *Problema:* Visualização inicial exibia termos corrompidos nas colunas de cidade, setor e porte de empresa (ex: `Braslia`, `So Paulo`, `finanas`, `educao`, `mdia`).
   - *Decisão:* Analisamos os bytes originais e verificamos que o Pandas importou os caracteres Unicode corretos (como `í` e `ã`), tratando-se apenas de uma incompatibilidade de codificação na tela do terminal. Nenhuma string precisou ser alterada, preservando a integridade do dado.
4. **Respostas da Pesquisa de Usuário (`user_profile`):**
   - *Problema:* O campo `orders_food_delivery` continha valores de texto variados como `'True', 'False', 'sim', 'nõo'`. 
   - *Decisão:* Mapeamos todos os valores equivalentes para Booleanos puros (`True` / `False`).
   - *Problema:* Apenas 800 usuários responderam a pesquisa, mas existem 1.200 usuários na tabela de sessões.
   - *Decisão:* Para preservar a integridade referencial no banco de dados sem perder dados de sessões, a dimensão de usuários (`dim_users`) foi construída contendo os 1.200 IDs de usuários das sessões, deixando os campos de perfil como `NULL` para os 400 usuários não respondentes.
5. **Erros nas Regras do Jogo (`attempts`):**
   - *Problema:* Identificamos sessões com números de tentativas inválidos (como `7` e `8` tentativas, ou derrotas registradas com `0` tentativas). Como representavam uma parcela irrisória dos dados, foram mantidos para não enviesar outras variáveis, mas sinalizamos a necessidade de auditoria no log do app.

---

## Entrega 2 — Análise e Correlações

Rodamos consultas SQL em nosso Data Warehouse para cruzar os drivers de engajamento com as variáveis de retorno (`played_next_day`) e retenção (`active_d30`). Seguem os principais achados estruturados por hipóteses:

### 1. Relação com a Newsletter (Abertura e Assinatura)
* **Comportamento D30:** Usuários que **abrem a newsletter antes de jogar** possuem uma retenção de longo prazo muito maior.
  - Não abriu a newsletter antes: **30,54%** de retenção D30.
  - Abriu a newsletter antes: **37,83%** de retenção D30 (**Aumento absoluto de +7,29 pp**).
* **Assinatura:** Assinantes ativos do *the news* também possuem maior engajamento geral no dia a dia (+1,76 pp no retorno no dia seguinte).

### 2. Horário do Jogo (Hábito Matinal vs. Acesso Avulso)
* **Comportamento D30:** O horário do jogo é a variável comportamental mais decisiva de todas.
  - Jogou à **Tarde (12h - 17h)** ou **Noite (18h - 23h)**: Retenção D30 média de **29,4%**.
  - Jogou de **Manhã (06h - 11h)**: Retenção D30 média de **37,58%** (**Aumento absoluto de +8,23 pp**).
* *Raciocínio:* Usuários matinais usam o Palavritas como parte do seu ritual diário de leitura de notícias logo no início do dia. Esse hábito ancorado à rotina matinal é muito mais duradouro e resistente ao churn do que sessões avulsas jogadas à tarde ou à noite.

### 3. Dificuldade da Palavra (O Efeito Desafio)
Analisamos o impacto de palavras difíceis (ex: *CIÚME*, *HERÓI*, com taxa de vitória de ~45% e média de ~4.2 tentativas) contra palavras fáceis (ex: *CORVO*, *GENRO*, com taxa de vitória de ~66% e média de ~3.3 tentativas):
* **Comportamento D1 (Voltar a jogar no dia seguinte):** 
  - Palavras Fáceis (Vitória >= 60%): **21,92%** de retorno no dia seguinte.
  - Palavras Difíceis (Vitória < 50%): **23,04%** de retorno no dia seguinte (**Aumento absoluto de +1,12 pp**).
* *Raciocínio:* A sensação de desafio (e até mesmo a frustração de perder ou ganhar no limite de tentativas) desperta o efeito psicológico de "quero provar que consigo amanhã". Facilitar o jogo reduz a taxa de retorno no dia seguinte.

### 4. Perfil Sociodemográfico e Hábitos de Delivery
* **Setor de Trabalho:** Os setores com melhor taxa de retorno diário são **Educação (23,60%)** e **Tech (23,28%)**. Setores de **Marketing (21,18%)** e **Direito (20,91%)** retornam menos.
* **Frequência de Food Delivery:** Não observamos correlação direta expressiva (usuários que pedem delivery 0 vezes têm 20,58% de retorno vs 24,01% para quem pede 7 vezes, indicando uma correlação marginal positiva, mas irrelevante para estratégias de produto).
* **Dispositivo:** A diferença entre Android (21,98% retorno) e iOS (22,29% retorno) é estatisticamente nula.

---

## Bônus — Validação de Significância Estatística

Para garantir que nossas conclusões não são frutos do acaso (ruído estatístico), submetemos os principais achados a um teste Z para diferença de proporções amostrais:

1. **Abrir a Newsletter antes de Jogar vs. Retenção D30:**
   - Z-score = **12,32** | p-value = **0,0000** (Praticamente zero).
   - *Conclusão:* Diferença altamente significante. Abrir a newsletter antes do jogo aumenta cientificamente a retenção.
2. **Jogar no Período Matinal vs. Outros Horários vs. Retenção D30:**
   - Z-score = **16,40** | p-value = **0,0000** (Praticamente zero).
   - *Conclusão:* O efeito do hábito matinal é estatisticamente indiscutível.
3. **Palavras Difíceis vs. Fáceis vs. Retorno no Dia Seguinte:**
   - Z-score = **2,15** | p-value = **0,0317** (Abaixo do limite clássico de 0.05).
   - *Conclusão:* Estatisticamente significante com 95% de confiança. Palavras mais desafiadoras geram um retorno marginal superior no dia seguinte.

---

## Entrega 3 — Propostas de Produto

Com base nos dados, temos três propostas de testes de produto para a próxima semana:

### Proposta 1: A Ancoragem da Newsletter
* **Hipótese:** Acreditamos que incentivar o leitor a jogar o Palavritas logo após abrir a newsletter matinal aumentará a retenção D30, porque os dados provam que o hábito matinal combinado com a newsletter eleva a retenção de longo prazo em 24%.
* **Ação:** 
  1. Adicionar um botão destacado/CTA ("Resolva o Palavritas de hoje") na seção superior da newsletter matinal do *the news*.
  2. Implementar um sistema de login ou token de sessão rápido no link da newsletter para sabermos se o usuário veio de lá.
* **Critério de Sucesso:** Aumento de **15%** no volume de sessões que iniciam com `newsletter_open_before_game = True` na primeira semana de teste, com reflexo direto na retenção D30 do grupo testado.

### Proposta 2: Notificação Reativa Matinal baseada em Sequência (Streak)
* **Hipótese:** Acreditamos que enviar um lembrete matinal (via push ou e-mail rápido às 08h) apenas para usuários que jogaram no dia anterior mas ainda não acessaram o jogo aumentará a taxa de retorno do dia seguinte (`played_next_day`), porque o hábito matinal é o maior preditor de retenção de longo prazo.
* **Ação:** Criar uma régua de comunicação automatizada às 08h do dia seguinte focada em reengajamento diário, destacando a sequência atual do usuário (Exemplo: *"Não perca sua sequência de 5 dias! O Palavritas de hoje está liberado!"*).
* **Critério de Sucesso:** Elevação da taxa de retorno diário geral (`played_next_day`) de **22,15% para pelo menos 25%** nos usuários impactados.

### Proposta 3: Balanceamento de Dificuldade da Palavra
* **Hipótese:** Acreditamos que evitar sequências de palavras fáceis demais manterá o engajamento elevado no dia seguinte, pois palavras difíceis aumentam o retorno diário estatisticamente em 1,12 pp pelo "desejo de revanche" do jogador.
* **Ação:** Criar um cronograma dinâmico de palavras que alterne a dificuldade, garantindo que não existam dois dias seguidos de palavras com taxa de acerto alta (fáceis) e inserindo uma palavra "desafio" (difícil) pelo menos duas vezes por semana.
* **Critério de Sucesso:** Manter a média de tentativas por semana acima de **3,7** por jogo e observar um aumento de **1 pp** na taxa de retorno médio nas semanas de teste.
