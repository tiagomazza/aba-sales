import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
import re

# =============================================================================
# CONFIG
# =============================================================================
st.set_page_config(page_title="Vendas Líquidas", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# =============================================================================
# PROCESSAMENTO ROBUSTO
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            # Pula sep=, linhas vazias
            data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
            csv_content = '\n'.join(data_lines)
            
            # TENTA , depois ; (suporta ambos!)
            try:
                df = pd.read_csv(io.StringIO(csv_content), sep=',', quotechar='"', encoding='latin1', on_bad_lines='skip', engine='python')
            except:
                df = pd.read_csv(io.StringIO(csv_content), sep=';', quotechar='"', encoding='latin1', on_bad_lines='skip', engine='python')
            
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # COLUNAS CRÍTICAS (com fallback)
            df['data_venda'] = pd.to_datetime(df.get('Data', df.iloc[:,0]), format='%d-%m-%Y', errors='coerce')
            df['FAMILIA'] = df.filter(like='Família').iloc[:,0].fillna('SEM_FAMILIA').astype(str)
            df['documento'] = df.get('Doc.', df.filter(like='Doc.').iloc[:,0]).fillna('').astype(str)
            df['vendedor'] = df.get('Vendedor', df.filter(like='Vendedor').iloc[:,0]).fillna('SEM_VENDEDOR').astype(str)
            df['cliente'] = df.filter(like='Nome [Clientes]').iloc[:,0].fillna(df.filter(like='Clientes').iloc[:,0]).fillna('SEM_CLIENTE').astype(str)
            
            # Valor bruto
            valor_cols = df.filter(regex='Valor|Pr.Cmp|Custo')
            if len(valor_cols) > 0:
                df['venda_bruta'] = pd.to_numeric(
                    valor_cols.iloc[:,0].astype(str).str.replace(',', '.').str.replace('€', ''),
                    errors='coerce'
                )
            else:
                st.warning("Coluna valor não encontrada!")
                return pd.DataFrame()
            
            # VALOR LÍQUIDO (NC negativo)
            def valor_liquido(row):
                if pd.isna(row['venda_bruta']) or row['venda_bruta'] <= 0:
                    return 0
                if 'NC' in str(row['documento']).upper():
                    return -row['venda_bruta']
                return row['venda_bruta']
            
            df['venda_liquida'] = df.apply(valor_liquido, axis=1)
            
            # FILTRAGEM
            df_clean = df.dropna(subset=['data_venda', 'venda_liquida'])
            
            # ❌ Remove ANULAÇÕES
            anulacao_col = df.filter(like='anulação').columns
            if len(anulacao_col) > 0:
                anuladas = df_clean[anulacao_col[0]].notna() & (df_clean[anulacao_col[0]] != '')
                n_anuladas = anuladas.sum()
                df_clean = df_clean[~anuladas].copy()
                if n_anuladas > 0:
                    st.caption(f"🗑️ {n_anuladas} anulações removidas")
            
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'cliente', 'venda_liquida']]
        except Exception as e:
            st.error(f"Erro processamento: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

# =============================================================================
# MAIN
# =============================================================================
def main():
    st.title("💰 Dashboard Vendas Líquidas")
    st.markdown("*FT/FTS/FTP positivo | NC negativo | Sem anulações*")
    
    # Upload
    st.sidebar.header("📁 Upload")
    uploaded_file = st.sidebar.file_uploader("analise_*.csv", type="csv")
    
    if uploaded_file is None:
        st.info("👆 **Carregue o CSV**")
        st.stop()
    
    df = process_uploaded_file(uploaded_file)
    if df.empty:
        st.error("❌ **Sem dados válidos**")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ **{len(df):,}** vendas líquidas processadas")

    # FILTROS
    st.sidebar.header("🔍 **Filtros**")
    
    # Data (mês atual)
    today = datetime.now()
    first_day = today.replace(day=1)
    date_range = st.sidebar.date_input("📅 Período", value=(first_day.date(), today.date()))
    
    df_filtered = df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[
            (df_filtered["data_venda"].dt.date >= start) & 
            (df_filtered["data_venda"].dt.date <= end)
        ]
    
    # Documentos (default todos presentes)
    doc_opts = sorted(df_filtered["documento"].dropna().unique())
    default_docs = [d for d in ['FT', 'FTS', 'NC', 'FTP'] if d in doc_opts]
    selected_docs = st.sidebar.multiselect("📄 Documentos", doc_opts, default=default_docs)
    
    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    selected_familia = st.sidebar.multiselect("👨‍👩‍👧 Família", familia_opts)
    
    vendedor_opts = sorted(df_filtered["vendedor"].dropna().unique())
    selected_vendedores = st.sidebar.multiselect("👤 Vendedor", vendedor_opts)
    
    # Aplica filtros
    if selected_docs: df_filtered = df_filtered[df_filtered["documento"].isin(selected_docs)]
    if selected_familia: df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedores: df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # =============================================================================
    # KPIs
    # =============================================================================
    st.markdown("### 📊 **KPIs Líquidos**")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    valor_liq = df_filtered['venda_liquida'].sum()
    clientes = df_filtered['cliente'].nunique()
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    docs_unicos = df_filtered['documento'].nunique()
    ticket_medio = valor_liq / len(df_filtered) if len(df_filtered) else 0
    
    with col1: st.metric("💵 Valor Líquido", f"€{valor_liq:,.2f}")
    with col2: st.metric("👥 Clientes Mov.", f"{clientes:,}")
    with col3: st.metric("🏷️ Famílias", familias)
    with col4: st.metric("👨‍💼 Vendedores", vendedores)
    with col5: st.metric("📄 Docs Únicos", docs_unicos)
    with col6: st.metric("💎 Ticket Médio", f"€{ticket_medio:.2f}")

    # =============================================================================
    # DASHBOARD
    # =============================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Evolução", "🏆 Família", "👥 Vendedor", "👨‍👩 Cliente", "🔄 Pivot"])
    
    with tab1:
        vendas_diarias = df_filtered.groupby(df_filtered['data_venda'].dt.date)['venda_liquida'].sum().reset_index()
        fig = px.line(vendas_diarias, x='data_venda', y='venda_liquida', 
                     title="Evolução Valor Líquido Diário")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        top_fam = df_filtered.groupby('FAMILIA')['venda_liquida'].sum().nlargest(15).reset_index()
        fig = px.bar(top_fam, x='FAMILIA', y='venda_liquida', 
                    title="Top 15 Famílias (Líquido)", text_auto=True)
        fig.update_traces(texttemplate='€%{text:.0f}')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        top_vend = df_filtered.groupby('vendedor')['venda_liquida'].sum().nlargest(15).reset_index()
        fig = px.bar(top_vend, x='vendedor', y='venda_liquida', 
                    title="Top 15 Vendedores (Líquido)", text_auto=True)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        top_cli = df_filtered.groupby('cliente')['venda_liquida'].sum().nlargest(15).reset_index()
        fig = px.bar(top_cli, x='cliente', y='venda_liquida', 
                    title="Top 15 Clientes (Líquido)")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab5:
        row_dim = st.selectbox("Linhas", ['FAMILIA', 'vendedor', 'cliente', 'documento'])
        col_dim = st.selectbox("Colunas", ['Nenhuma', 'FAMILIA', 'vendedor', 'documento'])
        agg_func = st.selectbox("Agregação", ['sum', 'mean', 'count'])
        
        if col_dim == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=row_dim, values='venda_liquida', aggfunc=agg_func)
        else:
            pivot = df_filtered.pivot_table(index=row_dim, columns=col_dim, values='venda_liquida', aggfunc=agg_func)
        st.dataframe(pivot.style.format("{:,.2f}"), use_container_width=True)

    # =============================================================================
    # TABELA + DOWNLOAD
    # =============================================================================
    st.markdown("### 📋 **Dados Filtrados**")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        st.dataframe(df_filtered[['data_venda', 'FAMILIA', 'vendedor', 'documento', 'cliente', 'venda_liquida']].head(200), use_container_width=True)
    
    with col2:
        csv_export = df_filtered.to_csv(index=False, sep=';', encoding='utf-8-sig')  # Export ; para PT
        st.download_button(
            "📥 **Download CSV**",
            csv_export,
            f"vendas_liquidas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv"
        )

if __name__ == "__main__":
    main()
