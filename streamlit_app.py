import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from github import Github
from pandas.errors import EmptyDataError


st.set_page_config(
    page_title="ABA - Sales",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


PASTA_CSV_LOCAL = "data"
SENHA_CORRETA = st.secrets.get("PASSWORD", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO = "tiagomazza/aba-sales"
TZ_PT = ZoneInfo("Europe/Lisbon")


def now_pt():
    return datetime.now(TZ_PT)


def format_pt(value):
    if pd.isna(value) or value == 0:
        return "0,00"
    try:
        s = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{'-' if value < 0 else ''}{s}"
    except Exception:
        return str(value)


def format_pt_sem_centimos(value):
    if pd.isna(value):
        return "€0"
    try:
        valor = int(round(float(value), 0))
        s = f"{abs(valor):,}".replace(",", ".")
        return f"{'-' if valor < 0 else ''}€{s}"
    except Exception:
        return "€0"


def valor_liquido(row):
    if pd.isna(row["venda_bruta"]):
        return 0
    doc = str(row["Doc."]).upper()
    debitos = {"NC", "NCA", "NCM", "NCS", "NFI", "QUE", "ND"}
    return -row["venda_bruta"] if doc in debitos else row["venda_bruta"]


def converter_para_hora_pt(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ_PT)


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

                if hasattr(conteudo, "last_commit") and conteudo.last_commit:
                    dt_utc = conteudo.last_commit.commit.committer.date
                    return converter_para_hora_pt(dt_utc)

                commits = list(repo.get_commits(path=caminho))[:1]
                if commits:
                    dt_utc = commits[0].commit.committer.date
                    return converter_para_hora_pt(dt_utc)

            except Exception:
                continue

        return None

    except Exception as e:
        st.error(f"GitHub erro: {e}")
        return None


def ler_conteudo_csv(conteudo):
    if isinstance(conteudo, bytes):
        raw = conteudo
    elif hasattr(conteudo, "read"):
        try:
            conteudo.seek(0)
        except Exception:
            pass
        raw = conteudo.read()
    else:
        raw = conteudo

    if isinstance(raw, bytes):
        try:
            return raw.decode("latin1")
        except Exception:
            return raw.decode("utf-8", errors="ignore")

    return str(raw)


def normalizar_linhas_csv(content):
    if "\\n" in content and "\n" not in content:
        content = content.replace("\\n", "\n")

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")

    if lines and lines[0].strip().lower().startswith("sep="):
        lines = lines[1:]

    lines = [line for line in lines if line.strip()]
    return lines


def tentar_ler_dataframe(csv_content):
    tentativas = [
        {"sep": ",", "engine": "python"},
        {"sep": ";", "engine": "python"},
        {"sep": None, "engine": "python"},
    ]

    ultimo_erro = None

    for params in tentativas:
        try:
            df = pd.read_csv(
                io.StringIO(csv_content),
                quotechar='"',
                encoding="latin1",
                on_bad_lines="skip",
                **params
            )
            if not df.empty or len(df.columns) > 0:
                return df
        except Exception as e:
            ultimo_erro = e

    if ultimo_erro:
        raise ultimo_erro

    raise EmptyDataError("Sem colunas para analisar no ficheiro.")


def processar_csv(conteudo, nome_arquivo=""):
    try:
        content = ler_conteudo_csv(conteudo)
        lines = normalizar_linhas_csv(content)

        if not lines:
            st.warning(f"⚠️ {nome_arquivo}: ficheiro vazio ou sem linhas úteis após limpeza.")
            return pd.DataFrame()

        csv_content = "\n".join(lines).strip()

        if not csv_content:
            st.warning(f"⚠️ {nome_arquivo}: sem conteúdo CSV após limpeza.")
            return pd.DataFrame()

        df = tentar_ler_dataframe(csv_content)

        df.columns = df.columns.astype(str).str.strip().str.replace('"', "", regex=False)

        colunas_obrigatorias = [
            "Data",
            "Família [Artigos]",
            "Vendedor",
            "Nome [Clientes]",
            "Valor [Documentos GC Lin]"
        ]
        faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
        if faltantes:
            st.error(f"Erro CSV em {nome_arquivo}: colunas obrigatórias em falta: {', '.join(faltantes)}")
            return pd.DataFrame()

        df["data"] = pd.to_datetime(df["Data"], format="%d-%m-%Y", errors="coerce")
        df["FAMILIA"] = df["Família [Artigos]"].fillna("SEM_FAMILIA").astype(str)
        df["documento"] = df.get("Doc.", pd.Series([""] * len(df))).fillna("").astype(str)
        df["vendedor"] = df["Vendedor"].fillna("SEM_VENDEDOR").astype(str)

        df["cliente"] = (
            df.get("Terceiro", pd.Series([""] * len(df)))
            .fillna("")
            .astype(str)
            .str.replace("=", "", regex=False)
            .str.replace('"', "", regex=False)
            + " - " +
            df["Nome [Clientes]"].fillna("SEM_CLIENTE").astype(str)
        )

        df["venda_bruta"] = pd.to_numeric(
            df["Valor [Documentos GC Lin]"]
            .astype(str)
            .str.replace("€", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce"
        )

        df["valor_vendido"] = df.apply(valor_liquido, axis=1)

        df_clean = df.dropna(subset=["data", "valor_vendido"]).copy()

        # Excluir qualquer linha com motivo de anulação preenchido
        if "Motivo de anulação do documento" in df_clean.columns:
            motivo = df_clean["Motivo de anulação do documento"].fillna("").astype(str).str.strip()
            df_clean = df_clean[motivo == ""].copy()

        df_clean = df_clean[df_clean["venda_bruta"] > 0].copy()

        df_clean["arquivo"] = nome_arquivo

        return df_clean[["data", "FAMILIA", "vendedor", "cliente", "documento", "valor_vendido", "arquivo"]]

    except EmptyDataError:
        st.error(f"Erro CSV em {nome_arquivo}: sem colunas para analisar no ficheiro.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro CSV em {nome_arquivo}: {e}")
        return pd.DataFrame()


def listar_csvs_pasta_local(pasta):
    if not os.path.isdir(pasta):
        return []
    return [f for f in os.listdir(pasta) if f.lower().endswith(".csv")]


def carregar_csvs_pasta_local(pasta):
    arquivos = listar_csvs_pasta_local(pasta)
    if not arquivos:
        return [], pd.DataFrame(), {}

    dfs = []
    datas_upload = {}
    progress_bar = st.progress(0)

    for i, nome in enumerate(arquivos):
        st.info(f"📥 {nome}")
        try:
            caminho = os.path.join(pasta, nome)

            if not os.path.isfile(caminho) or os.path.getsize(caminho) == 0:
                st.warning(f"⚠️ {nome}: ficheiro inexistente ou vazio.")
                progress_bar.progress((i + 1) / len(arquivos))
                continue

            with open(caminho, "rb") as f:
                conteudo = f.read()

            data_upload = obter_data_upload_github(nome, GITHUB_REPO, GITHUB_TOKEN)
            datas_upload[nome] = data_upload

            if data_upload:
                st.success(f"✅ {nome}: {data_upload.strftime('%d/%m/%Y %H:%M')}")
            else:
                st.warning(f"⚠️ {nome}: Sem data de atualização")

            df_temp = processar_csv(conteudo, nome)
            if not df_temp.empty:
                dfs.append(df_temp)
            else:
                st.warning(f"⚠️ {nome}: sem dados válidos após processamento.")

        except Exception as e:
            st.error(f"❌ Erro {nome}: {e}")

        progress_bar.progress((i + 1) / len(arquivos))

    progress_bar.empty()
    df_final = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return arquivos, df_final, datas_upload


def criar_pie_sem_rotulos_menores_1pc(grup_df, nome_categoria, titulo):
    fig_pie = px.pie(
        grup_df,
        names=nome_categoria,
        values="valor_vendido",
        title=titulo
    )

    fig_pie.update_traces(
        textinfo="percent+label",
        textfont_size=12,
        textposition="inside",
        texttemplate="%{label}<br>%{percent:.1%}",
        insidetextorientation="radial"
    )

    fig_pie.update_traces(
        hovertemplate="<b>%{label}</b><br>" +
                      "Valor: €%{value:,.0f}<br>" +
                      "Percentual: %{percent:.1%}<extra></extra>"
    )

    return fig_pie


def get_date_range(periodo):
    hoje = now_pt().date()

    if periodo == "Esta semana":
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        return inicio_semana, hoje

    elif periodo == "Este mês":
        inicio_mes = hoje.replace(day=1)
        return inicio_mes, hoje

    elif periodo == "Este ano":
        inicio_ano = hoje.replace(month=1, day=1)
        return inicio_ano, hoje

    elif periodo == "Semana passada":
        ultima_segunda = hoje - timedelta(days=hoje.weekday() + 7)
        ultima_sexta = ultima_segunda + timedelta(days=4)
        return ultima_segunda, ultima_sexta

    elif periodo == "Mês passado":
        if hoje.month == 1:
            inicio_mes_passado = datetime(hoje.year - 1, 12, 1).date()
            ultimo_dia = datetime(hoje.year - 1, 12, 31).date()
        else:
            inicio_mes_passado = datetime(hoje.year, hoje.month - 1, 1).date()
            primeiro_mes_atual = datetime(hoje.year, hoje.month, 1).date()
            ultimo_dia = primeiro_mes_atual - timedelta(days=1)
        return inicio_mes_passado, ultimo_dia

    elif periodo == "Ano passado":
        inicio_ano_passado = datetime(hoje.year - 1, 1, 1).date()
        fim_ano_passado = datetime(hoje.year - 1, 12, 31).date()
        return inicio_ano_passado, fim_ano_passado

    return None, None


def formatar_label_periodo(periodos, granularidade):
    if granularidade == "Dia":
        return pd.to_datetime(periodos).strftime("%d/%m/%Y")

    if granularidade == "Semana":
        labels = []
        for p in periodos:
            inicio = p.start_time.date()
            fim = p.end_time.date()
            labels.append(f"{inicio.strftime('%d/%m')} → {fim.strftime('%d/%m')}")
        return labels

    if granularidade == "Mês":
        return [p.strftime("%m/%Y") for p in periodos]

    if granularidade == "Trimestre":
        return [f"T{p.quarter}/{p.year}" for p in periodos]

    return periodos.astype(str)


def agregar_vendas(df_base, granularidade):
    df_plot = df_base.copy()
    df_plot["data"] = pd.to_datetime(df_plot["data"], errors="coerce")
    df_plot = df_plot.dropna(subset=["data"])

    if granularidade == "Dia":
        grupo = df_plot.groupby(df_plot["data"].dt.date, as_index=False)["valor_vendido"].sum()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = pd.to_datetime(grupo["periodo"])
        grupo["label"] = grupo["ordem"].dt.strftime("%d/%m/%Y")

    elif granularidade == "Semana":
        grupo = df_plot.groupby(df_plot["data"].dt.to_period("W-MON"))["valor_vendido"].sum().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = grupo["periodo"].dt.start_time
        grupo["label"] = formatar_label_periodo(grupo["periodo"], "Semana")

    elif granularidade == "Mês":
        grupo = df_plot.groupby(df_plot["data"].dt.to_period("M"))["valor_vendido"].sum().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = grupo["periodo"].dt.start_time
        grupo["label"] = formatar_label_periodo(grupo["periodo"], "Mês")

    elif granularidade == "Trimestre":
        grupo = df_plot.groupby(df_plot["data"].dt.to_period("Q"))["valor_vendido"].sum().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = grupo["periodo"].dt.start_time
        grupo["label"] = formatar_label_periodo(grupo["periodo"], "Trimestre")

    else:
        grupo = df_plot.groupby(df_plot["data"].dt.date, as_index=False)["valor_vendido"].sum()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = pd.to_datetime(grupo["periodo"])
        grupo["label"] = grupo["ordem"].dt.strftime("%d/%m/%Y")

    return grupo.sort_values("ordem")


def agregar_clientes(df_base, granularidade):
    df_plot = df_base.copy()
    df_plot["data"] = pd.to_datetime(df_plot["data"], errors="coerce")
    df_plot = df_plot.dropna(subset=["data"])

    if granularidade == "Dia":
        grupo = df_plot.groupby(df_plot["data"].dt.date)["cliente"].nunique().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = pd.to_datetime(grupo["periodo"])
        grupo["label"] = grupo["ordem"].dt.strftime("%d/%m/%Y")

    elif granularidade == "Semana":
        grupo = df_plot.groupby(df_plot["data"].dt.to_period("W-MON"))["cliente"].nunique().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = grupo["periodo"].dt.start_time
        grupo["label"] = formatar_label_periodo(grupo["periodo"], "Semana")

    elif granularidade == "Mês":
        grupo = df_plot.groupby(df_plot["data"].dt.to_period("M"))["cliente"].nunique().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = grupo["periodo"].dt.start_time
        grupo["label"] = formatar_label_periodo(grupo["periodo"], "Mês")

    elif granularidade == "Trimestre":
        grupo = df_plot.groupby(df_plot["data"].dt.to_period("Q"))["cliente"].nunique().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = grupo["periodo"].dt.start_time
        grupo["label"] = formatar_label_periodo(grupo["periodo"], "Trimestre")

    else:
        grupo = df_plot.groupby(df_plot["data"].dt.date)["cliente"].nunique().reset_index()
        grupo.columns = ["periodo", "valor"]
        grupo["ordem"] = pd.to_datetime(grupo["periodo"])
        grupo["label"] = grupo["ordem"].dt.strftime("%d/%m/%Y")

    return grupo.sort_values("ordem")


def deslocar_periodo_ano_anterior(data_inicio, data_fim):
    try:
        return data_inicio.replace(year=data_inicio.year - 1), data_fim.replace(year=data_fim.year - 1)
    except ValueError:
        return (
            (pd.Timestamp(data_inicio) - pd.DateOffset(years=1)).date(),
            (pd.Timestamp(data_fim) - pd.DateOffset(years=1)).date()
        )


def agregar_comparativo_ano_anterior(df_atual, df_anterior, granularidade, tipo):
    if tipo == "Valor Vendido":
        atual = agregar_vendas(df_atual, granularidade).copy()
        anterior = agregar_vendas(df_anterior, granularidade).copy()
    else:
        atual = agregar_clientes(df_atual, granularidade).copy()
        anterior = agregar_clientes(df_anterior, granularidade).copy()

    if atual.empty or anterior.empty:
        return pd.DataFrame()

    if granularidade == "Dia":
        atual["chave"] = atual["ordem"].dt.strftime("%m-%d")
        anterior["chave"] = anterior["ordem"].dt.strftime("%m-%d")
        atual["label_cmp"] = atual["ordem"].dt.strftime("%d/%m")
        anterior["label_cmp"] = anterior["ordem"].dt.strftime("%d/%m")

    elif granularidade == "Semana":
        atual["chave"] = atual["ordem"].dt.strftime("%U")
        anterior["chave"] = anterior["ordem"].dt.strftime("%U")
        atual["label_cmp"] = atual["label"]
        anterior["label_cmp"] = anterior["label"]

    elif granularidade == "Mês":
        mapa_meses = {
            1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
            7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
        }

        atual["num_mes"] = atual["ordem"].dt.month
        anterior["num_mes"] = anterior["ordem"].dt.month

        atual["chave"] = atual["num_mes"].astype(str).str.zfill(2)
        anterior["chave"] = anterior["num_mes"].astype(str).str.zfill(2)

        atual["label_cmp"] = atual["num_mes"].map(mapa_meses)
        anterior["label_cmp"] = anterior["num_mes"].map(mapa_meses)

    elif granularidade == "Trimestre":
        atual["chave"] = atual["ordem"].dt.quarter.astype(str)
        anterior["chave"] = anterior["ordem"].dt.quarter.astype(str)
        atual["label_cmp"] = "T" + atual["ordem"].dt.quarter.astype(str)
        anterior["label_cmp"] = "T" + anterior["ordem"].dt.quarter.astype(str)

    else:
        atual["chave"] = atual["ordem"].dt.strftime("%m-%d")
        anterior["chave"] = anterior["ordem"].dt.strftime("%m-%d")
        atual["label_cmp"] = atual["ordem"].dt.strftime("%d/%m")
        anterior["label_cmp"] = anterior["ordem"].dt.strftime("%d/%m")

    atual = atual[["chave", "label_cmp", "valor"]].rename(columns={"valor": "atual"})
    anterior = anterior[["chave", "label_cmp", "valor"]].rename(columns={"valor": "anterior"})

    comp = pd.merge(atual, anterior, on="chave", how="outer", suffixes=("_atual", "_anterior"))
    comp["label"] = comp["label_cmp_atual"].combine_first(comp["label_cmp_anterior"])
    comp = comp.sort_values("chave")

    return comp[["chave", "label", "atual", "anterior"]]


def criar_grafico_diario_vendas(graf_df, granularidade):
    titulo = "Diário de vendas" if granularidade == "Dia" else f"Vendas por {granularidade.lower()}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=graf_df["label"],
        y=graf_df["valor"],
        mode="lines+markers+text",
        name="Valor vendido",
        text=[format_pt_sem_centimos(v) for v in graf_df["valor"]],
        textposition="top center",
        line=dict(width=3, color="#1f77b4"),
        marker=dict(size=8, color="#1f77b4"),
        hovertemplate="<b>%{x}</b><br>Valor: €%{y:,.2f}<extra></extra>"
    ))

    fig.update_layout(
        title=titulo,
        xaxis_title="Período",
        yaxis_title="Valor Vendido",
        hovermode="x unified"
    )
    return fig


def criar_grafico_diario_clientes(graf_df, granularidade):
    titulo = "Diário de clientes movimentados" if granularidade == "Dia" else f"Clientes movimentados por {granularidade.lower()}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=graf_df["label"],
        y=graf_df["valor"],
        mode="lines+markers+text",
        name="Clientes movimentados",
        text=[f"{int(round(v, 0))}" for v in graf_df["valor"]],
        textposition="top center",
        line=dict(width=3, color="#2ca02c"),
        marker=dict(size=8, color="#2ca02c"),
        hovertemplate="<b>%{x}</b><br>Clientes: %{y:,.0f}<extra></extra>"
    ))

    fig.update_layout(
        title=titulo,
        xaxis_title="Período",
        yaxis_title="Clientes",
        hovermode="x unified"
    )
    return fig


