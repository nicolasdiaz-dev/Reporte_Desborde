import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1wtXzHb0Jl8OZK0_K5BZpI4GdNcsbi9Iom_h5tUE4C4w"
SHEET_NAME = "DATOS INB"

creds = Credentials.from_service_account_file("credenciales.json", scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

# Leer desde A1 hasta AC (columna 29)
data = sheet.get("A:AC")

print(f"Filas leidas: {len(data)}")
print(f"Columnas en fila 1: {len(data[0]) if data else 0}")
print(f"Encabezados: {data[0] if data else []}")

# Mostrar primeras 3 filas de datos para ver el formato de hora
print("\nPrimeras 3 filas de datos:")
for row in data[1:4]:
    print(row)
