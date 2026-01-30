import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Relatório de Vendas ST",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CARREGAMENTO DE DADOS (Google Sheets)
# =============================================================================
@st.cache_data(ttl=1800)  # Cache 30min
def load_data():
    """Carrega dados do Google Sheets público"""
    csv_url = (
        "https://docs.google.com/spreadsheets/d/"
        "1Ta1kAFkXne4wv4W9vpBYcqoWqSJOqToAwriSAnDT7cY/"
        "export?format=csv&gid=0"
    )
    
    try:
        df = pd.read_csv(csv_url)
        st.cache_data.clear()  # Limpa cache na primeira carga
        st.success(f"✅ Dados carregados: {len(df):,} registos")
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar: {str(e)}")
        st.error("Verifique se o Google Sheets está público")
        st.stop()

# =============================================================================
# PROCESSAMENTO DOS DADOS
# =============================================================================
def preprocess_data(df):
    """Processa e limpa os dados"""
    df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
    
    # Conversões automáticas
    for col in df.columns:
        # Datas
        if any(x in col for x in ['data', 'date', 'dt']):
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        # Números
        elif any(x in col for x in ['valor', 'value', 'total', 'quant', 'preco', 'price']):
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Remove linhas vazias
    df = df.dropna(subset=[col for col in df.columns if df[col].dtype in ['int64', 'float64']])
    
    return df

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================
def main():
    st.title("📊 Relatório de Vendas - Análise Completa")
    st.markdown("---")
    
    # Carrega dados
    with st.spinner("Carregando dados..."):
        df_raw = load_data()
        df = preprocess_data(df_raw.copy())
    
    # Debug: Info dos dados
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Registos", f"{len(df):,}")
    with col2: st.metric("Colunas", len(df.columns))
    with col3: st.metric("Período", f"{df.select_dtypes(include=['datetime']).min().min().date()} até {df.select_dtypes(include=['datetime']).max().max().date()}")
    with col4:
        if st.button("🔄 Recarregar"):
            st.cache_data.clear()
            st.rerun()
    
    # =============================================================================
    # SIDEBAR - FILTROS
    # =============================================================================
    st.sidebar.header("🔍 Filtros")
    
    # Detecta colunas relevantes
    date_cols = [col for col in df.columns if df[col].dtype == 'datetime64[ns]']
    num_cols = [col for col in df.columns if df[col].dtype in ['int64', 'float64']]
    cat_cols = [col for col in df.columns if df[col].dtype == 'object']
    
    df_filtered = df.copy()
    
    # Filtro data
    if date_cols:
        col_data = date_cols[0]
        min_date, max_date = df[col_data].min(), df[col_data].max()
        date_range = st.sidebar.date_input(
            "📅 Período",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_date=max_date.date()
        )
        if len(date_range) == 2:
            df_filtered = df_filtered[
                (df_filtered[col_data] >= pd.to_datetime(date_range[0])) &
                (df_filtered[col_data] <= pd.to_datetime(date_range[1]))
            ]
    
    # Filtros categóricos
    for col in cat_cols[:3]:  # Primeiros 3
        unique_vals = df_filtered[col].dropna().unique()
        if len(unique_vals) < 50:
            selected = st.sidebar.multiselect(
                f"{col.title()}",
                options=["Todos"] + sorted(unique_vals.tolist()),
                default=["Todos"]
            )
            if "Todos" not in selected:
                df_filtered = df_filtered[df_filtered[col].isin(selected)]
    
    # =============================================================================
    # KPIs PRINCIPAIS
    # =============================================================================
    st.header("💰 Indicadores Principais")
    
    num_metrics = []
    for col in num_cols[:3]:
        total = df_filtered[col].sum()
        media = df_filtered[col].mean()
        num_metrics.extend([total, media])
    
    cols = st.columns(min(6, len(num_metrics)))
    for i, val in enumerate(num_metrics):
        with cols[i % len(cols)]:
            st.metric("Métrica", f"{val:,.2f}")
    
    # =============================================================================
    # GRÁFICOS
    # =============================================================================
    st.header("📈 Visualizações")
    
    tab1, tab2, tab3 = st.tabs(["Vendas por Tempo", "Top Performers", "Distribuição"])
    
    with tab1:
        if date_cols and num_cols:
            col_date, col_num = date_cols[0], num_cols[0]
            vendas_tempo = df_filtered.groupby(col_date.dt.date)[col_num].sum().reset_index()
            
            fig = px.line(vendas_tempo, x=col_date, y=col_num, 
                         title="Evolução das Vendas", markers=True)
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        if cat_cols and num_cols:
            col_cat, col_num = cat_cols[0], num_cols[0]
            top_cat = df_filtered.groupby(col_cat)[col_num].sum().nlargest(10).reset_index()
            
           

