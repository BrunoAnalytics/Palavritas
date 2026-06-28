import sqlite3
import pandas as pd
import numpy as np

def analyze_data():
    conn = sqlite3.connect('dw_palavritas.db')
    
    print("=================================================================")
    print("          ANALISANDO DADOS DO PALAVRITAS (DW SQLITE)             ")
    print("=================================================================\n")
    
    # 1. Visão Geral das Métricas de Retenção
    query_total = """
    SELECT 
        COUNT(*) as total_sessoes,
        AVG(CAST(played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions;
    """
    df_total = pd.read_sql(query_total, conn)
    print("--- MÉTRICAS GERAIS ---")
    print(df_total.to_string(index=False))
    print("\n")
    
    # 2. Correlação: Abrir a Newsletter antes de Jogar vs Retenção
    query_newsletter = """
    SELECT 
        newsletter_open_before_game,
        COUNT(*) as total_sessoes,
        AVG(CAST(played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions
    GROUP BY newsletter_open_before_game;
    """
    df_newsletter = pd.read_sql(query_newsletter, conn)
    print("--- Relação: Abrir Newsletter antes de jogar ---")
    print(df_newsletter.to_string(index=False))
    print("\n")
    
    # 3. Correlação: Assinante de Newsletter vs Retenção
    query_subscriber = """
    SELECT 
        u.newsletter_subscriber,
        COUNT(s.session_id) as total_sessoes,
        AVG(CAST(s.played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(s.active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions s
    JOIN dim_users u ON s.user_id = u.user_id
    WHERE u.newsletter_subscriber IS NOT NULL
    GROUP BY u.newsletter_subscriber;
    """
    df_subscriber = pd.read_sql(query_subscriber, conn)
    print("--- Relação: Usuário é assinante da Newsletter (Pesquisa) ---")
    print(df_subscriber.to_string(index=False))
    print("\n")
    
    # 4. Correlação: Dispositivo de Acesso vs Retenção
    query_device = """
    SELECT 
        device,
        COUNT(*) as total_sessoes,
        AVG(CAST(played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions
    GROUP BY device;
    """
    df_device = pd.read_sql(query_device, conn)
    print("--- Relação: Dispositivo de Acesso ---")
    print(df_device.to_string(index=False))
    print("\n")

    # 5. Correlação: Faixa de Horário do Jogo vs Retenção
    # Agrupamos em blocos: Madrugada (0-5h), Manhã (6-11h), Tarde (12-17h), Noite (18-23h)
    query_hour = """
    SELECT 
        CASE 
            WHEN session_hour BETWEEN 0 AND 5 THEN '0. Madrugada (00h-05h)'
            WHEN session_hour BETWEEN 6 AND 11 THEN '1. Manhã (06h-11h)'
            WHEN session_hour BETWEEN 12 AND 17 THEN '2. Tarde (12h-17h)'
            ELSE '3. Noite (18h-23h)'
        END as periodo_dia,
        COUNT(*) as total_sessoes,
        AVG(CAST(played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions
    GROUP BY 1
    ORDER BY 1;
    """
    df_hour = pd.read_sql(query_hour, conn)
    print("--- Relação: Período do Dia da Sessão ---")
    print(df_hour.to_string(index=False))
    print("\n")
    
    # 6. Correlação: Dificuldade da palavra (número de tentativas) e Resultado vs Retenção
    query_result = """
    SELECT 
        result,
        attempts,
        COUNT(*) as total_sessoes,
        AVG(CAST(played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions
    GROUP BY result, attempts
    ORDER BY result, attempts;
    """
    df_result = pd.read_sql(query_result, conn)
    print("--- Relação: Resultado do Jogo e Qtd de Tentativas ---")
    print(df_result.to_string(index=False))
    print("\n")

    # 7. Correlação: Setor de Trabalho do Usuário (Pesquisa) vs Retenção
    query_sector = """
    SELECT 
        u.sector,
        COUNT(s.session_id) as total_sessoes,
        AVG(CAST(s.played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(s.active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions s
    JOIN dim_users u ON s.user_id = u.user_id
    WHERE u.sector IS NOT NULL
    GROUP BY u.sector
    ORDER BY pct_played_next_day DESC;
    """
    df_sector = pd.read_sql(query_sector, conn)
    print("--- Relação: Setor de Trabalho do Usuário ---")
    print(df_sector.to_string(index=False))
    print("\n")

    # 8. Correlação: Frequência de Food Delivery (Pesquisa) vs Retenção
    query_food = """
    SELECT 
        u.food_delivery_freq_week,
        COUNT(s.session_id) as total_sessoes,
        AVG(CAST(s.played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(s.active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions s
    JOIN dim_users u ON s.user_id = u.user_id
    WHERE u.food_delivery_freq_week IS NOT NULL
    GROUP BY u.food_delivery_freq_week
    ORDER BY u.food_delivery_freq_week;
    """
    df_food = pd.read_sql(query_food, conn)
    print("--- Relação: Frequência de Food Delivery Semanal ---")
    print(df_food.to_string(index=False))
    print("\n")

    # 9. Dificuldade de Palavras Específicas
    # Média de tentativas por palavra e impacto na retenção no dia seguinte
    query_words = """
    SELECT 
        word,
        COUNT(*) as total_jogos,
        AVG(attempts) as media_tentativas,
        AVG(CASE WHEN result = 'win' THEN 1.0 ELSE 0.0 END) * 100 as taxa_vitoria,
        AVG(CAST(played_next_day AS FLOAT)) * 100 as pct_played_next_day
    FROM fact_sessions
    GROUP BY word
    ORDER BY media_tentativas DESC;
    """
    df_words = pd.read_sql(query_words, conn)
    print("--- Dificuldade de Palavras Específicas (Top 5 Mais Difíceis e Impacto) ---")
    print(df_words.head(5).to_string(index=False))
    print("\n--- Dificuldade de Palavras Específicas (Top 5 Mais Fáceis e Impacto) ---")
    print(df_words.tail(5).to_string(index=False))
    print("\n")

    # 10. Correlação: Faixa Salarial vs Retenção
    query_salary = """
    SELECT 
        u.salary_range,
        COUNT(s.session_id) as total_sessoes,
        AVG(CAST(s.played_next_day AS FLOAT)) * 100 as pct_played_next_day,
        AVG(CAST(s.active_d30 AS FLOAT)) * 100 as pct_active_d30
    FROM fact_sessions s
    JOIN dim_users u ON s.user_id = u.user_id
    WHERE u.salary_range IS NOT NULL
    GROUP BY u.salary_range
    ORDER BY pct_played_next_day DESC;
    """
    df_salary = pd.read_sql(query_salary, conn)
    print("--- Relação: Faixa Salarial ---")
    print(df_salary.to_string(index=False))
    
    conn.close()

if __name__ == '__main__':
    analyze_data()
