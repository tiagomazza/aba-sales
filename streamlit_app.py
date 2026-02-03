import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

st.set_page_config(page_title="Vendas Líquidas", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
            csv_content = '\n'.join(data_lines)
            
            df = pd.read_csv(io.StringIO(csv_content), sep=',', quotechar='"', encoding='latin1', on_bad_lines='skip', engine='python')
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # Colunas principais
            df['data_venda'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
            df['FAMILIA'] = df['Família [Artigos]'].fillna('SEM_FAMILIA').astype(str)
            df['documento'] = df['Doc.'].fillna('').astype(str)
            df['vendedor'] = df['Vendedor'].fillna('SEM_VENDEDOR').astype(str)
            df['cliente'] = df['Nome [Clientes]'].fillna('SEM_CLIENTE').astype(str)
            df['venda_bruta'] = pd.to_numeric(df['Valor [Documentos GC Lin]'].astype(str).str.replace(',', '.').str.replace('€', ''), errors='coerce')
            
            # Valor líquido (NC negativo)
            def valor_liquido(row):
                if pd.isna(row['venda_bruta']):
                    return 0
                if 'NC' in str(row['documento']).upper():
                    return -row['venda_bruta']
                return row['venda_bruta']
            
            df['venda_liquida'] = df.apply(valor_liquido, axis=1)
            
            # FILTRA dados válidos
            df_clean = df.dropna(subset=['data_venda', 'venda_liquida'])
            df_clean = df_clean[df_clean['venda_bruta'] > 0].copy()
            
            # ❌ NOVA: Remove ANULAÇÕES
            if 'Motivo de anulação do documento' in df_clean.columns:
                anuladas = df_clean['Motivo de anulação do documento'].notna() & (df_clean['Motivo de anulação do documento'] != '')
                n_anuladas = anuladas.sum()
                df_clean = df_clean[~anuladas].copy()
                st.caption(f"🗑️ {n_anuladas} linhas anuladas removidas")
            
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'cliente', 'venda_liquida']]
        except Exception as e:
            st.error(f"Erro: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def main():
    st.title("💰 Vendas Líquidas (sem Anulações)")
    
    st.sidebar.header("📁 Upload")
    uploaded_file = st.sidebar.file_uploader("CSV", type="csv")
    
    if uploaded_file is None:
        st.info("👆 Carregue arquivo")
        st.stop()
    
    df = process_uploaded_file(uploaded_file)
    if df.empty:
        st.error("❌ Sem dados válidos")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ {len(df):,} vendas líquidas (sem anulações)")

    # FILTROS
    st.sidebar.header("🔍 Filtros")
    today = datetime.now()
    first_day = today.replace(day=1)
    
    date_range = st.sidebar.date_input("Período", value=(first_day.date(), today.date()))
    
    df_filtered = df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[(df_filtered["data_venda"].dt.date >= start) & 
                                 (df_filtered["data_venda"].dt.date <= end)]
    
    doc_opts = sorted(df_filtered["documento"].dropna().unique())
    default_docs = [d for d in ['FT', 'FTS', 'NC', 'FTP'] if d in doc_opts]
    selected_docs = st.sidebar.multiselect("Documentos", doc_opts, default=default_docs)
    
    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    selected_familia = st.sidebar.multiselect("Família", familia_opts)
    
    vendedor_opts = sorted(df_filtered["vendedor"].dropna().unique())
    selected_vendedores = st.sidebar.multiselect("Vendedor", vendedor_opts)
    
    if selected_docs: df_filtered = df_filtered[df_filtered["documento"].isin(selected_docs)]
    if selected_familia: df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedores: df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # KPIs
    st.markdown("### 📊 KPIs (sem anulações)")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    valor_liquido = df_filtered['venda_liquida'].sum()
    clientes_mov = df_filtered['cliente'].nunique()
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    docs = df_filtered['documento'].nunique()
    ticket = valor_liquido / len(df_filtered) if len(df_filtered) else 0
    
    with col1: st.metric("Valor Líquido", f"€{valor_liquido:,.2f}")
    with col2: st.metric("Clientes Mov.", f"{clientes_mov:,}")
    with col3: st.metric("Famílias", familias)
    with col4: st.metric("Vendedores", vendedores)
    with col5: st.metric("Documentos", docs)
    with col6: st.metric("Ticket Médio", f"€{ticket:.2f}")

    # GRÁFICOS
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Evolução", "🏆 Família", "👥 Vendedor", "👨‍👩 Cliente", "🔄 Pivot"])
    
    with tab1:
        vendas_dia = df_filtered.groupby(df_filtered['data_venda'].dt.date)['venda_liquida'].sum().reset_index()
        fig = px.line(vendas_dia, x='data_venda', y='venda_liquida', title="Valor Líquido Diário")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        top_familia = df_filtered.groupby('FAMILIA')['venda_liquida'].sum().nlargest(15).reset_index()
        fig = px.bar(top_familia, x='FAMILIA', y='venda_liquida', title="Top 15 Famílias")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        top_vend = df_filtered.groupby('vendedor')['venda_liquida'].sum().nlargest(15).reset_index()
        fig = px.bar(top_vend, x='vendedor', y='venda_liquida', title="Top 15 Vendedores")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        top_cli = df_filtered.groupby('cliente')['venda_liquida'].sum().nlargest(15).reset_index()
        fig = px.bar(top_cli, x='cliente', y='venda_liquida', title="Top 15 Clientes")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab5:
        row_dim = st.selectbox("Linhas", ['FAMILIA', 'vendedor', 'cliente', 'documento'])
        col_dim = st.selectbox("Colunas", ['Nenhuma', 'FAMILIA', 'vendedor', 'documento'])
        agg = st.selectbox("Função", ['sum', 'mean'])
        
        if col_dim == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=row_dim, values='venda_liquida', aggfunc=agg)
        else:
            pivot = df_filtered.pivot_table(index=row_dim, columns=col_dim, values='venda_liquida', aggfunc=agg)
        st.dataframe(pivot.style.format("{:,.2f}"))

    # Tabela + Download
    st.markdown("### 📋 Dados (sem anulações)")
    col1, col2 = st.columns([4,1])
    with col1:
        st.dataframe(df_filtered.head(200), use_container_width=True)
    with col2:
        csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 CSV Limpo", csv, f"vendas_limpa_{datetime.now().strftime('%Y%m%d')}.csv")

if __name__ == "__main__":
    main()
