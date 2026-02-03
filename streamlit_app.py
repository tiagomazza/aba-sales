import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
st.set_page_config(
    page_title="Relatório de Vendas - Dados Reais",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# PROCESSAMENTO DO CSV
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    """Processa CSV com colunas específicas do utilizador"""
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            # Pula "sep=," e linhas vazias
            data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
            csv_content = '\n'.join(data_lines)
            
            df = pd.read_csv(
                io.StringIO(csv_content),
                sep=',',
                quotechar='"',
                encoding='latin1',
                on_bad_lines='skip',
                engine='python'
            )
            
            # Limpa nomes das colunas
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # COLUNAS EXATAS
            df['data_venda'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
            df['FAMILIA'] = df['Família [Artigos]'].fillna('SEM_FAMILIA').astype(str)
            df['documento'] = df['Doc.'].fillna('').astype(str)
            df['venda'] = pd.to_numeric(
                df['Valor [Documentos GC Lin]'].astype(str)
                .str.replace(',', '.').str.replace('€', ''),
                errors='coerce'
            )
            df['cliente'] = df['Nome [Clientes]'].fillna('SEM_CLIENTE').astype(str)
            
            # FILTRA só FT, FTP, NC
            df = df[df['documento'].str.contains('FT|FTP|NC', case=False, na=False)]
            
            # Só valores > 0 e datas válidas
            df_clean = df.dropna(subset=['data_venda', 'venda'])
            df_clean = df_clean[df_clean['venda'] > 0].copy()
            
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'cliente', 'venda']]
            
        except Exception as e:
            st.error(f"Erro no processamento: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================
def main():
    st.title("📊 Relatório de Vendas - Análise FT/FTP/NC")
    st.markdown("**Foco**: Família, Documentos (FT/FTP/NC), Valor Vendido")

    # Sidebar - Upload
    st.sidebar.header("📁 Upload CSV")
    uploaded_file = st.sidebar.file_uploader("Carregue analise_*.csv", type="csv")
    
    if uploaded_file is None:
        st.info("👆 Carregue o CSV para começar")
        st.stop()
    
    with st.spinner("Processando dados..."):
        df = process_uploaded_file(uploaded_file)
    
    if df.empty:
        st.error("❌ Sem dados válidos. Verifique o arquivo.")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ {len(df):,} vendas carregadas")

    # Sidebar - Filtros
    st.sidebar.header("🔍 Filtros")
    
    # Data (default: mês atual)
    today = datetime.now()
    first_day = today.replace(day=1)
    date_range = st.sidebar.date_input(
        "Período",
        value=(first_day.date(), today.date()),
        min_value=df['data_venda'].min().date(),
        max_value=df['data_venda'].max().date()
    )
    
    # Aplica filtro data
    df_filtered = df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[
            (df_filtered["data_venda"].dt.date >= start) &
            (df_filtered["data_venda"].dt.date <= end)
        ]
    
    # Filtros específicos
    familia_opts = sorted(df_filtered["FAMILIA"].unique())
    doc_opts = sorted(df_filtered["documento"].unique())
    
    selected_familia = st.sidebar.multiselect("Família", familia_opts, default=familia_opts[:10])
    selected_docs = st.sidebar.multiselect("Documentos", doc_opts, default=['FT'])
    
    if selected_familia:
        df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_docs:
        df_filtered = df_filtered[df_filtered["documento"].isin(selected_docs)]

    # =============================================================================
    # RESUMO
    # =============================================================================
    st.markdown("### 📈 Resumo")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    total_vendas = df_filtered['venda'].sum()
    total_linhas = len(df_filtered)
    familias = df_filtered['FAMILIA'].nunique()
    docs = df_filtered['documento'].nunique()
    ticket_medio = total_vendas / total_linhas if total_linhas > 0 else 0
    
    with col1: st.metric("Valor Vendido", f"€{total_vendas:,.2f}")
    with col2: st.metric("Linhas", f"{total_linhas:,}")
    with col3: st.metric("Famílias", familias)
    with col4: st.metric("Documentos", docs)
    with col5: st.metric("Ticket Médio", f"€{ticket_medio:.2f}")

    # =============================================================================
    # GRÁFICOS
    # =============================================================================
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Evolução", "🏆 Top Família", "👥 Top Clientes", "📋 Pivot"])

    with tab1:
        vendas_tempo = df_filtered.groupby(df_filtered['data_venda'].dt.date)['venda'].sum().reset_index()
        fig = px.line(vendas_tempo, x='data_venda', y='venda', 
                     title="Evolução Valor Vendido")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        top_familia = (df_filtered.groupby('FAMILIA')['venda']
                      .sum()
                      .sort_values(ascending=False)
                      .head(15)
                      .reset_index())
        fig = px.bar(top_familia, x='FAMILIA', y='venda', 
                    title="Top 15 Famílias", text_auto=True)
        fig.update_traces(texttemplate='€%{text:.0f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(top_familia.style.format({'venda': '€{:,.2f}'}))

    with tab3:
        top_clientes = (df_filtered.groupby('cliente')['venda']
                       .sum()
                       .sort_values(ascending=False)
                       .head(15)
                       .reset_index())
        fig = px.bar(top_clientes, x='cliente', y='venda',
                    title="Top 15 Clientes")
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        row_dim = st.selectbox("Linhas", ['FAMILIA', 'cliente', 'documento'])
        col_dim = st.selectbox("Colunas", ['Nenhuma', 'FAMILIA', 'documento'])
        agg = st.selectbox("Agregação", ['sum', 'mean', 'count'])
        
        if col_dim == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=row_dim, values='venda', aggfunc=agg)
        else:
            pivot = df_filtered.pivot_table(index=row_dim, columns=col_dim, values='venda', aggfunc=agg)
        
        st.dataframe(pivot.style.format("{:,.2f}"))

    # =============================================================================
    # DADOS E DOWNLOAD
    # =============================================================================
    st.markdown("### 📥 Dados e Export")
    
    col1, col2 = st.columns([3,1])
    with col1:
        st.dataframe(df_filtered.head(100), use_container_width=True)
    with col2:
        csv = df_filtered.to_csv(i
