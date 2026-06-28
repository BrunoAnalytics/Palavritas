from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import joblib
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
import traceback
import numpy as np

app = FastAPI(title="Palavritas AI Engine API")

# Carrega o modelo de Churn treinado
try:
    model = joblib.load('churn_model.pkl')
except Exception as e:
    print(f"Erro crítico ao carregar o modelo: {e}")
    model = None

# Configuração de conexão
import os

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "palavritas_dw")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise EnvironmentError("Variável de ambiente DB_PASSWORD não definida. Configure o arquivo .env.")

DB_CONFIG = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

@app.get("/predict/behavior/{user_id}")
async def get_game_intelligence(user_id: str):
    """
    Retorna as decisões da IA para o jogo baseado no perfil do utilizador.
    """
    if model is None:
        raise HTTPException(status_code=500, detail="Modelo de IA não carregado corretamente.")

    # 1. Obter features do utilizador
    try:
        conn = psycopg2.connect(DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM public.dim_users_features WHERE user_id = %s", (user_id,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro de conexão: {str(e)}")
        
    if not user_data:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado na Feature Store")
        
    # 2. Predição de Churn - Abordagem Robustecida
    try:
        df = pd.DataFrame([user_data])
        
        # Mapeamento para garantir que as colunas da tabela coincidam com as que o modelo espera
        mapping = {
            'avg_attempts_7d': 'avg_attempts_30d',
            'win_rate_7d': 'win_rate_30d',
            'near_miss_count_7d': 'near_miss_count_30d'
        }
        df = df.rename(columns=mapping)
        
        # Ordem exata das colunas que o modelo espera (não alterar a ordem!)
        expected_columns = [
            'avg_attempts_30d', 'near_miss_count_30d', 'recency_days', 
            'win_rate_30d', 'total_sessions_30d', 'max_streak_reached', 'current_streak'
        ]
        
        # Criação do input final garantindo a ordem absoluta e preenchendo faltantes com 0
        input_data = pd.DataFrame(0, index=[0], columns=expected_columns)
        for col in expected_columns:
            if col in df.columns:
                input_data[col] = df[col].iloc[0]
        
        # Converte para array numérico (numpy) para evitar problemas com nomes de colunas
        input_values = input_data.astype(float).values
        
        # Predição de probabilidade
        churn_probability = float(model.predict_proba(input_values)[0][1])
    except Exception as e:
        print(f"ERRO DETALHADO: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro no processamento do modelo: {str(e)}")
    
    # 3. Lógica de Decisão
    difficulty_adjustment = "EASY" if churn_probability > 0.6 else "NORMAL"
    reward_multiplier = 2.0 if churn_probability > 0.6 else 1.0
    
    return {
        "user_id": user_id,
        "churn_risk": round(churn_probability, 2),
        "next_word_difficulty": difficulty_adjustment,
        "reward_multiplier": reward_multiplier,
        "gamification_trigger": "streak_rescue" if churn_probability > 0.7 else "none"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)