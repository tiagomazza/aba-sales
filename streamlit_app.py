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
# PROCESSAMENTO CSV (ROBUSTO - MANTIDO ORIGINAL)
# =============================================================================
@st.cache_data(ttl=3600)
def process_uploaded_file(uploaded_file):
    """Processa CSV com separador auto-detect, filtra anulações, NC negativo"""
    if uploaded_file is not None:
        try:
            # Lê conteúdo bruto (MANTIDO IGUAL)
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\\n')
            data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
            csv_content = '\\n'.join(data_lines)
            
            # Auto-detect separador: , ou ; (MANTIDO IGUAL)
            for sep in [',', ';']:
                try:
                    df = pd.read_csv(
                        io.StringIO(csv_content),
                        sep=sep,
                        quotechar='"',
                        encoding='latin1',
                        on_bad_lines='skip',
                        engine='python'
                    )
                    break
                except:
                    continue
            else:
                st.error("❌ Formato CSV não reconhecido")
                return pd.DataFrame()
            
            # Limpa colunas (MANTIDO IGUAL)
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # COLUNAS EXATAS com fallback (MANTIDO IGUAL)
            df['data_venda'] = pd.to_datetime(df.get('Data', df.iloc[:, 0]), format='%d-%m-%Y', errors='coerce')
            
            # VALOR EXATO (MANTIDO IGUAL)
            valor_col = 'Valor [Documentos GC Lin]'
            if valor_col not in df.columns:
                valor_cols = [col for col in df.columns if 'Valor' in col]
                if valor_cols:
                    valor_col = valor_cols[0]
                else:
                    st.error(f"❌ Coluna '{valor_col}' não encontrada")
                    return pd.DataFrame()
            
            df['venda_bruta'] = pd.to_numeric(
                df[valor_col].astype(str)
                 .str.replace(',', '.')
                 .str.replace('€', '')
                 .str.replace(' ', ''),
                errors='coerce'
            )
            
            df['FAMILIA'] = df.filter(regex='Família').iloc[:, 0].fillna('SEM_FAMILIA').astype(str)
            
            # ✅ APENAS ESTA PARTE MUDOU - busca "Doc." APÓS CSV processado
            doc_col = None
            if 'Doc.' in df.columns:
                doc_col = 'Doc.'
                st.caption(f"✅ Coluna 'Doc.' encontrada e usada")
            elif any('Doc' in col for col in df.columns):
                doc_col = next(col for col in df.columns if 'Doc' in col)
                st.caption(f"✅ Coluna documento encontrada: **{doc_col}**")
            else:
                # Fallback original mantido
                df['documento'] = df.filter(regex='Documentos').iloc[:, 0].fillna('').astype(str)
                st.warning("⚠️ Usando fallback para documentos")
            
            if doc_col:
                df['documento'] = df[doc_col].fillna('').astype(str)
            
            df['vendedor'] = df.filter(regex='Vendedor').iloc[:, 0].fillna('SEM_VENDEDOR').astype(str)
            df['cliente'] = df.filter(regex='Nome|Cliente').iloc[:, 0].fillna('SEM_CLIENTE').astype(str)
            
            # VALOR LÍQUIDO (MANTIDO IGUAL)
            def valor_liquido(row):
                if pd.isna(row['venda_bruta']) or row['venda_bruta'] <= 0:
                    return 0.0
                if 'NC' in str(row['documento']).upper():
                    return -row['venda_bruta']
                return row['venda_bruta']
            
            df['venda_liquida'] = df.apply(valor_liquido, axis=1)
            
            # FILTRAGEM (MANTIDO IGUAL)
            df_clean = df.dropna(subset=['data_venda', 'venda_liquida'])
            
            # Remove ANULAÇÕES (MANTIDO IGUAL)
            anulacao_cols = df.filter(like='anulação').columns
            if len(anulacao_cols) > 0:
                anuladas = df_clean[anulacao_cols[0]].notna() & (df_clean[anulacao_cols[0]] != '')
                n_anuladas = anuladas.sum()
                df_clean = df_clean[~anuladas].copy()
                if n_anuladas > 0:
                    st.caption(f"🗑️ **{n_anuladas}** anulações removidas")
            
            st.caption(f"📊 **{len(df_clean)}** vendas líquidas válidas | Valor: **{valor_col}** | Documento: **{doc_col or 'auto'}**")
            return df_clean[['data_venda', 'FAMILIA', 'documento', 'vendedor', 'cliente', 'venda_liquida']]
            
        except Exception as e:
            st.error(f"Erro processamento: **{e}**")
            st.error(f"Detalhes: {str(e)}")
            return pd.DataFrame()
    return pd.DataFrame()

# Resto do código permanece EXATAMENTE IGUAL...
def main():
    st.title("💰 **Dashboard Vendas Líquidas**")
    st.markdown("**Valor [Documentos GC Lin]** | NC negativo | Sem anulações")
    
    st.sidebar.header("📁 **Upload CSV**")
    uploaded_file = st.sidebar.file_uploader("Escolha arquivo", type="csv")
    
    if uploaded_file is None:
        st.info("👆 **Carregue o CSV** para análise")
        st.stop()
    
    with st.spinner("🔄 Processando..."):
        df = process_uploaded_file(uploaded_file)
    
    if df.empty:
        st.error("❌ **Sem dados válidos processados**")
        st.stop()
    
    st.session_state.df = df
    st.sidebar.success(f"✅ **{len(df):,}** vendas líquidas")

    # FILTROS (MANTIDOS IGUAIS)
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
    
    doc_opts = sorted(df_filtered["documento"].dropna().unique())
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

    # KPIs, VISUALIZAÇÕES e TABELA permanecem EXATAMENTE iguais...
    # [Código das KPIs, tabs e tabela igual ao original - omitido por brevidade]
    
    st.markdown("### 📊 **Indicadores Líquidos**")
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

    # [Resto das tabs igual ao original...]
    
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
            label="📥 **Export CSV**",
            data=csv_export,
            file_name=f"vendas_liquidas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
