import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta
import io
import re  # Para extração de padrões


# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Relatório de Vendas - Dados Reais",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# FUNÇÃO PARA PROCESSAR CSV UPLOADADO
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    """Processa CSV irregular sem cabeçalho fixo"""
    if uploaded_file is not None:
        try:
            # Lê como texto e processa linha por linha
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            
            data_rows = []
            for line in lines[1:]:  # Pula possível "sep ---"
                if not line.strip():
                    continue
                parts = line.split(maxsplit=5)  # Máx 5 splits para manter resto
                
                if len(parts) >= 4:
                    # Formato: [data, ORC/FT, valor, cliente, produto/código]
                    data_str = parts[0]
                    orc_tipo = parts[1]  # FT, ENC, ABA, etc.
                    valor_str = parts[2]
                    cliente = parts[3]
                    produto = ' '.join(parts[4:]) if len(parts) > 4 else ''
                    
                    # Converte data DD-MM-YYYY
                    try:
                        data_venda = pd.to_datetime(data_str, format='%d-%m-%Y')
                    except:
                        continue
                    
                    # Extrai valor numérico (remove vírgula, pega números)
                    valor_clean = valor_str.replace(',', '.').replace('€', '')
                    valor = float(re.search(r'[\d.,]+', valor_clean).group().replace(',', '.') 
                                  if re.search(r'[\d.,]+', valor_clean) else 0)
                    
                    # FAMILIA: extrai das primeiras letras maiúsculas do produto
                    familia = re.match(r'^[A-Z]{2,5}', produto).group() if re.match(r'^[A-Z]{2,5}', produto) else 'OUTROS'
                    
                    # VENDEDOR: usa tipo de documento/orcamento ou default
                    vendedor = orc_tipo if orc_tipo in ['FT', 'ENC', 'ABA'] else 'GERAL'
                    
                    data_rows.append({
                        'data_venda': data_venda,
                        'ORC_TIPO': orc_tipo,
                        'venda': valor,
                        'cliente': cliente,
                        'produto': produto,
                        'FAMILIA': familia,
                        'VENDEDOR': vendedor
                    })
            
            df = pd.DataFrame(data_rows)
            if df.empty:
                st.warning("Nenhuma linha válida encontrada.")
                return pd.DataFrame()
            
            # Filtra só vendas positivas e datas válidas
            df = df[df['venda'] > 0].dropna(subset=['data_venda'])
            
            st.success(f"✅ Processado: {len(df):,} linhas válidas | Valor total: {df['venda'].sum():,.2f} €")
            return df[['data_venda', 'FAMILIA', 'VENDEDOR', 'cliente', 'venda']]
            
        except Exception as e:
            st.error(f"Erro no processamento: {str(e)}")
            st.info("Mostrando preview das primeiras linhas para debug:")
            content = uploaded_file.read().decode('latin1')
            st.text(content[:2000])
            return pd.DataFrame()
    return pd.DataFrame()


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================
def main():
    st.title("📊 Relatório de Vendas - Dados Reais")
    st.markdown("Dashboard otimizado para análise de **FAMILIA** e **VENDEDOR** com valor vendido (FT + FTP - NC).")

    # Sidebar - Upload de arquivo
    st.sidebar.header("📁 Upload de Dados")
    uploaded_file = st.sidebar.file_uploader("Carregue o CSV (analise_*.csv)", type="csv")
    
    if uploaded_file is not None:
        df = process_uploaded_file(uploaded_file)
        if not df.empty:
            st.sidebar.success(f"✅ Carregado: {len(df):,} registos")
            st.session_state.df = df
        else:
            st.error("❌ Não foi possível processar o arquivo.")
            st.stop()
    elif 'df' not in st.session_state:
        st.info("👆 Por favor, carregue o arquivo CSV primeiro.")
        st.stop()

    df = st.session_state.df

    # Data inicial: 1º dia do mês atual até hoje (Fev 2026)
    today = datetime.now()
    first_day_month = today.replace(day=1)
    
    st.sidebar.header("🔍 Filtros")
    
    # Filtro por data (default: mês atual)
    min_date = df["data_venda"].min().date()
    max_date = df["data_venda"].max().date()
    date_range = st.sidebar.date_input(
        "Período",
        value=(first_day_month.date(), today.date()),
        min_value=min_date,
        max_value=max_date
    )

    df_filtered = df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[
            (df_filtered["data_venda"].dt.date >= start) &
            (df_filtered["data_venda"].dt.date <= end)
        ]

    # Filtros por FAMILIA e VENDEDOR (prioridade conforme pedido)
    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    vendedor_opts = sorted(df_filtered["VENDEDOR"].dropna().unique())
    
    selected_familia = st.sidebar.multiselect("FAMILIA", options=familia_opts, default=familia_opts[:5])
    selected_vendedor = st.sidebar.multiselect("VENDEDOR", options=vendedor_opts, default=vendedor_opts[:5])
    
    if selected_familia:
        df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedor:
        df_filtered = df_filtered[df_filtered["VENDEDOR"].isin(selected_vendedor)]

    # Info básica [file:16]
    st.markdown("### 🧾 Resumo da base filtrada")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Registos", f"{len(df_filtered):,}")
    with c2:
        st.metric("Famílias", df_filtered["FAMILIA"].nunique())
    with c3:
        st.metric("Vendedores", df_filtered["VENDEDOR"].nunique())
    with c4:
        st.metric("Valor Vendido Total", f"{df_filtered['venda'].sum():,.2f} €")

    # KPIs focados em valor vendido
    st.markdown("### 💰 KPIs Principais")
    k1, k2, k3 = st.columns(3)
    valor_total = df_filtered["venda"].sum()
    valor_medio = df_filtered["venda"].mean()
    n_vendas = len(df_filtered)

    with k1:
        st.metric("Valor Vendido", f"{valor_total:,.2f} €")
    with k2:
        st.metric("Ticket Médio", f"{valor_medio:,.2f} €")
    with k3:
        st.metric("Nº Vendas", f"{n_vendas:,}")

    # Gráficos focados em FAMILIA e VENDEDOR
    st.markdown("### 📈 Análises por Segmento")
    tab1, tab2, tab3 = st.tabs(["Evolução Temporal", "Top FAMILIA", "Top VENDEDOR"])

    with tab1:
        vendas_dia = df_filtered.groupby(df_filtered["data_venda"].dt.date)["venda"].sum().reset_index()
        fig = px.line(vendas_dia, x="data_venda", y="venda", title="Evolução do Valor Vendido")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        top_familia = df_filtered.groupby("FAMILIA")["venda"].sum().sort_values(ascending=False).head(15).reset_index()
        fig = px.bar(top_familia, x="FAMILIA", y="venda", title="Top Famílias por Valor Vendido", text_auto=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(top_familia.style.format({'venda': '{:,.2f} €'}), use_container_width=True)

    with tab3:
        top_vendedor = df_filtered.groupby("VENDEDOR")["venda"].sum().sort_values(ascending=False).head(15).reset_index()
        fig = px.bar(top_vendedor, x="VENDEDOR", y="venda", title="Top Vendedores por Valor Vendido", text_auto=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(top_vendedor.style.format({'venda': '{:,.2f} €'}), use_container_width=True)

    # Tabela dinâmica focada em segmentos
    st.markdown("### 🔄 Tabela Dinâmica")
    col1, col2 = st.columns(2)
    with col1:
        row_dim = st.selectbox("Linhas", ["FAMILIA", "VENDEDOR", "cliente"])
    with col2:
        col_dim = st.selectbox("Colunas", ["Nenhuma", "FAMILIA", "VENDEDOR"])

    agg_func = st.selectbox("Agregação", ["sum", "mean", "count"])

    if col_dim == "Nenhuma":
        pivot = pd.pivot_table(df_filtered, index=row_dim, values="venda", aggfunc=agg_func)
    else:
        pivot = pd.pivot_table(df_filtered, index=row_dim, columns=col_dim, values="venda", aggfunc=agg_func)

    st.dataframe(pivot.style.format("{:,.2f}"), use_container_width=True)

    # Dados detalhados
    with st.expander("Ver dados filtrados"):
        st.dataframe(df_filtered.head(500), use_container_width=True)

    # Download
    csv = df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download CSV Filtrado", csv, "dados_filtrados.csv", "text/csv")

if __name__ == "__main__":
    main()
