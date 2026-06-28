import pandas as pd

df = pd.read_csv('data_clean/user_profile_clean.csv')
print("Valores de 'state' com comprimento maior que 10:")
long_states = df[df['state'].astype(str).str.len() > 10]['state'].unique()
print(long_states)

print("\nTodos os valores únicos de 'state':")
print(df['state'].unique())
