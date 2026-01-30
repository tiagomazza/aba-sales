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

    # Filtros categóricos
    for col in ["produto", "vendedor", "regiao"]:
        valores = sorted(df[col].unique().tolist())
        selecao = st.sidebar.multiselect(
            f"{col.capitalize()}",
            options=["(Todos)"] + valores,
            default="(Todos)"
        )
        if "(Todos)" not in selecao:
            df_filtered = df_filtered[df_filtered[col].isin(selecao)]

    # =============================================================================
    # KPIs
    # =============================================================================
    st.markdown("### 💰 Indicadores principais (base filtrada)")
    k1, k2, k3 = st.columns(3)

    faturacao_total = df_filtered["total"].sum()
    quantidade_total = df_filtered["quantidade"].sum()
    ticket_medio = faturacao_total / max(len(df_filtered["cliente"].unique()), 1)

    with k1:
        st.metric("Faturação total", f"{faturacao_total:,.2f} €")
    with k2:
        st.metric("Quantidade vendida", int(quantidade_total))
    with k3:
        st.metric("Ticket médio por cliente", f"{ticket_medio:,.2f} €")

    # =============================================================================
    # GRÁFICOS
    # =============================================================================
    st.markdown("### 📈 Visualizações")

    tab1, tab2, tab3 = st.tabs(["Evolução", "Top N", "Distribuição"])

    # Evolução temporal
    with tab1:
        vendas_dia = (
            df_filtered
            .groupby(df_filtered["data_venda"].dt.date)["total"]
            .sum()
            .reset_index()
            .rename(columns={"data_venda": "data"})
        )
        fig = px.line(
            vendas_dia,
            x="data",
            y="total",
            title="Faturação diária",
            markers=True
        )
        st.plotly_chart(fig, use_container_width=True)

    # Top N
    with tab2:
        col_dim = st.selectbox("Dimensão para ranking", ["produto", "vendedor", "regiao"])
        top_n = st.slider("Top N", 3, 20, 10)

        ranking = (
            df_filtered
            .groupby(col_dim)["total"]
            .sum()
            .reset_index()
            .sort_values("total", ascending=False)
            .head(top_n)
        )

        fig_bar = px.bar(
            ranking,
            x=col_dim,
            y="total",
            title=f"Top {top_n} por {col_dim}",
            text_auto=True
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.dataframe(ranking, use_container_width=True)

    # Distribuição
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            fig_hist = px.histogram(
                df_filtered,
                x="total",
                nbins=30,
                title="Distribuição do valor total por venda"
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        with c2:
            fig_box = px.box(
                df_filtered,
                x="produto",
                y="total",
                title="Boxplot de total por produto"
            )
            st.plotly_chart(fig_box, use_container_width=True)

    # =============================================================================
    # TABELAS DETALHADAS
    # =============================================================================
    st.markdown("### 📋 Dados detalhados")

    with st.expander("Ver amostra dos dados filtrados"):
        st.dataframe(df_filtered.head(200), use_container_width=True)

    with st.expander("Resumo estatístico (numérico)"):
        st.dataframe(df_filtered[["quantidade", "preco_unitario", "total"]].describe(), use_container_width=True)

    # =============================================================================
    # TABELA DINÂMICA
    # =============================================================================
    st.markdown("### 🔄 Tabela dinâmica")

    col1, col2, col3 = st.columns(3)
    with col1:
        row_dim = st.selectbox("Linhas", ["produto", "vendedor", "regiao", "cliente"])
    with col2:
        col_dim = st.selectbox("Colunas", ["Nenhuma", "produto", "vendedor", "regiao", "cliente"])
    with col3:
        agg_metric = st.selectbox("Métrica", ["quantidade", "total"])

    agg_func = st.selectbox("Agregação", ["sum", "mean", "count"], index=0)

    if col_dim == "Nenhuma":
        pivot = pd.pivot_table(
            df_filtered,
            index=row_dim,
            values=agg_metric,
            aggfunc=agg_func
        )
    else:
        pivot = pd.pivot_table(
            df_filtered,
            index=row_dim,
            columns=col_dim,
            values=agg_metric,
            aggfunc=agg_func
        )

    st.dataframe(pivot, use_container_width=True)

    # =============================================================================
    # RODAPÉ
    # =============================================================================
    st.markdown("---")
    st.caption("App de exemplo com dados fictícios de vendas para treino de análises no Streamlit Cloud.")

if __name__ == "__main__":
    main()

