import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os
from datetime import datetime
from google.colab import drive  # Para montar Google Drive no Colab

st.set_page_config(page_title="Vendas Líquidas", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# Configurações secretas - MUDE AQUI!
SENHA_CORRETA = "sua_senha_secreta"  # Defina sua senha
PASTA_DRIVE = "/content/drive/MyDrive/sua_pasta_csv/"  # Caminho da pasta específica

def format_pt(value):
    """Formata números PT-PT: 1.234,56"""
    if pd.isna(value) or value == 0:
        return '0,00'
    try:
        s = f"{abs(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{ '-' if value < 0 else '' }{s}"
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

@st.cache_data(ttl=3600)
def processar_csv(conteudo):
    """Processa um arquivo CSV (de upload ou Drive)"""
    try:
        if isinstance(conteudo, bytes):
            content = conteudo.decode('latin1')
        else:
            content = conteudo.read().decode('latin1')
        
        lines = content.split('\n')
        data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
        csv_content = '\n'.join(data_lines)
        
        df = pd.read_csv(io.StringIO(csv_content), sep=',', quotechar='"', encoding='latin1', 
                        on_bad_lines='skip', engine='python')
        df.columns = df.columns.str.strip().str.replace('"', '')
        
        # Renomeia colunas essenciais
        df['data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
        df['FAMILIA'] = df['Família [Artigos]'].fillna('SEM_FAMILIA').astype(str)
        df['documento'] = df['Doc.'].fillna('').astype(str)
        df['vendedor'] = df['Vendedor'].fillna('SEM_VENDEDOR').astype(str)
        
        df['cliente'] = (df.get('Terceiro', pd.Series(['']*len(df)))
                        .fillna('').astype(str).str.replace('=', '').str.replace('"', '') + 
                        ' - ' + df['Nome [Clientes]'].fillna('SEM_CLIENTE'))
        
        df['venda_bruta'] = pd.to_numeric(df['Valor [Documentos GC Lin]'].astype(str)
                                        .str.replace(',', '.').str.replace('€', ''), errors='coerce')
        
        df['valor_vendido'] = df.apply(valor_liquido, axis=1)
        
        df_clean = df.dropna(subset=['data', 'valor_vendido'])
        df_clean = df_clean[df_clean['venda_bruta'] > 0].copy()
        
        # Remove anulações
        if 'Motivo de anulação do documento' in df_clean.columns:
            anuladas = df_clean['Motivo de anulação do documento'].notna() & \
                      (df_clean['Motivo de anulação do documento'] != '')
            df_clean = df_clean[~anuladas].copy()
        
        return df_clean[['data', 'FAMILIA', 'vendedor', 'cliente', 'valor_vendido']]
    except Exception as e:
        st.error(f"Erro ao processar: {e}")
        return pd.DataFrame()

def carregar_drive():
    """Carrega todos CSVs da pasta do Drive após senha correta"""
    try:
        # Monta Drive se necessário
        if not os.path.exists('/content/drive'):
            drive.mount('/content/drive')
            st.success("✅ Drive montado!")
        
        if not os.path.exists(PASTA_DRIVE):
            st.error(f"❌ Pasta não encontrada: {PASTA_DRIVE}")
            return pd.DataFrame()
        
        arquivos = [f for f in os.listdir(PASTA_DRIVE) if f.endswith('.csv')]
        if not arquivos:
            st.warning("⚠️ Nenhum CSV na pasta.")
            return pd.DataFrame()
        
        dfs = []
        for arquivo in arquivos:
            caminho = os.path.join(PASTA_DRIVE, arquivo)
            with open(caminho, 'rb') as f:
                df_temp = processar_csv(f)
            if not df_temp.empty:
                dfs.append(df_temp)
                st.info(f"✅ {arquivo}")
        
        if dfs:
            df_final = pd.concat(dfs, ignore_index=True)
            st.success(f"🎉 Carregados {len(dfs)} arquivos!")
            return df_final
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro Drive: {e}")
        return pd.DataFrame()

def main():
    st.title("📊 Dashboard Vendas Líquidas")
    
    # Sidebar - Upload e Botão Drive
    st.sidebar.header("📁 Carregar Dados")
    
    # Opção 1: Upload manual
    uploaded_file = st.sidebar.file_uploader("Escolha CSV", type="csv")
    
    # Opção 2: Botão senha para Drive
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔐 Drive Privado**")
    senha_input = st.sidebar.text_input("Senha:", type="password")
    btn_drive = st.sidebar.button("🚀 Carregar CSVs do Drive")
    
    df = pd.DataFrame()
    
    # Lógica de carregamento
    if btn_drive:
        if senha_input == SENHA_CORRETA:
            with st.spinner("Carregando do Drive..."):
                df = carregar_drive()
        else:
            st.sidebar.error("❌ Senha incorreta!")
    
    elif uploaded_file is not None:
        with st.spinner("Processando upload..."):
            df = processar_csv(uploaded_file)
    
    else:
        st.info("👈 Carregue um CSV ou use a senha do Drive")
        st.stop()
    
    if df.empty:
        st.error("❌ Nenhum dado válido processado")
        st.stop()
    
    # Armazena no session_state
    st.session_state.df = df
    st.sidebar.success("✅ Dados carregados!")

    # FILTROS
    st.sidebar.header("🎚️ Filtros")
    today = datetime.now()
    first_day = today.replace(day=1)
    
    date_range = st.sidebar.date_input("Período", value=(first_day.date(), today.date()))
    
    df_filtered = df.copy()
    if len(date_range) == 2:
        start, end = date_range
        df_filtered = df_filtered[(df_filtered["data"].dt.date >= start) & 
                                 (df_filtered["data"].dt.date <= end)]
    
    familia_opts = sorted(df_filtered["FAMILIA"].dropna().unique())
    selected_familia = st.sidebar.multiselect("Família", familia_opts)
    
    vendedor_opts = sorted(df_filtered["vendedor"].dropna().unique())
    selected_vendedores = st.sidebar.multiselect("Vendedor", vendedor_opts)
    
    if selected_familia:
        df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedores:
        df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # KPIs
    st.markdown("### 🏆 Indicadores Principais")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    valor_total = df_filtered['valor_vendido'].sum()
    clientes_mov = df_filtered['cliente'].nunique()
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    ticket_medio = valor_total / len(df_filtered) if len(df_filtered) else 0
    
    with col1: st.metric("💰 Valor Vendido", f"€{format_pt(valor_total)}")
    with col2: st.metric("👥 Clientes", f"{clientes_mov:,}")
    with col3: st.metric("🏷️ Famílias", familias)
    with col4: st.metric("👨‍💼 Vendedores", vendedores)
    with col5: st.metric("💳 Ticket Médio", f"€{format_pt(ticket_medio)}")

    # Gráficos
    grafico_tipo = st.sidebar.selectbox("📊 Gráfico Principal", ["Valor Vendido", "Clientes Movimentados"])
    
    tabs = st.tabs(["📈 Vendas Diárias", "🏷️ Top Famílias", "👨‍💼 Top Vendedores", "👥 Top Clientes", "📊 Pivot"])
    
    with tabs[0]:
        if grafico_tipo == "Valor Vendido":
            vendas_dia = df_filtered.groupby(df_filtered['data'].dt.date)['valor_vendido'].sum().reset_index()
            fig = px.bar(vendas_dia, x='data', y='valor_vendido', title="Vendas por Dia", 
                        text='valor_vendido')
        else:
            clientes_dia = df_filtered.groupby(df_filtered['data'].dt.date)['cliente'].nunique().reset_index()
            fig = px.bar(clientes_dia, x='data', y='cliente', title="Clientes por Dia", text='cliente')
        
        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig.update_layout(yaxis_tickformat=',.0f')
        st.plotly_chart(fig, use_container_width=True)
    
    with tabs[1]:
        top_familia = df_filtered.groupby('FAMILIA')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_familia, x='FAMILIA', y='valor_vendido', title="Top 15 Famílias")
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
        row_dim = st.selectbox("Linhas", ['FAMILIA', 'vendedor', 'cliente'])
        col_dim = st.selectbox("Colunas", ['Nenhuma', 'FAMILIA', 'vendedor'])
        agg_func = st.selectbox("Agregação", ['sum', 'mean', 'count'])
        
        if col_dim == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=row_dim, values='valor_vendido', aggfunc=agg_func)
        else:
            pivot = df_filtered.pivot_table(index=row_dim, columns=col_dim, values='valor_vendido', aggfunc=agg_func)
        
        st.dataframe(pivot.style.format(format_pt), use_container_width=True)

    # Tabela final + Download
    st.markdown("### 📋 Dados Filtrados")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        st.dataframe(df_filtered[['data', 'FAMILIA', 'vendedor', 'cliente', 'valor_vendido']]
                    .head(500).style.format({'valor_vendido': format_pt}), use_container_width=True)
    
    with col2:
        csv_export = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Download CSV",
            data=csv_export,
            file_name=f"vendas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
