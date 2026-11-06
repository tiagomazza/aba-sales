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

    # Limpeza cirúrgica e radical de células para eliminar o formato '="valor"' ou quaisquer aspas e iguais residuais
    for col in df_temp.columns:
        if df_temp[col].dtype == 'object':
            def limpar_celula(val):
                if pd.isna(val):
                    return ""
                s = str(val).strip()
                # Se a célula estiver no formato exato '="VALOR"' (começa com =" e acaba com ")
                if s.startswith('="') and s.endswith('"'):
                    return s[2:-1]  # Retira os 2 primeiros (="'") e o último caractere ('"')
                # Se começar apenas com o sinal de igual
                if s.startswith('='):
                    s = s[1:]
                # Remove quaisquer resíduos de aspas ou iguais restantes e espaços em branco
                return s.replace('"', '').replace('=', '').strip()

            df_temp[col] = df_temp[col].apply(limpar_celula)

    # Tratamento da coluna 'inactivo' (procura por correspondência exata de nome ignorando maiúsculas/minúsculas)
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
