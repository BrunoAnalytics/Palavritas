import pandas as pd
import requests
import io
import os

def clean_data():
    sheet_id = "104R-o0zIQz4PHkzsIaRajoL4WuGs2poTfTAGV55TPzU"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    
    print("Baixando planilha do Google Sheets...")
    response = requests.get(url)
    response.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(response.content))
    
    df_sessions = pd.read_excel(xls, sheet_name='palavritas_sessions')
    df_attempts = pd.read_excel(xls, sheet_name='palavritas_attempts')
    df_users = pd.read_excel(xls, sheet_name='user_profile')
    
    print("\n--- Diagnosticando e Limpando palavritas_sessions ---")
    print(f"Total de linhas inicial: {len(df_sessions)}")
    
    # 1. Padronizar a coluna device
    device_mapping = {
        'ios': 'iOS', 'iOS': 'iOS', 'IOS': 'iOS',
        'android': 'Android', 'Android': 'Android', 'ANDROID': 'Android'
    }
    df_sessions['device'] = df_sessions['device'].map(device_mapping).fillna(df_sessions['device'])
    print(f"Dispositivos únicos após limpeza: {df_sessions['device'].unique()}")
    
    # 2. Investigar duplicatas de session_id
    duplicates_count = df_sessions.duplicated(subset=['session_id']).sum()
    print(f"Número de session_id duplicados: {duplicates_count}")
    if duplicates_count > 0:
        # Ordenamos por 'attempts' decrescente e mantemos a primeira para garantir que pegamos o resultado final
        df_sessions = df_sessions.sort_values(by=['session_id', 'attempts'], ascending=[True, False])
        df_sessions = df_sessions.drop_duplicates(subset=['session_id'], keep='first')
        print(f"Total de linhas após dropar duplicatas de session_id: {len(df_sessions)}")

    # 3. Tratar nulos em result
    df_sessions['result'] = df_sessions['result'].fillna('unknown')
    
    # 4. Tratar datas
    df_sessions['word_date'] = pd.to_datetime(df_sessions['word_date'], format='mixed', dayfirst=True).dt.date
    
    print("\n--- Diagnosticando e Limpando user_profile ---")
    # 1. Corrigir encoding corrompido
    encoding_fixes = {
        'city': {
            'Braslia': 'Brasília',
            'So Paulo': 'São Paulo',
        },
        'sector': {
            'educao': 'educação',
            'finanas': 'finanças',
            'sade': 'saúde',
        },
        'company_size': {
            'mdia': 'média'
        }
    }
    for col, mapping in encoding_fixes.items():
        df_users[col] = df_users[col].replace(mapping)
        
    print("Cidades após correção de encoding:", df_users['city'].dropna().unique())
    print("Setores após correção de encoding:", df_users['sector'].dropna().unique())
    
    # 2. Normalizar orders_food_delivery para booleano
    food_delivery_map = {
        'True': True, 'sim': True, '1': True,
        'False': False, 'não': False, 'no': False, '0': False
    }
    df_users['orders_food_delivery'] = df_users['orders_food_delivery'].astype(str).str.strip().map(food_delivery_map)
    # Qualquer outro valor vira False
    df_users['orders_food_delivery'] = df_users['orders_food_delivery'].fillna(False).astype(bool)
    print("orders_food_delivery únicos após normalização:", df_users['orders_food_delivery'].unique())

    print("\n--- Gravando arquivos locais limpos ---")
    os.makedirs('data_clean', exist_ok=True)
    df_sessions.to_csv('data_clean/palavritas_sessions_clean.csv', index=False)
    df_attempts.to_csv('data_clean/palavritas_attempts_clean.csv', index=False)
    df_users.to_csv('data_clean/user_profile_clean.csv', index=False)
    print("Arquivos limpos salvos em 'data_clean/'!")

if __name__ == '__main__':
    clean_data()
