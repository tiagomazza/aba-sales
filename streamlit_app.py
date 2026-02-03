import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

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
# PROCESSAMENTO CSV (CORRIGIDO PARA SEU ARQUIVO)
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    """Processa CSV com 'sep=' no cabeçalho - CORRIGIDO"""
    if uploaded_file is not None:
        try:
            # Lê conteúdo bruto
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            
            # ✅ CORREÇÃO: Remove linha com 'sep=' E pega o separador real
            sep_line = None
            data_lines = []
            for i, line in enumerate(lines):
                if 'sep=' in line:
                    # Extrai o separador real da linha sep=
                    sep_line = line.strip()
                    continue
                if line.strip():
                    data_lines.append(line)
            
            if not data_lines:
                st.error("❌ Arquivo vazio após limpeza")
                return pd.DataFrame()
            
            # Detecta separador da linha 'sep=' ou usa padrão
            real_sep = ','
            if sep_line:
                if ';' in sep_line:
                    real_sep = ';'
                elif '\t' in sep_line:
                    real_sep = '\t'
            
            st.caption(f"🔍 Detectado separador: **'{real_sep}'**")
            
            # Junta linhas de dados (sem cabeçalho sep=)
            csv_content = '\n'.join(data_lines)
            
            # Lê com o separador correto
            df = pd.read_csv(
                io.StringIO(csv_content),
                sep=real_sep,
                quotechar='"',
                encoding='latin1',
                on_bad_lines='skip',
                engine='python'
            )
            
            # Limpa colunas
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # Debug: mostra primeiras colunas
            st.caption(f"📋 **{len(df.columns)}** colunas detectadas: {list(df.columns[:5])}...")
            
            # Data
            df['data_venda'] = pd.to_datetime(df.get('Data', df.iloc[:, 0]), format='%d-%m-%Y', errors='coerce')
            
            # Valor
            valor_col = 'Valor [Documentos GC Lin]'
            if valor_col not in df.columns:
                valor_cols = [col for col in df.columns if 'Valor' in col and 'Documentos' in col]
                if not valor_cols:
                    valor_cols = [col for col in df.columns if 'Valor' in col]
                if valor_cols:
                    valor_col = valor_cols[0]
                else:
                    st.error(f"❌ Coluna valor não encontrada")
                    return pd.DataFrame()
            
            df['venda_bruta'] = pd.to_numeric(
                df[valor_col].astype(str)
                .str.replace(',', '.')
                .str.replace('€', '')
                .str.replace(' ', ''),
                errors='coerce'
            )
            
            # ✅ DOCUMENTO - busca "Doc."
            doc_col = None
            if 'Doc.' in df.columns:
                doc_col = 'Doc.'
            elif any('Doc' in col for col in df.columns):
                doc_col = next(col for col in df.columns if 'Doc' in col)
            
            df['documento'] = df[doc_col].fillna('SEM_DOC').astype(str) if doc_col else 'SEM_DOC'
            
            # Outras colunas
            df['FAMILIA'] = df.filter(regex='Família|Familia', regex=True).iloc[:, 0].fillna('SEM_FAMILIA').astype(str)
            df['vendedor'] = df.filter(regex='Vendedor').iloc[:, 0].fillna('SEM_VENDEDOR').astype(str)
            df['cliente'] = df.filter(regex='Nome|Cliente').iloc[:, 0].fillna('SEM_CLIENTE').astype(str)
            
            # Valor líquido (NC negativo)
            def valor_liquido(row):
                if pd.isna(row['venda_bruta']) or row['venda_bruta'] <= 0:
                    return 0.0
                if 'NC' in str(row['documento']).upper():
                    return -row['venda_bruta']
                return row['venda_bruta']
            
            df['venda_liquida'] = df.apply(valor_liquido, axis=1)
            
            # Filtragem
            df_clean = df.dropna(subset=['data_venda', 'venda_liquida'])
            
            # Remove anulações
            anulacao_cols = df.filter(like='anulação', axis=1).columns
            if len(anulacao_cols) > 0:
                anuladas = df_clean[anulacao_cols[0]].notna() & (df_clean[anulacao_cols[0]] != '')
                n_anuladas = anuladas.sum()
                df_clean = df_clean[~anuladas].copy()
                if n_anuladas > 0:
                    st.caption(f"🗑️ **{n_anuladas}** anulações removidas")
            
            st.success(f"✅ **{len(df_clean):,}** vendas processadas | Valor: **{valor_col}** | Doc: **{doc_col or 'N/A'}**")
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'cliente', 'venda_liquida']]
            
        except Exception as e:
            st.error(f"❌ Erro: **{e}**")
            st.error("📄 Debug: primeiras linhas do arquivo:")
            # Mostra primeiras linhas para debug
            content_preview = '\n'.join(lines[:5] if 'lines' in locals() else content.split('\n')[:5])
            st.code(content_preview, language='text')
            return pd.DataFrame()
    return pd.DataFrame()

# =============================================================================
# APLICAÇÃO PRINCIPAL (IGUAL)
# =============================================================================
def main():
    st.title("💰 **Dashboard Vendas Líquidas**")
    
    st.sidebar.header("📁 **Upload CSV**")
    uploaded_file = st.sidebar.file_uploader("Escolha arquivo", type="csv")
    
    if uploaded_file is None:
        st.info("👆 **Carregue o CSV**")
        st.stop()
    
    with st.spinner("🔄 Processando..."):
        df = process_uploaded_file(uploaded_file)
    
    if df.empty:
        st.error("❌ **Sem dados válidos**")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ **{len(df):,}** vendas")

    # FILTROS
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
    
    # ✅ FILTRO DOCUMENTOS DA COLUNA "Doc."
    doc_opts = sorted(df_filtered["documento"].dropna().unique())[:50]  # Limita opções
    default_docs = [d for d in ['FT', 'FTS', 'NC', 'FTP'] if d in doc_opts]
    selected_docs = st.sidebar.multiselect("📄 Documentos", doc_opts, default=default_docs)
    
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
    st.markdown("### 📊 **Indicadores**")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    valor_total = df_filtered['venda_liquida'].sum()
    clientes_total = df_filtered['cliente'].nunique()
    familias_total = df_filtered['FAMILIA'].nunique()
    vendedores_total = df_filtered['vendedor'].nunique()
    docs_total = df_filtered['documento'].nunique()
    ticket_medio = valor_total / len(df_filtered) if len(df_filtered) > 0 else 0
    
    with col1: st.metric("💎 Valor Líquido", f"€{valor_total:,.2f}")
    with col2: st.metric("👥 Clientes", f"{clientes_total:,}")
    with col3: st.metric("🏷️ Famílias", familias_total)
    with col4: st.metric("👨‍💼 Vendedores", vendedores_total)
    with col5: st.metric("📄 Documentos", docs_total)
    with col6: st.metric("🎯 Ticket Médio", f"€{ticket_medio:.2f}")

    # Tabela final
    st.markdown("### 📋 **Dados Filtrados**")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        st.dataframe(
            df_filtered[['data_venda', 'FAMILIA', 'vendedor', 'documento', 'cliente', 'venda_liquida']]
            .sort_values('venda_liquida', ascending=False)
            .head(200), 
            use_container_width=True
        )
    
    with col2:
        csv_export = df_filtered.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            label="📥 Export CSV",
            data=csv_export,
            file_name=f"vendas_filtradas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
