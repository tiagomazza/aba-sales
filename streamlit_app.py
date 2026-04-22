import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from github import Github

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


def processar_csv(conteudo, nome_arquivo=""):
    try:
        if isinstance(conteudo, bytes):
            content = conteudo.decode("latin1")
        else:
            content = conteudo.read().decode("latin1") if hasattr(conteudo, "read") else conteudo.decode("latin1")

        lines = content.split("\n")
        data_lines = [line for line in lines[1:] if line.strip() and not line.startswith("sep=")]
        csv_content = "\n".join(data_lines)

        df = pd.read_csv(
            io.StringIO(csv_content),
            sep=",",
            quotechar='"',
            encoding="latin1",
            on_bad_lines="skip",
            engine="python"
        )

        df.columns = df.columns.str.strip().str.replace('"', "", regex=False)

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
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce"
        )

        df["valor_vendido"] = df.apply(valor_liquido, axis=1)

        df_clean = df.dropna(subset=["data", "valor_vendido"]).copy()
        df_clean = df_clean[df_clean["venda_bruta"] > 0].copy()

        if "Motivo de anulação do documento" in df_clean.columns:
            anuladas = (
                df_clean["Motivo de anulação do documento"].notna() &
                (df_clean["Motivo de anulação do documento"].astype(str).str.strip() != "")
            )
            df_clean = df_clean[~anuladas].copy()

        df_clean["arquivo"] = nome_arquivo

        return df_clean[["data", "FAMILIA", "vendedor", "cliente", "documento", "valor_vendido", "arquivo"]]

    except Exception as e:
        st.error(f"Erro CSV: {e}")
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
            with open(os.path.join(pasta, nome), "rb") as f:
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

        except Exception as e:
            st.error(f"❌ Erro {nome}: {e}")

        progress_bar.progress((i + 1) / len(arquivos))

    progress_bar.empty()
    df_final = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return arquivos, df_final, datas_upload


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


def gerar_label_diario(df):
    df = df.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"])
    grupo = df.groupby(df["data"].dt.date, as_index=False)["valor_vendido"].sum()
    grupo.columns = ["periodo", "valor"]
    grupo["ordem"] = pd.to_datetime(grupo["periodo"])
    grupo["label"] = grupo["ordem"].dt.strftime("%d/%m/%Y")
    return grupo.sort_values("ordem")


def gerar_comparacao_ano_anterior(df_base, data_inicio, data_fim):
    df = df_base.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"])

    atual = df[(df["data"].dt.date >= data_inicio) & (df["data"].dt.date <= data_fim)].copy()
    if atual.empty:
        return pd.DataFrame(), pd.DataFrame(), False

    inicio_prev = data_inicio.replace(year=data_inicio.year - 1)
    fim_prev = data_fim.replace(year=data_fim.year - 1)

    anterior = df[(df["data"].dt.date >= inicio_prev) & (df["data"].dt.date <= fim_prev)].copy()
    if anterior.empty:
        return atual, pd.DataFrame(), False

    atual = atual.groupby(atual["data"].dt.strftime("%m-%d"), as_index=False)["valor_vendido"].sum()
    atual.columns = ["chave", "valor_atual"]

    anterior = anterior.groupby(anterior["data"].dt.strftime("%m-%d"), as_index=False)["valor_vendido"].sum()
    anterior.columns = ["chave", "valor_anterior"]

    base_datas = pd.date_range(start=pd.Timestamp(data_inicio), end=pd.Timestamp(data_fim), freq="D")
    base = pd.DataFrame({"data": base_datas})
    base["chave"] = base["data"].dt.strftime("%m-%d")
    base["label"] = base["data"].dt.strftime("%d/%m/%Y")

    base = base.merge(atual, on="chave", how="left").merge(anterior, on="chave", how="left")
    base["valor_atual"] = base["valor_atual"].fillna(0)
    base["valor_anterior"] = base["valor_anterior"].fillna(0)

    return base, anterior, True


