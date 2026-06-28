import os

print("--- VERIFICANDO VARIÁVEIS DO POSTGRES (PG*) ---")
pg_vars = {k: v for k, v in os.environ.items() if k.upper().startswith('PG')}
if pg_vars:
    for k, v in pg_vars.items():
        print(f"{k}: {repr(v)}")
else:
    print("Nenhuma variável de ambiente iniciando com 'PG' foi encontrada.")
