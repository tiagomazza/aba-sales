import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
st.set_page_config(
    page_title="Relatório de Vendas Completo",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# PROCESSAMENTO CSV
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    """Processa CSV com todas colunas especificadas"""
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
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
            
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # COLUNAS EXATAS
            df['data_venda'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
            df['FAMILIA'] = df['Família [Artigos]'].fillna('SEM_FAMILIA').astype(str)
            df['documento'] = df['Doc.'].fillna('').astype(str)
            df['vendedor'] = df['Vendedor'].fillna('SEM_VENDEDOR').astype(str)
            df['venda'] = pd.to_numeric(
                df['Valor [Documentos GC Lin]'].astype(str)
                .str.replace(',', '.').str.replace('€', ''),
                errors='coerce'
            )
            df['cliente'] = df['Nome [Clientes]'].fillna('SEM_CLIENTE').astype(str)
            
            # FILTRA só FT, FTP, NC
            df = df[df['documento'].str.contains('FT|FTP|NC', case=False, na=False)]
            
            df_clean = df.dropna(subset=['data_venda', 'venda'])
            df_clean = df_clean[df_clean['venda'] > 0].copy()
            
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'cliente', 'venda']]
            
        except Exception as e:
            st.error(f"Erro: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

# =============================================================================
# MAIN
# =============================================================================
def main():
    st.title("📊 Dashboard Vendas Completo")
    st.markdown("**FT/FTP/NC | Família | Vendedor | Cliente | Valor Vendido**")

    # Upload
    st.sidebar.header("📁 Upload")
    uploaded_file = st.sidebar.file_uploader("analise_*.csv", type="csv")
    
    if uploaded_file is None:
        st.info("👆 Carregue CSV")
        st.stop()
    
    df = process_uploaded_file(uploaded_file)
    if df.empty:
        st.error("❌ Sem dados válidos")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ {len(df):,} vendas FT/FTP/NC")

    # FILTROS
    st.sidebar.header("🔍 Filtros")
    
    # Data (mês atual por default)
    today = datetime.now()
    first_day = today.replace(day=1)
    date_range = st.sidebar.date_input(
        "Período", 
        value=(first_day.date(), today.date()),
        min_value=df['data_venda'].min().date(),
        max_value=df['data_venda'].max().date()
    )
    
    df_filtered = df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[
            (df_filtered["data_venda"].dt.date >= start) &
            (df_filtered["data_venda"].dt.date <= end)
        ]
    
    # Família
    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    selected_familia = st.sidebar.multiselect("👨‍👩‍👧‍👦 Família", familia_opts)
    
    # Documento
    doc_opts = sorted(df_filtered["documento"].dropna().unique())
    selected_docs = st.sidebar.multiselect("📄 Documento", doc_opts, default=['FT'])
    
    # Vendedor (NOVO)
    vendedor_opts = sorted(df_filtered["vendedor"].dropna().unique())
    selected_vendedores = st.sidebar.multiselect("👤 Vendedor", vendedor_opts)
    
    # Aplica filtros
    if selected_familia: 
        df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_docs: 
        df_filtered = df_filtered[df_filtered["documento"].isin(selected_docs)]
    if selected_vendedores: 
        df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # =============================================================================
    # KPIs
    # =============================================================================
    st.markdown("### 💰 KPIs")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    total_vendas = df_filtered['venda'].sum()
    total_linhas = len(df_filtered)
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    docs = df_filtered['documento'].nunique()
    ticket = total_vendas / total_linhas if total_linhas else 0
    
    with col1: st.metric("Valor Total", f"€{total_vendas:,.2f}")
    with col2: st.metric("Linhas", f"{total_linhas:,}")
    with col3: st.metric("Famílias", familias)
    with col4: st.metric("Vendedores", vendedores)
    with col5: st.metric("Documentos", docs)
    with col6: st.metric("Ticket Médio", f"€{ticket:.2f}")

    # =============================================================================
    # GRÁFICOS
    # =============================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Evolução", "🏆 Top Família", "👥 Top Vendedor", "👨‍👩 Top Cliente", "🔄 Pivot"])

    with tab1:
        vendas_dia = df_filtered.groupby(df_filtered['data_venda'].dt.date)['venda'].sum().reset_index()
        fig = px.line(vendas_dia, x='data_venda', y='venda', title="Evolução Diária")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        top_familia = df_filtered.groupby('FAMILIA')['venda'].sum().sort_values(ascending=False).head(15).reset_index()
        fig = px.bar(top_familia, x='FAMILIA', y='venda', title="Top 15 Famílias", text_auto=True)
        fig.update_traces(texttemplate='€%{text:.0f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        top_vendedor = df_filtered.groupby('vendedor')['venda'].sum().sort_values(ascending=False).head(15).reset_index()
        fig = px.bar(top_vendedor, x='vendedor', y='venda', title="Top 15 Vendedores", text_auto=True)
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        top_cliente = df_filtered.groupby('cliente')['venda'].sum().sort_values(ascending=False).head(15).reset_index()
        fig = px.bar(top_cliente, x='cliente', y='venda', title="Top 15 Clientes")
        st.plotly_chart(fig, use_container_width=True)

    with tab5:
        row_opts = ['FAMILIA', 'vendedor', 'cliente', 'documento']
        col_opts = ['Nenhuma'] + row_opts
        
        row_dim = st.selectbox("Linhas", row_opts)
        col_dim = st.selectbox("Colunas", col_opts)
        agg_func = st.selectbox("Função", ['sum', 'mean', 'count'])
        
        if col_dim == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=row_dim, values='venda', aggfunc=agg_func)
        else:
            pivot = df_filtered.pivot_table(index=row_dim, columns=col_dim, values='venda', aggfunc=agg_func)
        
        st.dataframe(pivot.style.format("{:,.2f}"), use_container_width=True)

    # =============================================================================
    # TABELA E DOWNLOAD
    # =============================================================================
    st.markdown("### 📋 Dados Filtrados")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        st.dataframe(df_filtered[['data_venda', 'FAMILIA', 'vendedor', 'documento', 'cliente', 'venda']].head(200), 
                    use_container_width=True)
    
    with col2:
        csv_export = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 CSV",
            data=csv_export,
            file_name=f"vendas_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
