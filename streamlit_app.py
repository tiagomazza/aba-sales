import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Relatório de Vendas ST - Dados Fictícios",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# GERAÇÃO DE DADOS FICTÍCIOS
# =============================================================================
@st.cache_data(ttl=600)
def generate_fake_sales(n_rows=1000, n_days=90, random_state=42):
    np.random.seed(random_state)

    # Datas
    end_date = datetime.today()
    start_date = end_date - timedelta(days=n_days)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")

    # Dimensões fictícias
    produtos = [
        "Produto A", "Produto B", "Produto C",
        "Produto D", "Produto E"
    ]
    vendedores = [
        "Vendedor 1", "Vendedor 2", "Vendedor 3",
        "Vendedor 4"
    ]
    clientes = [
        "Cliente X", "Cliente Y", "Cliente Z",
        "Cliente W", "Cliente Q"
    ]
    regioes = ["Norte", "Centro", "Sul", "Ilhas"]

    # Gera linhas
    data = {
        "data_venda": np.random.choice(dates, size=n_rows),
        "produto": np.random.choice(produtos, size=n_rows, p=[0.25, 0.2, 0.2, 0.2, 0.15]),
        "vendedor": np.random.choice(vendedores, size=n_rows),
        "cliente": np.random.choice(clientes, size=n_rows),
        "regiao": np.random.choice(regioes, size=n_rows),
        "quantidade": np.random.randint(1, 20, size=n_rows),
        "preco_unitario": np.round(np.random.uniform(5, 150, size=n_rows), 2),
    }

    df = pd.DataFrame(data)
    df["total"] = df["quantidade"] * df["preco_unitario"]

    return df

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================
def main():
    st.title("📊 Relatório de Vendas - Dados Fictícios")
    st.markdown("Base de testes com vendas simuladas para treino de análises e dashboards.")

    # Sidebar - parâmetros da simulação
    st.sidebar.header("⚙️ Configuração dos Dados")
    n_rows = st.sidebar.slider("Número de registos", 200, 5000, 1000, step=100)
    n_days = st.sidebar.slider("Número de dias de histórico", 30, 365, 90, step=15)
    seed = st.sidebar.number_input("Random seed", value=42, step=1)

    with st.spinner("Gerando dados fictícios..."):
        df = generate_fake_sales(n_rows=n_rows, n_days=n_days, random_state=seed)

    # Info básica
    st.markdown("### 🧾 Resumo da base")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Registos", f"{len(df):,}")
    with c2:
        st.metric("Produtos distintos", df["produto"].nunique())
    with c3:
        st.metric("Clientes distintos", df["cliente"].nunique())
    with c4:
        st.metric("Vendedores distintos", df["vendedor"].nunique())

    # =============================================================================
    # FILTROS
    # =============================================================================
    st.sidebar.header("🔍 Filtros")

    df_filtered = df.copy()

    # Filtro por data
    min_date = df["data_venda"].min().date()
    max_date = df["data_venda"].max().date()
    date_range = st.sidebar.date_input(
        "Período de venda",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[
            (df_filtered["data_venda"].dt.date >= start)
            & (df_filtered["data_venda"].dt.date <= end)
        ]

    # Filtros categór
