import psycopg2
import sys

print("--- TESTANDO CONEXÃO POSTGRESQL DIRETAMENTE ---")
try:
    # Tenta conectar usando os dados do script
    conn = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="123456",
        host="localhost",
        port="5432"
    )
    print("Conexão estabelecida com sucesso!")
    conn.close()
except Exception as e:
    print(f"Erro bruto detectado: {type(e)}")
    # Se for erro de decode ou contiver bytes não-decodificados
    try:
        # Se for um erro de psycopg2, as mensagens de erro podem estar em bytes na libpq
        # Vamos tentar decodificar a mensagem de forma segura com latin-1
        msg = str(e).encode('utf-8', errors='replace').decode('latin-1')
        print(f"Mensagem de erro tratada: {msg}")
    except Exception as decode_err:
        print(f"Não foi possível decodificar a mensagem de erro: {decode_err}")
