-- =================================================================
-- QUERIES SQL DE ANÁLISE — CASE PALAVRITAS (THE NEWS)
-- Banco de Dados: PostgreSQL / SQLite (Data Warehouse Model)
-- Autor: Analista de Dados Produto & Growth
-- =================================================================

-- 1. Visão Geral das Métricas de Retenção
SELECT 
    COUNT(*) as total_sessoes,
    ROUND(AVG(CAST(played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day,
    ROUND(AVG(CAST(active_d30 AS FLOAT)) * 100, 2) as pct_active_d30
FROM fact_sessions;

-- 2. Impacto de Abrir a Newsletter antes de Jogar
SELECT 
    newsletter_open_before_game,
    COUNT(*) as total_sessoes,
    ROUND(AVG(CAST(played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day,
    ROUND(AVG(CAST(active_d30 AS FLOAT)) * 100, 2) as pct_active_d30
FROM fact_sessions
GROUP BY newsletter_open_before_game;

-- 3. Comparativo de Assinantes vs Não-Assinantes da Newsletter
SELECT 
    u.newsletter_subscriber,
    COUNT(s.session_id) as total_sessoes,
    ROUND(AVG(CAST(s.played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day,
    ROUND(AVG(CAST(s.active_d30 AS FLOAT)) * 100, 2) as pct_active_d30
FROM fact_sessions s
JOIN dim_users u ON s.user_id = u.user_id
WHERE u.newsletter_subscriber IS NOT NULL
GROUP BY u.newsletter_subscriber;

-- 4. Impacto do Período do Dia na Retenção de Longo Prazo (D30)
SELECT 
    CASE 
        WHEN session_hour BETWEEN 0 AND 5 THEN '0. Madrugada (00h-05h)'
        WHEN session_hour BETWEEN 6 AND 11 THEN '1. Manhã (06h-11h)'
        WHEN session_hour BETWEEN 12 AND 17 THEN '2. Tarde (12h-17h)'
        ELSE '3. Noite (18h-23h)'
    END as periodo_dia,
    COUNT(*) as total_sessoes,
    ROUND(AVG(CAST(played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day,
    ROUND(AVG(CAST(active_d30 AS FLOAT)) * 100, 2) as pct_active_d30
FROM fact_sessions
GROUP BY 1
ORDER BY 1;

-- 5. Impacto do Resultado e Número de Tentativas da Sessão no Retorno Diário
SELECT 
    result,
    attempts,
    COUNT(*) as total_sessoes,
    ROUND(AVG(CAST(played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day,
    ROUND(AVG(CAST(active_d30 AS FLOAT)) * 100, 2) as pct_active_d30
FROM fact_sessions
GROUP BY result, attempts
ORDER BY result, attempts;

-- 6. Análise de Dificuldade de Palavras vs Retorno no Dia Seguinte
-- Mostra a relação entre taxa de vitória e média de tentativas com a retenção no dia seguinte
SELECT 
    word,
    COUNT(*) as total_jogos,
    ROUND(AVG(attempts), 2) as media_tentativas,
    ROUND(AVG(CASE WHEN result = 'win' THEN 1.0 ELSE 0.0 END) * 100, 2) as taxa_vitoria,
    ROUND(AVG(CAST(played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day
FROM fact_sessions
GROUP BY word
ORDER BY media_tentativas DESC;

-- 7. Análise por Segmento de Trabalho (Setor)
SELECT 
    u.sector,
    COUNT(s.session_id) as total_sessoes,
    ROUND(AVG(CAST(s.played_next_day AS FLOAT)) * 100, 2) as pct_played_next_day,
    ROUND(AVG(CAST(s.active_d30 AS FLOAT)) * 100, 2) as pct_active_d30
FROM fact_sessions s
JOIN dim_users u ON s.user_id = u.user_id
WHERE u.sector IS NOT NULL
GROUP BY u.sector
ORDER BY pct_played_next_day DESC;
