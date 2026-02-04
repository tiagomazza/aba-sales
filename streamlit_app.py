import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
import os

st.set_page_config(page_title="Vendas Líquidas", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

# Pasta local dentro do projeto onde estão os CSV
PASTA_CSV_LOCAL = "data"   # muda se usares outro nome
SENHA_CORRETA = "admin2026"  # Mude se quiser!

def format_pt(value):
    """Formata números PT-PT: 1.234,56"""
    if pd.isna(value) or value == 0:
        return '0,00'
    try:
        s = f"{abs(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{'-' if value < 0 else ''}{s}"
    except:
        return str(value)

def valor_liquido(row):
    if pd.isna(row['venda_bruta']):
        return 0
    doc = str(row['documento']).upper()
    debitos = {'NC', 'NCA', 'NCM', 'NCS', 'NFI', 'QUE', 'ND'}
    if doc in debitos:
        return -row['venda_bruta']
    return row['venda_bruta']

def processar_csv(conteudo):
    """Processa qualquer CSV (local ou upload)"""
    try:
        if isinstance(conteudo, bytes):
            content = conteudo.decode('latin1')
        else:
            content = conteudo.read().decode('latin1') if hasattr(conteudo, 'read') else conteudo.decode('latin1')

        lines = content.split('\n')
        data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
        csv_content = '\n'.join(data_lines)

        df = pd.read_csv(io.StringIO(csv_content), sep=',', quotechar='"',
                         encoding='latin1', on_bad_lines='skip', engine='python')
        df.columns = df.columns.str.strip().str.replace('"', '')

        df['data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
        df['FAMILIA'] = df['Família [Artigos]'].fillna('SEM_FAMILIA').astype(str)
        df['documento'] = df['Doc.'].fillna('').astype(str)
        df['vendedor'] = df['Vendedor'].fillna('SEM_VENDEDOR').astype(str)

        df['cliente'] = (
            df.get('Terceiro', pd.Series([''] * len(df)))
            .fillna('')
            .astype(str)
            .str.replace('=', '')
            .str.replace('"', '')
            + ' - ' + df['Nome [Clientes]'].fillna('SEM_CLIENTE')
        )

        df['venda_bruta'] = pd.to_numeric(
            df['Valor [Documentos GC Lin]'].astype(str)
            .str.replace(',', '.')
            .str.replace('€', ''),
            errors='coerce'
        )

        df['valor_vendido'] = df.apply(valor_liquido, axis=1)

        df_clean = df.dropna(subset=['data', 'valor_vendido'])
        df_clean = df_clean[df_clean['venda_bruta'] > 0].copy()

        if 'Motivo de anulação do documento' in df_clean.columns:
            anuladas = df_clean['Motivo de anulação do documento'].notna() & \
                       (df_clean['Motivo de anulação do documento'] != '')
            df_clean = df_clean[~anuladas].copy()

        return df_clean[['data', 'FAMILIA', 'vendedor', 'cliente', 'valor_vendido']]
    except Exception as e:
        st.error(f"Erro processamento: {e}")
        return pd.DataFrame()

def listar_csvs_pasta_local(pasta):
    """Lista CSVs numa pasta local do projeto"""
    if not os.path.isdir(pasta):
        return []
    arquivos = [
        f for f in os.listdir(pasta)
        if os.path.isfile(os.path.join(pasta, f)) and f.lower().endswith('.csv')
    ]  # [web:17][web:14]
    return arquivos

def carregar_csvs_pasta_local(pasta):
    """Lê e processa todos os CSV de uma pasta local"""
    arquivos = listar_csvs_pasta_local(pasta)
    if not arquivos:
        return [], pd.DataFrame()

    dfs = []
    progress_bar = st.progress(0)
    for i, nome in enumerate(arquivos):
        st.info(f"📥 {nome}...")
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, 'rb') as f:
                conteudo = f.read()
            df_temp = processar_csv(conteudo)
            if not df_temp.empty:
                dfs.append(df_temp)
        except Exception as e:
            st.warning(f"Erro ao ler {nome}: {e}")
        progress_bar.progress((i + 1) / len(arquivos))

    progress_bar.empty()

    if dfs:
        df = pd.concat(dfs, ignore_index=True)
        return arquivos, df
    return arquivos, pd.DataFrame()

def main():
    st.title("📊 Dashboard Vendas Líquidas")
    st.markdown(f"**Pasta local configurada:** `{PASTA_CSV_LOCAL}/`")

    # Sidebar
    st.sidebar.header("📁 Carregar Dados")

    # Opção 1: Pasta local do projeto (principal, protegida por senha)
    senha = st.sidebar.text_input("🔐 Senha:", type="password")
    if st.sidebar.button("🚀 Carregar da pasta do projeto", use_container_width=True):
        if senha != SENHA_CORRETA:
            st.sidebar.error("❌ Senha incorreta!")
            st.stop()

        arquivos, df = carregar_csvs_pasta_local(PASTA_CSV_LOCAL)
        if not arquivos:
            st.error(f"❌ Nenhum CSV encontrado em `{PASTA_CSV_LOCAL}/`")
            st.stop()
        if df.empty:
            st.error("❌ Nenhum dado válido nos CSV!")
            st.stop()

        st.success(f"📂 Encontrados {len(arquivos)} CSV(s)")
        st.session_state.df = df
        st.sidebar.success(f"✅ {len(arquivos)} arquivos | {len(df):,} linhas")
        st.rerun()

    # Opção 2: Upload manual (fallback)
    uploaded_files = st.sidebar.file_uploader(
        "📁 Ou faça upload:", type="csv", accept_multiple_files=True
    )
    if uploaded_files:
        dfs = [processar_csv(f) for f in uploaded_files]
        dfs_validos = [d for d in dfs if not d.empty]
        if not dfs_validos:
            st.error("❌ Nenhum dado válido nos ficheiros enviados!")
            st.stop()
        df = pd.concat(dfs_validos, ignore_index=True)
        st.session_state.df = df
        st.sidebar.success(f"✅ {len(dfs_validos)} arquivos | {len(df):,} linhas")
        st.rerun()

    if "df" not in st.session_state:
        st.info("👈 Digite a senha e clique 'Carregar da pasta do projeto' ou faça upload de CSV.")
        st.stop()

    # Dados carregados
    df = st.session_state.df

    # FILTROS
    st.sidebar.header("🎚️ Filtros")
    today = datetime.now()
    first_day = today.replace(day=1)

    date_range = st.sidebar.date_input("Período", value=(first_day.date(), today.date()))

    df_filtered = df.copy()
    if len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[
            (df_filtered["data"].dt.date >= start) &
            (df_filtered["data"].dt.date <= end)
        ]

    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    selected_familia = st.sidebar.multiselect("Família", familia_opts)

    vendedor_opts = sorted(df_filtered["vendedor"].dropna().unique())
    selected_vendedores = st.sidebar.multiselect("Vendedor", vendedor_opts)

    if selected_familia:
        df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedores:
        df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # KPIs
    st.markdown("### 🏆 KPIs")
    col1, col2, col3, col4, col5 = st.columns(5)

    total = df_filtered['valor_vendido'].sum()
    clientes = df_filtered['cliente'].nunique()
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    ticket = total / len(df_filtered) if len(df_filtered) else 0

    with col1:
        st.metric("💰 Total", f"€{format_pt(total)}")
    with col2:
        st.metric("👥 Clientes", f"{clientes:,}")
    with col3:
        st.metric("🏷️ Famílias", familias)
    with col4:
        st.metric("👨‍💼 Vendedores", vendedores)
    with col5:
        st.metric("💳 Ticket", f"€{format_pt(ticket)}")

    # GRÁFICOS
    tipo = st.sidebar.selectbox("📊 Principal", ["Valor Vendido", "Clientes"])

    tabs = st.tabs(["📈 Diárias", "🏷️ Famílias", "👨‍💼 Vendedores", "👥 Clientes", "📊 Pivot"])

    with tabs[0]:
        if tipo == "Valor Vendido":
            diario = df_filtered.groupby(df_filtered['data'].dt.date)['valor_vendido'].sum().reset_index()
            fig = px.bar(diario, x='data', y='valor_vendido', title="Vendas Diárias", text='valor_vendido')
        else:
            diario = df_filtered.groupby(df_filtered['data'].dt.date)['cliente'].nunique().reset_index()
            fig = px.bar(diario, x='data', y='cliente', title="Clientes Diários", text='cliente')
        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        top_fam = df_filtered.groupby('FAMILIA')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_fam, x='FAMILIA', y='valor_vendido', title="Top 15 Famílias")
        st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        top_vend = df_filtered.groupby('vendedor')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_vend, x='vendedor', y='valor_vendido', title="Top 15 Vendedores")
        st.plotly_chart(fig, use_container_width=True)

    with tabs[3]:
        top_cli = df_filtered.groupby('cliente')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_cli, x='cliente', y='valor_vendido', title="Top 15 Clientes")
        st.plotly_chart(fig, use_container_width=True)

    with tabs[4]:
        linha = st.selectbox("Linhas", ['FAMILIA', 'vendedor', 'cliente'])
        coluna = st.selectbox("Colunas", ['Nenhuma', 'FAMILIA', 'vendedor'])
        func = st.selectbox("Função", ['sum', 'mean'])

        if coluna == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=linha, values='valor_vendido', aggfunc=func)
        else:
            pivot = df_filtered.pivot_table(index=linha, columns=coluna,
                                            values='valor_vendido', aggfunc=func)
        st.dataframe(pivot.style.format(format_pt))

    # Download
    st.markdown("### 📥 Exportar")
    csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        "📊 CSV Completo",
        csv_data,
        f"vendas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )

if __name__ == "__main__":
    main()
