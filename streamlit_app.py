import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os
from datetime import datetime
from google.colab import drive  # Para montar Google Drive no Colab

st.set_page_config(page_title="Vendas Líquidas", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# Senha secreta (mude para a sua!)
SENHA_CORRETA = "SUA_SENHA_AQUI"
PASTA_DRIVE = "/content/drive/MyDrive/sua_pasta_csv/"  # Caminho da pasta específica no Drive

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
def process_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('latin1')
            lines = content.split('\n')
            data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
            csv_content = '\n'.join(data_lines)
            
            df = pd.read_csv(io.StringIO(csv_content), sep=',', quotechar='"', encoding='latin1', on_bad_lines='skip', engine='python')
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # Renomeadas as colunas
            df['data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
            df['FAMILIA'] = df['Família [Artigos]'].fillna('SEM_FAMILIA').astype(str)
            df['documento'] = df['Doc.'].fillna('').astype(str)
            df['vendedor'] = df['Vendedor'].fillna('SEM_VENDEDOR').astype(str)
            
            df['cliente'] = (df.get('Terceiro', pd.Series(['']*len(df)))
                             .fillna('').astype(str)
                             .str.replace('=', '').str.replace('"', '') + 
                             ' - ' + df['Nome [Clientes]'].fillna('SEM_CLIENTE'))
            
            df['venda_bruta'] = pd.to_numeric(df['Valor [Documentos GC Lin]'].astype(str)
                                            .str.replace(',', '.').str.replace('€', ''), errors='coerce')
            
            df['valor_vendido'] = df.apply(valor_liquido, axis=1)
            
            df_clean = df.dropna(subset=['data', 'valor_vendido'])
            df_clean = df_clean[df_clean['venda_bruta'] > 0].copy()
            
            # Remove anulações SEM exibir mensagem
            if 'Motivo de anulação do documento' in df_clean.columns:
                anuladas = df_clean['Motivo de anulação do documento'].notna() & \
                          (df_clean['Motivo de anulação do documento'] != '')
                df_clean = df_clean[~anuladas].copy()
            
            # Retorna apenas colunas essenciais (sem documento nos KPIs)
            return df_clean[['data', 'FAMILIA', 'vendedor', 'cliente', 'valor_vendido']]
        except Exception as e:
            st.error(f"Erro: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def carregar_de_drive():
    """Carrega todos CSVs da pasta específica do Drive após senha correta."""
    try:
        # Monta Drive se não montado
        if not os.path.exists('/content/drive'):
            drive.mount('/content/drive')
        
        if not os.path.exists(PASTA_DRIVE):
            st.error(f"Pasta não encontrada: {PASTA_DRIVE}")
            return pd.DataFrame()
        
        # Lista todos CSVs na pasta
        arquivos_csv = [f for f in os.listdir(PASTA_DRIVE) if f.endswith('.csv')]
        if not arquivos_csv:
            st.warning("Nenhum CSV encontrado na pasta.")
            return pd.DataFrame()
        
        dfs = []
        for arquivo in arquivos_csv:
            caminho = os.path.join(PASTA_DRIVE, arquivo)
            df_temp = process_uploaded_file(open(caminho, 'rb'))  # Simula upload
            if not df_temp.empty:
                dfs.append(df_temp)
                st.info(f"Carregado: {arquivo}")
        
        if dfs:
            df_final = pd.concat(dfs, ignore_index=True)
            return df_final
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar do Drive: {e}")
        return pd.DataFrame()

def main():
    st.title("📊 Vendas")
    
    st.sidebar.header("📁 Upload")
    uploaded_file = st.sidebar.file_uploader("CSV", type="csv")
    
    # Novo botão de senha abaixo do uploader
    st.sidebar.markdown("---")
    senha = st.sidebar.text_input("🔐 Senha para Drive:", type="password")
    if st.sidebar.button("Carregar CSVs do Drive"):
        if senha == SENHA_CORRETA:
            df_drive = carregar_de_drive()
            if not df_drive.empty:
                st.session_state.df = df_drive
                st.sidebar.success("✅ CSVs carregados do Drive!")
                st.rerun()
            else:
                st.sidebar.error("❌ Sem dados válidos no Drive.")
        else:
            st.sidebar.error("❌ Senha incorreta!")
    
    # Prioriza Drive se carregado, senão usa upload
    if 'df' in st.session_state:
        df = st.session_state.df
    elif uploaded_file is not None:
        df = process_uploaded_file(uploaded_file)
    else:
        st.info("👈 Carregue arquivo ou use senha")
        st.stop()
    
    if df.empty:
        st.error("❌ Sem dados válidos")
        st.stop()
    
    st.session_state.df = df

    # FILTROS (resto do código igual)
    st.sidebar.header("🎚️ Filtros")
    today = datetime.now()
    first_day = today.replace(day=1)
    
    date_range = st.sidebar.date_input("Período", value=(first_day.date(), today.date()))
    
    df_filtered = df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
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

    # KPIs - SEM documentos
    st.markdown("### 🏆 KPIs")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    valor_total = df_filtered['valor_vendido'].sum()
    clientes_mov = df_filtered['cliente'].nunique()
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    ticket = valor_total / len(df_filtered) if len(df_filtered) else 0
    
    with col1: st.metric("Valor Vendido", f"€{format_pt(valor_total)}")
    with col2: st.metric("Clientes Mov.", f"{clientes_mov:,}")
    with col3: st.metric("Famílias", familias)
    with col4: st.metric("Vendedores", vendedores)
    with col5: st.metric("Ticket Médio", f"€{format_pt(ticket)}")

    # OPÇÃO DE GRÁFICO
    grafico_tipo = st.sidebar.selectbox("Gráfico Principal", ["Valor Vendido", "Clientes Movimentados"])
    
    # GRÁFICOS
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Vendas", "Ⓜ️ Família", "👥 Vendedor", "👨‍👩 Cliente", "🔄 Pivot"])
    
    with tab1:
        if grafico_tipo == "Valor Vendido":
            vendas_dia = df_filtered.groupby(df_filtered['data'].dt.date)['valor_vendido'].sum().reset_index()
            fig = px.bar(vendas_dia, x='data', y='valor_vendido', 
                        title="Vendas", text='valor_vendido')
        else:  # Clientes Movimentados
            clientes_dia = df_filtered.groupby(df_filtered['data'].dt.date)['cliente'].nunique().reset_index()
            fig = px.bar(clientes_dia, x='data', y='cliente', 
                        title="Clientes Movimentados", text='cliente')
        
        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig.update_layout(yaxis_tickformat=',.0f', xaxis_title="Data", yaxis_title=grafico_tipo)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        top_familia = df_filtered.groupby('FAMILIA')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_familia, x='FAMILIA', y='valor_vendido', title="Top 15 Famílias")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        top_vend = df_filtered.groupby('vendedor')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_vend, x='vendedor', y='valor_vendido', title="Top 15 Vendedores")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        top_cli = df_filtered.groupby('cliente')['valor_vendido'].sum().nlargest(15).reset_index()
        fig = px.bar(top_cli, x='cliente', y='valor_vendido', title="Top 15 Clientes")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab5:
        row_dim = st.selectbox("Linhas", ['FAMILIA', 'vendedor', 'cliente'])
        col_dim = st.selectbox("Colunas", ['Nenhuma', 'FAMILIA', 'vendedor'])
        agg = st.selectbox("Função", ['sum', 'mean'])
        
        if col_dim == 'Nenhuma':
            pivot = df_filtered.pivot_table(index=row_dim, values='valor_vendido', aggfunc=agg)
        else:
            pivot = df_filtered.pivot_table(index=row_dim, columns=col_dim, values='valor_vendido', aggfunc=agg)
        st.dataframe(pivot.style.format(format_pt))

    # Tabela + Download
    st.markdown("###