def criar_pie_sem_rotulos_menores_1pc(grup_df, nome_categoria, titulo):
    import plotly.express as px
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
        insidetextorientation="radial",
        hovertemplate="<b>%{label}</b><br>Valor: €%{value:,.0f}<br>Percentual: %{percent:.1%}<extra></extra>"
    )
    return fig_pie


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
        periodo = st.sidebar.selectbox("Períodos de análise", ["Esta semana", "Este mês", "Este ano", "Semana passada", "Mês passado", "Ano passado"])
        data_inicio, data_fim = get_date_range(periodo)
    else:
        hoje = now_pt()
        ontem = hoje - timedelta(days=1)
        inicio_mes = hoje.replace(day=1)
        date_range = st.sidebar.date_input("📅 Escolha um intervalo", (inicio_mes.date(), ontem.date()))
        if len(date_range) == 2:
            data_inicio, data_fim = date_range[0], date_range[1]

    df_filt = df.copy()
    if data_inicio and data_fim:
        df_filt = df_filt[(df_filt["data"].dt.date >= data_inicio) & (df_filt["data"].dt.date <= data_fim)]

    vendedores_unicos = sorted(df_filt["vendedor"].dropna().unique())
    pre_vend = ["VT", "OC", "DB", "HR", "AB", "FL"]
    vendedor = st.sidebar.multiselect("🦸 Vendedor", options=vendedores_unicos, default=[v for v in pre_vend if v in vendedores_unicos])

    docs_unicos = sorted(df_filt["documento"].dropna().unique())
    pre_docs = ["FT", "FTP", "NC", "NFI"]
    doc_filter = st.sidebar.multiselect("📄 Documento", options=docs_unicos, default=[d for d in pre_docs if d in docs_unicos])

    familia = st.sidebar.multiselect("Ⓜ️ Família", sorted(df_filt["FAMILIA"].dropna().unique()))

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

    comparar_ano_anterior = st.checkbox("Comparar com o ano anterior", value=False)

    tabs = st.tabs(["📈 Diário de vendas", "Ⓜ️ Família", "🦸 Vendedor", "👥 Cliente", "📊 Pivot"])

    with tabs[0]:
        if df_filt.empty:
            st.warning("Sem dados para exibir no gráfico.")
        else:
            if comparar_ano_anterior and data_inicio and data_fim:
                base, _, disponivel = gerar_comparacao_ano_anterior(df_filt, data_inicio, data_fim)
                if disponivel and not base.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=base["label"],
                        y=base["valor_atual"],
                        mode="lines+markers+text",
                        name="Ano atual",
                        text=[f"€{format_pt(v)}" for v in base["valor_atual"]],
                        textposition="top center",
                        hovertemplate="Data: %{x}<br>Valor: €%{y:,.2f}<extra></extra>"
                    ))
                    fig.add_trace(go.Scatter(
                        x=base["label"],
                        y=base["valor_anterior"],
                        mode="lines+markers+text",
                        name="Ano anterior",
                        text=[f"€{format_pt(v)}" for v in base["valor_anterior"]],
                        textposition="top center",
                        hovertemplate="Data: %{x}<br>Valor: €%{y:,.2f}<extra></extra>"
                    ))
                    fig.update_layout(
                        title="Diário de vendas com comparação anual",
                        xaxis_title="Período",
                        yaxis_title="€",
                        hovermode="x unified"
                    )
                    fig.update_yaxes(tickprefix="€", separatethousands=True)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Não existem dados suficientes para comparar com o ano anterior.")
                    graf_df = gerar_label_diario(df_filt)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=graf_df["label"],
                        y=graf_df["valor"],
                        mode="lines+markers+text",
                        name="Vendas",
                        text=[f"€{format_pt(v)}" for v in graf_df["valor"]],
                        textposition="top center",
                        hovertemplate="Data: %{x}<br>Valor: €%{y:,.2f}<extra></extra>"
                    ))
                    fig.update_layout(title="Diário de vendas", xaxis_title="Período", yaxis_title="€", hovermode="x unified")
                    fig.update_yaxes(tickprefix="€", separatethousands=True)
                    st.plotly_chart(fig, use_container_width=True)
            else:
                graf_df = gerar_label_diario(df_filt)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=graf_df["label"],
                    y=graf_df["valor"],
                    mode="lines+markers+text",
                    name="Vendas",
                    text=[f"€{format_pt(v)}" for v in graf_df["valor"]],
                    textposition="top center",
                    hovertemplate="Data: %{x}<br>Valor: €%{y:,.2f}<extra></extra>"
                ))
                fig.update_layout(title="Diário de vendas", xaxis_title="Período", yaxis_title="€", hovermode="x unified")
                fig.update_yaxes(tickprefix="€", separatethousands=True)
                st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            grup_fam = df_filt.groupby("FAMILIA", as_index=False)["valor_vendido"].sum()
            top = grup_fam.nlargest(15, "valor_vendido")
            import plotly.express as px
            fig = px.bar(top, x="FAMILIA", y="valor_vendido", title="Top Famílias")
            st.plotly_chart(fig, use_container_width=True)
            fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_fam, "FAMILIA", "Participação por Família (100%)")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[2]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            grup_vend = df_filt.groupby("vendedor", as_index=False)["valor_vendido"].sum()
            top = grup_vend.nlargest(15, "valor_vendido")
            import plotly.express as px
            fig = px.bar(top, x="vendedor", y="valor_vendido", title="Top Vendedores")
            st.plotly_chart(fig, use_container_width=True)
            fig_pie = criar_pie_sem_rotulos_menores_1pc(grup_vend, "vendedor", "Participação por Vendedor (100%)")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[3]:
        if df_filt.empty:
            st.warning("Sem dados para exibir.")
        else:
            grup_cli = df_filt.groupby("cliente", as_index=False)["valor_vendido"].sum()
            top = grup_cli.nlargest(15, "valor_vendido")
            import plotly.express as px
            fig = px.bar(top, x="cliente", y="valor_vendido", title="Top Clientes")
            st.plotly_chart(fig, use_container_width=True)
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