def criar_grafico_comparativo(comp_df, tipo, granularidade, ano_atual, ano_anterior):
    if comp_df.empty:
        return None

    nome_y = "Valor Vendido" if tipo == "Valor Vendido" else "Clientes"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=comp_df["label"],
        y=comp_df["atual"],
        mode="lines+markers",
        name=str(ano_atual),
        line=dict(width=3, color="#1f77b4"),
        marker=dict(size=7, color="#1f77b4"),
        hovertemplate=(f"<b>%{{x}}</b><br>{ano_atual}: €%{{y:,.2f}}<extra></extra>"
                       if tipo == "Valor Vendido"
                       else f"<b>%{{x}}</b><br>{ano_atual}: %{{y:,.0f}}<extra></extra>")
    ))

    fig.add_trace(go.Scatter(
        x=comp_df["label"],
        y=comp_df["anterior"],
        mode="lines+markers",
        name=str(ano_anterior),
        line=dict(width=2, dash="dash", color="#ff7f0e"),
        marker=dict(size=6, color="#ff7f0e"),
        hovertemplate=(f"<b>%{{x}}</b><br>{ano_anterior}: €%{{y:,.2f}}<extra></extra>"
                       if tipo == "Valor Vendido"
                       else f"<b>%{{x}}</b><br>{ano_anterior}: %{{y:,.0f}}<extra></extra>")
    ))

    fig.update_layout(
        title=f"Comparação visual com ano anterior por {granularidade.lower()}",
        xaxis_title="Período comparável",
        yaxis_title=nome_y,
        hovermode="x unified",
        legend_title="Ano"
    )

    if granularidade == "Mês":
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                           "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        )

    return fig


