import sqlite3
import pandas as pd
import numpy as np
import math

def normal_cdf(z):
    # Aproximação da CDF da distribuição normal padrão (Erro menor que 1e-7)
    # Ref: Handbook of Mathematical Functions
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    d = 0.39894228
    prob = 1.0 - d * math.exp(-z*z / 2.0) * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    if z > 0:
        return prob
    else:
        return 1.0 - prob

def z_test_proportions(x1, n1, x2, n2):
    p1 = x1 / n1
    p2 = x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1/n1 + 1/n2))
    z = (p1 - p2) / se
    p_value = 2 * (1 - normal_cdf(abs(z)))
    return z, p_value

def calculate_significance():
    conn = sqlite3.connect('dw_palavritas.db')
    
    print("=================================================================")
    print("      CÁLCULO DE SIGNIFICÂNCIA ESTATÍSTICA (BÔNUS DO CASE)      ")
    print("=================================================================\n")
    
    # 1. Teste para: Abrir newsletter antes de jogar vs Retenção D30
    # Grupo A: Não abriu a newsletter antes de jogar
    # Grupo B: Abriu a newsletter antes de jogar
    q_news = """
    SELECT 
        newsletter_open_before_game,
        SUM(CAST(active_d30 AS INT)) as ativos_d30,
        COUNT(*) as total
    FROM fact_sessions
    GROUP BY newsletter_open_before_game;
    """
    df_news = pd.read_sql(q_news, conn)
    
    x1 = df_news[df_news['newsletter_open_before_game'] == 0]['ativos_d30'].values[0]
    n1 = df_news[df_news['newsletter_open_before_game'] == 0]['total'].values[0]
    x2 = df_news[df_news['newsletter_open_before_game'] == 1]['ativos_d30'].values[0]
    n2 = df_news[df_news['newsletter_open_before_game'] == 1]['total'].values[0]
    
    z, p_val = z_test_proportions(x2, n2, x1, n1) # Comparando B com A
    print("1. IMPACTO DE ABRIR A NEWSLETTER ANTES DE JOGAR NA RETENÇÃO D30:")
    print(f"   - Grupo A (Não abriu antes): Proporção = {x1/n1*100:.2f}% ({x1}/{n1})")
    print(f"   - Grupo B (Abriu antes): Proporção = {x2/n2*100:.2f}% ({x2}/{n2})")
    print(f"   - Diferença absoluta: +{x2/n2*100 - x1/n1*100:.2f}%")
    print(f"   - Estatística Z = {z:.4f}")
    print(f"   - p-value = {p_val:.4e}")
    print(f"   - É estatisticamente significante a 95%? {'SIM' if p_val < 0.05 else 'NÃO'}")
    print("\n")
    
    # 2. Teste para: Jogar de Manhã (06h-11h) vs Outros Períodos na Retenção D30
    # Grupo A: Jogou à tarde, noite ou madrugada
    # Grupo B: Jogou de manhã
    q_morning = """
    SELECT 
        CASE WHEN session_hour BETWEEN 6 AND 11 THEN 1 ELSE 0 END as is_morning,
        SUM(CAST(active_d30 AS INT)) as ativos_d30,
        COUNT(*) as total
    FROM fact_sessions
    GROUP BY 1;
    """
    df_morning = pd.read_sql(q_morning, conn)
    
    x1_m = df_morning[df_morning['is_morning'] == 0]['ativos_d30'].values[0]
    n1_m = df_morning[df_morning['is_morning'] == 0]['total'].values[0]
    x2_m = df_morning[df_morning['is_morning'] == 1]['ativos_d30'].values[0]
    n2_m = df_morning[df_morning['is_morning'] == 1]['total'].values[0]
    
    z_m, p_val_m = z_test_proportions(x2_m, n2_m, x1_m, n1_m)
    print("2. IMPACTO DE JOGAR DE MANHÃ (06H-11H) NA RETENÇÃO D30:")
    print(f"   - Grupo A (Tarde/Noite/Madrugada): Proporção = {x1_m/n1_m*100:.2f}% ({x1_m}/{n1_m})")
    print(f"   - Grupo B (Manhã): Proporção = {x2_m/n2_m*100:.2f}% ({x2_m}/{n2_m})")
    print(f"   - Diferença absoluta: +{x2_m/n2_m*100 - x1_m/n1_m*100:.2f}%")
    print(f"   - Estatística Z = {z_m:.4f}")
    print(f"   - p-value = {p_val_m:.4e}")
    print(f"   - É estatisticamente significante a 95%? {'SIM' if p_val_m < 0.05 else 'NÃO'}")
    print("\n")
    
    # 3. Teste para: Palavra Difícil vs Retorno no Dia Seguinte
    # Vamos considerar palavras mais difíceis (vitória < 50%) contra mais fáceis (vitória > 60%)
    # Coletamos sessões agrupadas por palavra
    q_words = """
    SELECT 
        session_id,
        word,
        played_next_day,
        attempts,
        result
    FROM fact_sessions;
    """
    df_all_s = pd.read_sql(q_words, conn)
    
    # Dificuldade da palavra baseada na taxa de vitória geral por palavra
    word_stats = df_all_s.groupby('word').agg(
        taxa_vitoria=('result', lambda s: (s == 'win').mean())
    ).reset_index()
    
    df_merged = pd.merge(df_all_s, word_stats, on='word')
    
    # Grupo A: Palavras Fáceis (Taxa Vitória >= 60%)
    # Grupo B: Palavras Difíceis (Taxa Vitória < 50%)
    easy_sessions = df_merged[df_merged['taxa_vitoria'] >= 0.60]
    hard_sessions = df_merged[df_merged['taxa_vitoria'] < 0.50]
    
    x1_w = easy_sessions['played_next_day'].sum()
    n1_w = len(easy_sessions)
    x2_w = hard_sessions['played_next_day'].sum()
    n2_w = len(hard_sessions)
    
    z_w, p_val_w = z_test_proportions(x2_w, n2_w, x1_w, n1_w)
    print("3. IMPACTO DE PALAVRA DIFÍCIL (VITÓRIA < 50%) VS FÁCIL (VITÓRIA >= 60%) NO RETORNO NO DIA SEGUINTE:")
    print(f"   - Grupo A (Palavras Fáceis): Proporção de retorno = {x1_w/n1_w*100:.2f}% ({x1_w}/{n1_w})")
    print(f"   - Grupo B (Palavras Difíceis): Proporção de retorno = {x2_w/n2_w*100:.2f}% ({x2_w}/{n2_w})")
    print(f"   - Diferença absoluta: +{x2_w/n2_w*100 - x1_w/n1_w*100:.2f}%")
    print(f"   - Estatística Z = {z_w:.4f}")
    print(f"   - p-value = {p_val_w:.4e}")
    print(f"   - É estatisticamente significante a 95%? {'SIM' if p_val_w < 0.05 else 'NÃO'}")

    conn.close()

if __name__ == '__main__':
    calculate_significance()
