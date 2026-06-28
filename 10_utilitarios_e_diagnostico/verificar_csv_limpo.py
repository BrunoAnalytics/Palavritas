import pandas as pd

df = pd.read_csv('data_clean/user_profile_clean.csv')
print("Cidades no CSV limpo:")
for val in df['city'].dropna().unique():
    print(val, [ord(c) for c in val])

print("\nSetores no CSV limpo:")
for val in df['sector'].dropna().unique():
    print(val, [ord(c) for c in val])