def obter_top_clientes_com_vendedor_principal(df_filt, top_n=15):
    base = (
        df_filt.groupby(["cliente", "vendedor"], as_index=False)["valor_vendido"]
        .sum()
        .sort_values(["cliente", "valor_vendido"], ascending=[True, False])
    )

    principal = base.drop_duplicates(subset=["cliente"], keep="first").copy()
    totais = df_filt.groupby("cliente", as_index=False)["valor_vendido"].sum()
    result = totais.merge(principal[["cliente", "vendedor"]], on="cliente", how="left")
    result = result.sort_values("valor_vendido", ascending=False).head(top_n)
    return result


def main():
    st.title("📊 ABA-SALES Dashboard")
    st.sidebar.header("🗃️ Carregar ficheiros")

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

    uploaded = st.sidebar.file_uploader("📁 Upload manual:", type="csv", accept_multiple_files=True)

    if uploaded:
        dfs = []
        for f in uploaded:
            try:
                f.seek(0)
            except Exception:
                pass
            df_temp = processar_csv(f, f.name)
            if not df_temp.empty:
                dfs.append(df_temp)

        df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

        if not df.empty:
            st.session_state.update(
                df=df,
                arquivos=[f.name for f in uploaded],
                datas_upload={}
            )
            st.sidebar.success(f"✅ {len(uploaded)} | {len(df):,} linhas")
            st.rerun()
        else:
            st.error("❌ Sem dados")

    if "df" not in st.session_state:
        st.info("👈 Carregue os dados")
        st.stop()

    df = st.session_state.df.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    datas_upload = st.session_state.get("datas_upload", {})

    if datas_upload:
        ultima_data = max([d for d in datas_upload.values() if d is not None], default=None)
        if ultima_data:
            st.info(f"📅 Ficheiro atualizado a {ultima_data.strftime('%d/%m/%Y %H:%M')} (hora PT)")
        else:
            st.warning("⚠️ Ficheiros sem data de atualização válida.")
    else:
        st.info("📅 Nenhum ficheiro carregado do GitHub.")

    st.sidebar.header("🎚️ Filtros")

    modo_filtro = st.sidebar.radio("📅 Modo de filtro:", ["Períodos", "Calendário"], index=0)
    data_inicio, data_fim = None, None

    if modo_filtro == "Períodos":
        periodo = st.sidebar.selectbox(
            "Períodos de análise",
            ["Esta semana", "Este mês", "Este ano", "Semana passada", "Mês passado", "Ano passado"]
        )
        data_inicio, data_fim = get_date_range(periodo)
        if data_inicio and data_fim:
            st.sidebar.info(f"📊 {periodo}: {data_inicio.strftime('%d/%m')} → {data_fim.strftime('%d/%m')}")
    else:
        hoje = now_pt()
        ontem = hoje - timedelta(days=1)
        inicio_mes = hoje.replace(day=1)
        date_range = st.sidebar.date_input("📅 Escolha um intervalo", (inicio_mes.date(), ontem.date()))
        if len(date_range) == 2:
            data_inicio, data_fim = date_range[0], date_range[1]

    granularidade = st.sidebar.selectbox(
        "🗓️ Agrupar gráficos por",
        ["Dia", "Semana", "Mês", "Trimestre"],
        index=0
    )

    tipo = st.sidebar.selectbox("📊 Gráfico", ["Valor Vendido", "Clientes movimentados"])

    comparar_ano_anterior = st.sidebar.checkbox("📉 Comparar com ano anterior", value=False)

    df_filt = df.copy()

    if data_inicio and data_fim:
        df_filt = df_filt[
            (df_filt["data"].dt.date >= data_inicio) &
            (df_filt["data"].dt.date <= data_fim)
        ]

    vendedores_unicos = sorted(df_filt["vendedor"].dropna().unique())
    pre_vend = ["VT", "OC", "DB", "HR", "AB", "FL"]
    vendedor = st.sidebar.multiselect(
        "🦸 Vendedor",
        options=vendedores_unicos,
        default=[v for v in pre_vend if v in vendedores_unicos]
    )

    docs_unicos = sorted(df_filt["documento"].dropna().unique())
    pre_docs = ["FT", "FTP", "NC", "NFI"]
    doc_filter = st.sidebar.multiselect(
        "📄 Documento",
        options=docs_unicos,
        default=[d for d in pre_docs if d in docs_unicos]
    )

    familia = st.sidebar.multiselect(
        "Ⓜ️ Família",
        sorted(df_filt["FAMILIA"].dropna().unique())
    )

    if vendedor:
        df_filt = df_filt[df_filt["vendedor"].isin(vendedor)]
    if doc_filter:
        df_filt = df_filt[df_filt["documento"].isin(doc_filter)]
    if familia:
        df_filt = df_filt[df_filt["FAMILIA"].isin(familia)]

    st.markdown("### 🏆 KPIs")
    cols = st.columns(5)

    total = df_filt["valor_vendido"].sum()
    cli = df_filt["cliente"].nunique()
    fam = df_filt["FAMILIA"].nunique()
    vend = df_filt["vendedor"].nunique()

    dias_com_venda = df_filt.groupby(df_filt["data"].dt.date)["valor_vendido"].count().gt(0).sum()
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

    tabs = st.tabs(["📈 Diário de vendas", "Ⓜ️ Família", "🦸 Vendedor", "👥 Cliente", "📊 Pivot"])

    with tabs[0]:
        if df_filt.empty:
            st.warning("Sem dados para exibir no gráfico.")
        else:
            if tipo == "Valor Vendido":
                graf_df = agregar_vendas(df_filt, granularidade)
                fig = criar_grafico_diario_vendas(graf_df, granularidade)
            else:
                graf_df = agregar_clientes(df_filt, granularidade)
                fig = criar_grafico_diario_clientes(graf_df, granularidade)

            st.plotly_chart(fig, use_container_width=True)

            if comparar_ano_anterior and data_inicio and data_fim:
                inicio_ant, fim_ant = deslocar_periodo_ano_anterior(data_inicio, data_fim)

                df_base_comparacao = df.copy()

                if vendedor:
                    df_base_comparacao = df_base_comparacao[df_base_comparacao["vendedor"].isin(vendedor)]
                if doc_filter:
                    df_base_comparacao = df_base_comparacao[df_base_comparacao["documento"].isin(doc_filter)]
                if familia:
                    df_base_comparacao = df_base_comparacao[df_base_comparacao["FAMILIA"].isin(familia)]

                df_anterior = df_base_comparacao[
                    (df_base_comparacao["data"].dt.date >= inicio_ant) &
                    (df_base_comparacao["data"].dt.date <= fim_ant)
                ].copy()

                if df_anterior.empty:
                    st.info("Não há dados do ano anterior para este mesmo período.")
                else:
                    comp_df = agregar_comparativo_ano_anterior(df_filt, df_anterior, granularidade, tipo)

                    if comp_df.empty:
                        st.info("Não foi possível montar a comparação com o ano anterior.")
                    else:
                        fig_comp = criar_grafico_comparativo(
                            comp_df,
                            tipo,
                            granularidade,
                            data_inicio.year,
                            inicio_ant.year
                        )
                        st.plotly_chart(fig_comp, use_container_width=True)

    with tabs[1]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            dividir_familia_por_vendedor = st.checkbox(
                "Dividir Top Famílias por vendedor",
                value=False,
                key="chk_familia_vendedor"
            )

            if dividir_familia_por_vendedor:
                grup_fam_vend = (
                    df_filt.groupby(["FAMILIA", "vendedor"], as_index=False)["valor_vendido"]
                    .sum()
                )

                top_familias = (
                    grup_fam_vend.groupby("FAMILIA", as_index=False)["valor_vendido"]
                    .sum()
                    .nlargest(15, "valor_vendido")["FAMILIA"]
                    .tolist()
                )

                top = grup_fam_vend[grup_fam_vend["FAMILIA"].isin(top_familias)].copy()

                ordem_familias = (
                    top.groupby("FAMILIA")["valor_vendido"]
                    .sum()
                    .sort_values(ascending=False)
                    .index
                    .tolist()
                )

                fig = px.bar(
                    top,
                    x="FAMILIA",
                    y="valor_vendido",
                    color="vendedor",
                    title="Top Famílias por Vendedor",
                    category_orders={"FAMILIA": ordem_familias},
                    barmode="stack"
                )
            else:
                grup_fam = df_filt.groupby("FAMILIA", as_index=False)["valor_vendido"].sum()
                top = grup_fam.nlargest(15, "valor_vendido")
                fig = px.bar(
                    top,
                    x="FAMILIA",
                    y="valor_vendido",
                    title="Top Famílias"
                )

            st.plotly_chart(fig, use_container_width=True)

            grup_fam = df_filt.groupby("FAMILIA", as_index=False)["valor_vendido"].sum()
            fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_fam, "FAMILIA", "Participação por Família (100%)")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[2]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            grup_vend = df_filt.groupby("vendedor", as_index=False)["valor_vendido"].sum()
            top = grup_vend.nlargest(15, "valor_vendido")
            fig = px.bar(top, x="vendedor", y="valor_vendido", title="Top Vendedores")
            st.plotly_chart(fig, use_container_width=True)

            fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_vend, "vendedor", "Participação por Vendedor (100%)")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[3]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            colorir_clientes_por_vendedor = st.checkbox(
                "Colorir Top Clientes por vendedor",
                value=False,
                key="chk_cliente_vendedor"
            )

            if colorir_clientes_por_vendedor:
                top = obter_top_clientes_com_vendedor_principal(df_filt, top_n=15)
                fig = px.bar(
                    top,
                    x="cliente",
                    y="valor_vendido",
                    color="vendedor",
                    title="Top Clientes por Vendedor Associado"
                )
            else:
                grup_cli = df_filt.groupby("cliente", as_index=False)["valor_vendido"].sum()
                top = grup_cli.nlargest(15, "valor_vendido")
                fig = px.bar(
                    top,
                    x="cliente",
                    y="valor_vendido",
                    title="Top Clientes"
                )

            st.plotly_chart(fig, use_container_width=True)

            grup_cli = df_filt.groupby("cliente", as_index=False)["valor_vendido"].sum()
            fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_cli, "cliente", "Participação por Cliente (100%)")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[4]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            linha = st.selectbox("➖ Linhas", ["FAMILIA", "vendedor", "cliente"])
            colu = st.selectbox("➕ Colunas", ["vendedor", "Nenhuma", "FAMILIA"])

            func_label = st.selectbox("🔢 Agregador", ["Soma", "Média"])
            func_map = {"Soma": "sum", "Média": "mean"}
            func = func_map[func_label]

            if colu == "Nenhuma":
                pivot = df_filt.pivot_table(index=linha, values="valor_vendido", aggfunc=func)
            else:
                pivot = df_filt.pivot_table(index=linha, columns=colu, values="valor_vendido", aggfunc=func)

            st.dataframe(pivot.style.format(format_pt), use_container_width=True)

    csv = df_filt.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "💾 Exportar CSV",
        csv,
        f"vendas_{now_pt().strftime('%Y%m%d_%H%M')}.csv"
    )


if __name__ == "__main__":
    main()