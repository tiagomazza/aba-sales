import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
import re

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
st.set_page_config(
    page_title="Dashboard Vendas Líquidas",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# PROCESSAMENTO CSV (CORRIGIDO)
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    """Processa CSV com 'sep=' no cabeçalho"""
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            
            # Remove linha com 'sep=' e detecta separador
            sep_line = None
            data_lines = []
            for line in lines:
                if 'sep=' in line:
                    sep_line = line.strip()
                    continue
                if line.strip():
                    data_lines.append(line)
            
            if not data_lines:
                st.error("❌ Arquivo vazio")
                return pd.DataFrame()
            
            # Detecta separador
            real_sep = ','
            if sep_line and ';' in sep_line:
                real_sep = ';'
            elif sep_line and '\t' in sep_line:
                real_sep = '\t'
            
            st.caption(f"🔍 Separador: **'{real_sep}'**")
            
            csv_content = '\n'.join(data_lines)
            
            df = pd.read_csv(
                io.StringIO(csv_content),
                sep=real_sep,
                quotechar='"',
                encoding='latin1',
                on_bad_lines='skip',
                engine='python'
            )
            
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            st.caption(f"📋 **{len(df.columns)}** colunas: {list(df.columns[:6])}...")
            
            # Data
            data_col = df.filter(like='Data').columns
            df['data_venda'] = pd.to_datetime(
                df[data_col[0]].astype(str), 
                format='%d-%m-%Y', 
                errors='coerce'
            ) if len(data_col) > 0 else pd.NaT
            
            # Valor
            valor_cols = [col for col in df.columns if 'Valor [Documentos GC Lin]' in col]
            if not valor_cols:
                valor_cols = [col for col in df.columns if 'Valor' in col]
            valor_col = valor_cols[0] if valor_cols else None
            
            if valor_col:
                df['venda_bruta'] = pd.to_numeric(
                    df[valor_col].astype(str)
                    .str.replace(',', '.')
                    .str.replace('€', '')
                    .str.replace(' ', ''),
                    errors='coerce'
                )
            else:
                st.error("❌ Coluna valor não encontrada")
                return pd.DataFrame()
            
            # ✅ DOCUMENTO "Doc."
            doc_cols = [col for col in df.columns if 'Doc.' in col]
            doc_col = doc_cols[0] if doc_cols else None
            df['documento'] = df[doc_col].fillna('SEM_DOC').astype(str) if doc_col else 'SEM_DOC'
            
            # Família ✅ CORRIGIDO: sem regex=True duplicado
            familia_cols = df.filter(regex=r'Família|Familia').columns
            df['FAMILIA'] = df[familia_cols[0]].fillna('SEM_FAMILIA').astype(str) if len(familia_cols) > 0 else 'SEM_FAMILIA'
            
            # Vendedor e Cliente
            vendedor_cols = df.filter(regex='Vendedor').columns
            df['vendedor'] = df[vendedor_cols[0]].fillna('SEM_VENDEDOR').astype(str) if len(vendedor_cols) > 0 else 'SEM_VENDEDOR'
            
            cliente_cols = df.filter(regex='Cliente|Nome').columns
            df['cliente'] = df[cliente_cols[0]].fillna('SEM_CLIENTE').astype(str) if len(cliente_cols) > 0 else 'SEM_CLIENTE'
            
            # Valor líquido
            def valor_liquido(row):
                if pd.isna(row['venda_bruta']) or row['venda_bruta'] <= 0:
                    return 0.0
                if 'NC' in str(row['documento']).upper():
                    return -row['venda_bruta']
                return row['venda_bruta']
            
            df['venda_liquida'] = df.apply(valor_liquido, axis=1)
            
            # Filtragem
            df_clean = df.dropna(subset=['data_venda', 'venda_liquida'])
            
            # Anulações
            anulacao_cols = df.filter(like='anulação').columns
            if len(anulacao_cols) > 0:
                anuladas = df_clean[anulacao_cols[0]].notna() & (df_clean[anulacao_cols[0]] != '')
                df_clean = df_clean[~anuladas].copy()
            
            st.success(f"✅ **{len(df_clean):,}** vendas | Doc: **{doc_col or 'N/A'}**")
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'cliente', 'venda_liquida']]
            
        except Exception as e:
            st.error(f"❌ Erro: **{e}**")
            return pd.DataFrame()
    return pd.DataFrame()

# Resto igual...
def main():
    st.title("💰 **Dashboard Vendas Líquidas**")
    
    st.sidebar.header("📁 **Upload**")
    uploaded_file = st.sidebar.file_uploader("Escolha CSV", type="csv")
    
    if uploaded_file is None:
        st.info("👆 Carregue o CSV")
        st.stop()
    
    with st.spinner("🔄 Processando..."):
        df = process_uploaded_file(uploaded_file)
    
    if df.empty:
        st.error("❌ Sem dados")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ **{len(df):,}** vendas")

    st.sidebar.header("🔍 **Filtros**")
    today = datetime.now()
    first_day_month = today.replace(day=1)
    date_range = st.sidebar.date_input(
        "📅 Período",
        value=(first_day_month.date(), today.date()),
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
    
    # Filtro Documentos
    doc_opts = sorted(df_filtered["documento"].dropna().unique())[:50]
    default_docs = ['FT', 'FTS', 'NC', 'FTP']
    selected_docs = st.sidebar.multiselect(
        "📄 Documentos", 
        doc_opts, 
        default=[d for d in default_docs if d in doc_opts]
    )
    
    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    selected_familia = st.sidebar.multiselect("🏷️ Família", familia_opts)
    
    vendedor_opts = sorted(df_filtered["vendedor"].dropna().unique())
    selected_vendedores = st.sidebar.multiselect("👨‍💼 Vendedor", vendedor_opts)
    
    if selected_docs:
        df_filtered = df_filtered[df_filtered["documento"].isin(selected_docs)]
    if selected_familia:
        df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedores:
        df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # KPIs
    st.markdown("### 📊 **KPIs**")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    valor_total = df_filtered['venda_liquida'].sum()
    with col1: st.metric("💎 Total", f"€{valor_total:,.2f}")
    with col2: st.metric("📄 Docs", df_filtered['documento'].nunique())
    
    # Tabela
    st.markdown("### 📋 **Dados**")
    st.dataframe(
        df_filtered[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'venda_liquida']]
        .sort_values('venda_liquida', ascending=False)
        .head(200),
        use_container_width=True
    )

if __name__ == "__main__":
    main()
