import pandas as pd
import requests
import io

sheet_id = "104R-o0zIQz4PHkzsIaRajoL4WuGs2poTfTAGV55TPzU"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

response = requests.get(url)
response.raise_for_status()
xls = pd.ExcelFile(io.BytesIO(response.content))
df_users = pd.read_excel(xls, sheet_name='user_profile')

print("Valores únicos brutos da coluna city:")
for val in df_users['city'].dropna().unique():
    print(val, [ord(c) for c in val])

print("\nValores únicos brutos da coluna sector:")
for val in df_users['sector'].dropna().unique():
    print(val, [ord(c) for c in val])
