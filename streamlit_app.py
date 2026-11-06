import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="ABA-Route",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("ABA-Route")

# URL direto (Raw) fixo do ficheiro CSV no GitHub
GITHUB_URL = "https://raw.githubusercontent.com/tiagomazza/aba-route/main/clientes.csv"
ENCODING = "latin-1"

# Definição da função para carregar e tratar os dados com cache do Streamlit
@st.cache_data
def load_data(url, enc):
    # Carrega o CSV ignorando a primeira linha (header=1) para que a linha seguinte se torne o cabeçalho
    try:
        df_temp = pd.read_csv(url, sep=",", encoding=enc, header=1)
        if len(df_temp.columns) == 1:
            df_temp = pd.read_csv(url, sep=";", encoding=enc, header=1)
    except Exception:
        df_temp = pd.read_csv(url, sep=";", encoding=enc, header=1)

    # Limpeza geral de segurança em todas as colunas de texto
    for col in df_temp.columns:
        if df_temp[col].dtype == 'object':
            df_temp[col] = df_temp[col].astype(str).str.strip()

    # Tratamento específico para remover o padrão exacto '="' no início e '"' no fim nas colunas críticas
    colunas_alvo = ['cliente', 'telefone', 'telemóvel', 'telemovel']
    for col in df_temp.columns:
        # Verifica se o nome da coluna corresponde (ignorando maiúsculas/minúsculas e acentos)
        col_lower = col.strip().lower()
        if any(alvo in col_lower for alvo in colunas_alvo):
            df_temp[col] = (
                df_temp[col]
                .astype(str)
                .str.replace(r'^="', '', regex=True)  # Remove '="' do início
                .str.replace(r'"$', '', regex=True)   # Remove '"' do final
                .str.replace(r'=', '', regex=True)    # Remove qualquer '=' residual
                .str.strip()
            )

    # Tratamento da coluna 'inactivo' (0 -> "não" e 1 -> "sim")
    col_inactivo = [c for c in df_temp.columns if c.strip().lower() in ['inactivo', 'inativo']]
    if col_inactivo:
        target_col = col_inactivo[0]
        df_temp[target_col] = df_temp[target_col].astype(str).str.strip()
        mapa_inactivo = {'0': 'não', '1': 'sim', '0.0': 'não', '1.0': 'sim'}
        df_temp[target_col] = df_temp[target_col].replace(mapa_inactivo)

    return df_temp

try:
    df = load_data(GITHUB_URL, ENCODING)
    st.success("Ficheiro clientes.csv carregado e processado com sucesso!")

    st.markdown("---")

    st.subheader("Visualização dos Dados")
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error(f"Erro ao carregar o ficheiro CSV do GitHub: {e}")
