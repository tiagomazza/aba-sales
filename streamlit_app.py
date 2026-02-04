import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import os

st.set_page_config(page_title="Vendas Líquidas", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ID da sua pasta (já configurado!)
ID_PASTA_DRIVE = "1gTZfcpQLdwhhuTJO3Ls0xxWHyOAo4X1C"
SENHA_CORRETA = "admin2026"  # Mude se quiser!

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

def processar_csv(conteudo):
    """Processa qualquer CSV (Drive ou upload)"""
    try:
        if isinstance(conteudo, bytes):
            content = conteudo.decode('latin1')
        else:
            content = conteudo.read().decode('latin1') if hasattr(conteudo, 'read') else conteudo.decode('latin1')
        
        lines = content.split('\n')
        data_lines = [line for line in lines[1:] if line.strip() and not line.startswith('sep=')]
        csv_content = '\n'.join(data_lines)
        
        df = pd.read_csv(io.StringIO(csv_content), sep=',', quotechar='"', encoding='latin1', 
                        on_bad_lines='skip', engine='python')
        df.columns = df.columns.str.strip().str.replace('"', '')
        
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
        
        if 'Motivo de anulação do documento' in df_clean.columns:
            anuladas = df_clean['Motivo de anulação do documento'].notna() & \
                      (df_clean['Motivo de anulação do documento'] != '')
            df_clean = df_clean[~anuladas].copy()
        
        return df_clean[['data', 'FAMILIA', 'vendedor', 'cliente', 'valor_vendido']]
    except Exception as e:
        st.error(f"Erro processamento: {e}")
        return pd.DataFrame()

@st.cache_resource(ttl=3600)
def conectar_drive():
    """Conecta Google Drive API"""
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def listar_csvs_drive(service):
    """Lista CSVs da pasta 1gTZfcpQLdwhhuTJO3Ls0xxWHyOAo4X1C"""
    results = service.files().list(
        q=f"'{ID_PASTA_DRIVE}' in parents and name contains '.csv' and trashed=false",
        fields="files(id, name, size)").execute()
    return results.get('files', [])

def baixar_csv_drive(service, file_id):
    """Baixa CSV específico"""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

def main():
    st.title("📊 Dashboard Vendas Líquidas")
    st.markdown("**Pasta Drive configurada:** `1gTZfcpQLdwhhuTJO3Ls0xxWHyOAo4X1C`")
    
    # Sidebar
    st.sidebar.header("📁 Carregar Dados")
    
    # Opção 1: Drive (principal)
    senha = st.sidebar.text_input("🔐 Senha:", type="password")
    if st.sidebar.button("🚀 Carregar do Drive", use_container_width=True):
        if senha != SENHA_CORRETA:
            st.sidebar.error("❌ Senha incorreta!")
            st.stop()
        
        try:
            with st.spinner("🔄 Conectando Drive..."):
                service = conectar_drive()
                csvs = listar_csvs_drive(service)
                
                if not csvs:
                    st.error("❌ Nenhum CSV encontrado na pasta!")
                    st.stop()
                
                st.success(f"📂 Encontrados {len(csvs)} CSVs")
                
                dfs = []
                progress_bar = st.progress(0)
                for i, csv_file in enumerate(csvs):
                    nome = csv_file['name']
                    st.info(f"📥 {nome}...")
                    
                    conteudo = baixar_csv_drive(service, csv_file['id'])
                    df_temp = processar_csv(conteudo)
                    
                    if not df_temp.empty:
                        dfs.append(df_temp)
                    
                    progress_bar.progress((i + 1) / len(csvs))
                
                progress_bar.empty()
                
                if dfs:
                    df = pd.concat(dfs, ignore_index=True)
                    st.session_state.df = df
                    st.sidebar.success(f"✅ {len(dfs)} arquivos | {len(df):,} linhas")
                    st.rerun()
                else:
                    st.error("❌ Nenhum dado válido!")
                    st.stop()
                    
        except Exception as e:
            st.error(f"❌ Erro Drive: {e}")
            st.info("👉 Verifique: Service Account tem acesso à pasta?")
    
    # Opção 2: Upload manual (fallback)
    elif st.sidebar.file_uploader("📁 Ou faça upload:", type="csv", accept_multiple_files=True):
        uploaded_files = st.sidebar.file_uploader("CSV", type="csv", accept_multiple_files=True)
        if uploaded_files:
            dfs = [processar_csv(f) for f in uploaded_files]
            df = pd.concat([d for d in dfs if not d.empty], ignore_index=True)
            st.session_state.df = df
            st.rerun()
    else:
        st.info("👈 Digite senha e clique 'Carregar do Drive'")
        st.stop()
    
    # Dados carregados - continua igual...
    df = st.session_state.df
    
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
    
    if selected_familia: df_filtered = df_filtered[df_filtered["FAMILIA"].isin(selected_familia)]
    if selected_vendedores: df_filtered = df_filtered[df_filtered["vendedor"].isin(selected_vendedores)]

    # KPIs
    st.markdown("### 🏆 KPIs")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    total = df_filtered['valor_vendido'].sum()
    clientes = df_filtered['cliente'].nunique()
    familias = df_filtered['FAMILIA'].nunique()
    vendedores = df_filtered['vendedor'].nunique()
    ticket = total / len(df_filtered) if len(df_filtered) else 0
    
    with col1: st.metric("💰 Total", f"€{format_pt(total)}")
    with col2: st.metric("👥 Clientes", f"{clientes:,}")
    with col3: st.metric("🏷️ Famílias", familias)
    with col4: st.metric("👨‍💼 Vendedores", vendedores)
    with col5: st.metric("💳 Ticket", f"€{format_pt(ticket)}")

    # GRÁFICOS (igual ao anterior)
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
            pivot = df_filtered.pivot_table(index=linha, columns=coluna, values='valor_vendido', aggfunc=func)
        st.dataframe(pivot.style.format(format_pt))

    # Download
    st.markdown("### 📥 Exportar")
    csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📊 CSV Completo", csv_data, f"vendas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")

if __name__ == "__main__":
    main()
