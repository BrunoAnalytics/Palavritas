import os

print("--- VERIFICANDO VARIÁVEIS DE AMBIENTE ---")
for key in ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME']:
    val = os.getenv(key)
    if val is not None:
        print(f"{key}: {val} (Tipo: {type(val)}) (Representação: {repr(val)})")
    else:
        print(f"{key} não está definida nas variáveis de ambiente.")
