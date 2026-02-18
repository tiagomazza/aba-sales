import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime, timedelta
import os
from github import Github



st.set_page_config(page_title="ABA - Sales", page_icon="📊",
                    layout="wide", initial_sidebar_state="expanded")


PASTA_CSV_LOCAL = "data"
SENHA_CORRETA = st.secrets.get("PASSWORD", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO = "tiagomazza/aba-sales"



def format_pt(value):
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
    doc = str(row['Doc.']).upper()
    debitos = {'NC', 'NCA', 'NCM', 'NCS', 'NFI', 'QUE', 'ND'}
    return -row['venda_bruta'] if doc in debitos else row['venda_bruta']



def obter_data_upload_github(nome_arquivo, repo_nome, token=""):
    if not token:
        return None
    try:
        g = Github(token)
        repo = g.get_repo(repo_nome)
        caminhos = [nome_arquivo, f"data/{nome_arquivo}"]
        for caminho in caminhos:
            try:
                conteudo = repo.get_contents(caminho)
                if hasattr(conteudo, 'last_commit') and conteudo.last_commit:
                    return conteudo.last_commit.commit.committer.date.replace(tzinfo=None)
                commits = list(repo.get_commits(path=caminho))[:1]
                if commits:
                    return commits[0].commit.committer.date.replace(tzinfo=None)
            except:
                continue
        return None
    except Exception as e:
        st.error(f"GitHub erro: {e}")
        return None



def processar_csv(conteudo, nome_arquivo=""):
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
        df['documento'] = df.get('Doc.', '').fillna('').astype(str)
        df['vendedor'] = df['Vendedor'].fillna('SEM_VENDEDOR').astype(str)


        df['cliente'] = (
            df.get('Terceiro', pd.Series([''] * len(df)))
            .fillna('').astype(str).str.replace('=', '').str.replace('"', '')
            + ' - ' + df['Nome [Clientes]'].fillna('SEM_CLIENTE')
        )


        df['venda_bruta'] = pd.to_numeric(
            df['Valor [Documentos GC Lin]'].astype(str).str.replace(',', '.').str.replace('€', ''),
            errors='coerce'
        )


        df['valor_vendido'] = df.apply(valor_liquido, axis=1)
        df_clean = df.dropna(subset=['data', 'valor_vendido'])
        df_clean = df_clean[df_clean['venda_bruta'] > 0].copy()


        if 'Motivo de anulação do documento' in df_clean.columns:
            anuladas = df_clean['Motivo de anulação do documento'].notna() & \
                       (df_clean['Motivo de anulação do documento'] != '')
            df_clean = df_clean[~anuladas].copy()


        df_clean['arquivo'] = nome_arquivo
        return df_clean[['data', 'FAMILIA', 'vendedor', 'cliente', 'documento', 'valor_vendido', 'arquivo']]
    except Exception as e:
        st.error(f"Erro CSV: {e}")
        return pd.DataFrame()



def listar_csvs_pasta_local(pasta):
    if not os.path.isdir(pasta):
        return []
    return [f for f in os.listdir(pasta) if f.lower().endswith('.csv')]



def carregar_csvs_pasta_local(pasta):
    arquivos = listar_csvs_pasta_local(pasta)
    if not arquivos:
        return [], pd.DataFrame(), {}


    dfs, datas_upload = [], {}
    progress_bar = st.progress(0)


    for i, nome in enumerate(arquivos):
        st.info(f"📥 {nome}")
        try:
            with open(os.path.join(pasta, nome), 'rb') as f:
                conteudo = f.read()


            data_upload = obter_data_upload_github(nome, GITHUB_REPO, GITHUB_TOKEN)
            datas_upload[nome] = data_upload


            if data_upload:
                st.success(f"✅ {nome}: {data_upload.strftime('%d/%m %H:%M')}")
            else:
                st.warning(f"⚠️ {nome}: Sem data de atualização")


            df_temp = processar_csv(conteudo, nome)
            if not df_temp.empty:
                dfs.append(df_temp)


        except Exception as e:
            st.error(f"❌ Erro {nome}: {e}")


        progress_bar.progress((i + 1) / len(arquivos))
    progress_bar.empty()


    df_final = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return arquivos, df_final, datas_upload



def criar_pie_sem_rotulos_menores_1pc(grup_df, nome_categoria, titulo):
    """Cria gráfico de pizza mantendo TODAS fatias, mas sem rótulos < 1%"""
    total_geral = grup_df['valor_vendido'].sum()
    
    fig_pie = px.pie(
        grup_df,
        names=nome_categoria,
        values='valor_vendido',
        title=titulo
    )
    
    # Remove rótulos de fatias < 1%
    fig_pie.update_traces(
        textinfo='percent+label',
        textfont_size=12,
        textposition='inside',
        texttemplate='%{label}<br>%{percent:.1%}',
        insidetextorientation='radial'
    )
    
    # Configura hover para mostrar valores exatos
    fig_pie.update_traces(
        hovertemplate='<b>%{label}</b><br>' +
                      'Valor: €%{value:,.0f}<br>' +
                      'Percentual: %{percent:.1%}<extra></extra>'
    )
    
    return fig_pie


def get_date_range(periodo):
    """Retorna as datas inicial e final baseado no período selecionado"""
    hoje = datetime.now().date()
    
    if periodo == "Esta semana":
        # Segunda até hoje
        inicio_semana = hoje - timedelta(days=hoje.weekday())  # Segunda
        return inicio_semana, hoje
    
    elif periodo == "Este mês":
        # Dia 1 até hoje
        inicio_mes = hoje.replace(day=1)
        return inicio_mes, hoje
    
    elif periodo == "Este ano":
        # 1º Jan até hoje
        inicio_ano = hoje.replace(month=1, day=1)
        return inicio_ano, hoje
    
    elif periodo == "Semana passada":
        # Segunda a sexta da semana passada
        ultima_segunda = hoje - timedelta(days=hoje.weekday() + 7)  # Segunda passada
        ultima_sexta = ultima_segunda + timedelta(days=4)
        return ultima_segunda, ultima_sexta
    
    elif periodo == "Mês passado":
        # Dia 1 até último dia do mês passado
        if hoje.month == 1:
            inicio_mes_passado = (hoje.replace(year=hoje.year-1, month=12, day=1)).date()
            ultimo_dia = datetime(hoje.year-1, 12, 31).date()
        else:
            mes_passado = hoje.month - 1
            ano = hoje.year if mes_passado > 0 else hoje.year - 1
            inicio_mes_passado = hoje.replace(month=mes_passado, day=1).date()
            proximo_mes = mes_passado + 1 if mes_passado < 12 else 1
            proximo_ano = ano if mes_passado < 12 else ano + 1
            ultimo_dia = (hoje.replace(month=proximo_mes, year=proximo_ano, day=1) - timedelta(days=1)).date()
        return inicio_mes_passado, ultimo_dia
    
    elif periodo == "Ano passado":
        # 1º Jan até 31 Dez do ano passado
        inicio_ano_passado = datetime(hoje.year - 1, 1, 1).date()
        fim_ano_passado = datetime(hoje.year - 1, 12, 31).date()
        return inicio_ano_passado, fim_ano_passado
    
    return None, None


def main():
    st.title("📊 ABA-SALES Dashboard")


    st.sidebar.header("🗃️ Carregar ficheiros")


    # Senha → Pasta local
    senha = st.sidebar.text_input("🔐 Senha:", type="password")
    if st.sidebar.button("🚀 Carregar dados"):
        if senha != SENHA_CORRETA:
            st.error("❌ Senha incorreta!")
            st.stop()


        arquivos, df, datas_upload = carregar_csvs_pasta_local(PASTA_CSV_LOCAL)
        if df.empty:
            st.error("❌ Sem dados válidos")
            st.stop()
        st.session_state.update(df=df, arquivos=arquivos, datas_upload=datas_upload)
        st.sidebar.success(f"✅ {len(arquivos)} CSV | {len(df):,} linhas")
        st.rerun()


    # Upload manual
    uploaded = st.sidebar.file_uploader("📁 Upload manual:", type="csv", accept_multiple_files=True)
    if uploaded:
        dfs = [processar_csv(f, f.name) for f in uploaded]
        df = pd.concat([d for d in dfs if not d.empty], ignore_index=True)
        if not df.empty:
            st.session_state.update(df=df, arquivos=[f.name for f in uploaded], datas_upload={})
            st.sidebar.success(f"✅ {len(uploaded)} | {len(df):,} linhas")
            st.rerun()
        else:
            st.error("❌ Sem dados")


    if "df" not in st.session_state:
        st.info("👈 Carregue os dados")
        st.stop()


    df = st.session_state.df
    datas_upload = st.session_state.get('datas_upload', {})


    # Data de atualização
    if datas_upload:
        ultima_data = max([d for d in datas_upload.values() if d is not None], default=None)
        if ultima_data:
            st.info(f"📅 Ficheiro atualizado a {ultima_data.strftime('%d/%m %H:%M')}")
        else:
            st.warning("⚠️ Ficheiros sem data de atualização válida.")
    else:
        st.info("📅 Nenhum ficheiro carregado do GitHub.")


    # 🎚️ Filtros - AMBOS OS MÉTODOS DISPONÍVEIS
    st.sidebar.header("🎚️ Filtros")
    
    # ✅ MODO 1: Períodos pré-definidos (NOVO)
    modo_filtro = st.sidebar.radio("📅 Modo de filtro:", ["Períodos", "Calendário"], index=0)
    
    data_inicio, data_fim = None, None
    
    if modo_filtro == "Períodos":
        periodo = st.sidebar.selectbox(
            "Períodos de análise",
            ["Esta semana", "Este mês", "Este ano", "Semana passada", "Mês passado", "Ano passado"]
        )
        data_inicio, data_fim = get_date_range(periodo)
        if data_inicio and data_fim:
            st.sidebar.info(f"📊 **{periodo}**: {data_inicio.strftime('%d/%m')} → {data_fim.strftime('%d/%m')}")
    
    else:  # Calendário (ANTIGO)
        hoje = datetime.now()
        ontem = hoje - timedelta(days=1)
        inicio_mes = hoje.replace(day=1)
        date_range = st.sidebar.date_input("📅 Escolha um intervalo", (inicio_mes.date(), ontem.date()))
        if len(date_range) == 2:
            data_inicio, data_fim = date_range[0], date_range[1]


    df_filt = df.copy()
    if data_inicio and data_fim:
        df_filt = df_filt[
            (df_filt.data.dt.date >= data_inicio) &
            (df_filt.data.dt.date <= data_fim)
        ]


    vendedores_unicos = sorted(df_filt.vendedor.dropna().unique())
    pre_vend = ['VT', 'OC', 'DB', 'HR', 'AB', 'FL']
    vendedor = st.sidebar.multiselect(
        "🦸 Vendedor",
        options=vendedores_unicos,
        default=[v for v in pre_vend if v in vendedores_unicos]
    )


    docs_unicos = sorted(df_filt.documento.dropna().unique())
    pre_docs = ['FT', 'FTP', 'NC','NFI']
    doc_filter = st.sidebar.multiselect(
        "📄 Documento",
        options=docs_unicos,
        default=[d for d in pre_docs if d in docs_unicos]
    )


    familia = st.sidebar.multiselect("Ⓜ️ Família", sorted(df_filt.FAMILIA.dropna().unique()))


    if vendedor:
        df_filt = df_filt[df_filt.vendedor.isin(vendedor)]
    if doc_filter:
        df_filt = df_filt[df_filt.documento.isin(doc_filter)]
    if familia:
        df_filt = df_filt[df_filt.FAMILIA.isin(familia)]


    # KPIs
    st.markdown("### 🏆 KPIs")
    cols = st.columns(5)
    total = df_filt.valor_vendido.sum()
    cli = df_filt.cliente.nunique()
    fam = df_filt.FAMILIA.nunique()
    vend = df_filt.vendedor.nunique()
    
    # ✅ Ticket médio por dias com vendas
    dias_com_venda = df_filt.groupby(df_filt.data.dt.date).valor_vendido.count().gt(0).sum()
    ticket = total / dias_com_venda if dias_com_venda > 0 else 0


    with cols[0]:
        st.metric("💰 Total", f"€{format_pt(total)}")
    with cols[1]:
        st.metric("👥 Clientes", f"{cli:,}")
    with cols[2]:
        st.metric("Ⓜ️ Famílias", fam)
    with cols[3]:
        st.metric("🦸 Vendedores", vend)
    with cols[4]:
        st.metric("💳 Ticket médio", f"€{format_pt(ticket)}")


    # Gráficos
    tipo = st.sidebar.selectbox("📊 Gráfico", ["Valor Vendido", "Clientes movimentados"])
    tabs = st.tabs(["📈 Diario de vendas", "Ⓜ️ Família", "🦸 Vendedor", "👥 Cliente", "📊 Pivot"])


    with tabs[0]:
        if tipo == "Valor Vendido":
            diario = df_filt.groupby(df_filt.data.dt.date).valor_vendido.sum().reset_index()
            fig = px.bar(diario, x='data', y='valor_vendido', title="Diário", text='valor_vendido')
        else:
            diario = df_filt.groupby(df_filt.data.dt.date).cliente.nunique().reset_index()
            fig = px.bar(diario, x='data', y='cliente', title="Clientes Diário", text='cliente')
        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)


    with tabs[1]:
        # Agrupamento completo para pizza
        grup_fam = df_filt.groupby('FAMILIA').valor_vendido.sum().reset_index()
        # Top 15 para barras
        top = grup_fam.nlargest(15, 'valor_vendido')
        fig = px.bar(top, x='FAMILIA', y='valor_vendido', title="Top Famílias")
        st.plotly_chart(fig, use_container_width=True)


        # Pizza com TODAS fatias, mas SEM rótulos < 1%
        fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_fam, 'FAMILIA', "Participação por Família (100%)")
        st.plotly_chart(fig_pie, use_container_width=True)


    with tabs[2]:
        grup_vend = df_filt.groupby('vendedor').valor_vendido.sum().reset_index()
        top = grup_vend.nlargest(15, 'valor_vendido')
        fig = px.bar(top, x='vendedor', y='valor_vendido', title="Top Vendedores")
        st.plotly_chart(fig, use_container_width=True)


        # Pizza com TODAS fatias, mas SEM rótulos < 1%
        fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_vend, 'vendedor', "Participação por Vendedor (100%)")
        st.plotly_chart(fig_pie, use_container_width=True)


    with tabs[3]:
        grup_cli = df_filt.groupby('cliente').valor_vendido.sum().reset_index()
        top = grup_cli.nlargest(15, 'valor_vendido')
        fig = px.bar(top, x='cliente', y='valor_vendido', title="Top Clientes")
        st.plotly_chart(fig, use_container_width=True)


        # Pizza com TODAS fatias, mas SEM rótulos < 1%
        fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_cli, 'cliente', "Participação por Cliente (100%)")
        st.plotly_chart(fig_pie, use_container_width=True)


    with tabs[4]:
        linha = st.selectbox("➖ Linhas", ['FAMILIA', 'vendedor', 'cliente'])
        colu = st.selectbox("➕ Colunas", ['vendedor', 'Nenhuma', 'FAMILIA'])


        func_label = st.selectbox("🔢 Agregador", ['Soma', 'Média'])
        func_map = {'Soma': 'sum', 'Média': 'mean'}
        func = func_map[func_label]


        if colu == 'Nenhuma':
            pivot = df_filt.pivot_table(index=linha, values='valor_vendido', aggfunc=func)
        else:
            pivot = df_filt.pivot_table(index=linha, columns=colu, values='valor_vendido', aggfunc=func)


        st.dataframe(pivot.style.format(format_pt))


    csv = df_filt.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        "💾 Exportar CSV",
        csv,
        f"vendas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )



if __name__ == "__main__":
    main()
