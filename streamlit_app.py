import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime, timedelta
import os
from github import Github

# ... (todas as funções anteriores permanecem iguais até os tabs) ...

    with tabs[1]:
        # Agrupamento completo para pizza
        grup_fam = df_filt.groupby('FAMILIA').valor_vendido.sum().reset_index()
        # Top 15 para barras
        top = grup_fam.nlargest(15, 'valor_vendido')
        fig = px.bar(top, x='FAMILIA', y='valor_vendido', title="Top Famílias")
        st.plotly_chart(fig, use_container_width=True)

        # Gráfico de pizza SEM rótulos abaixo de 1%
        total_geral = grup_fam['valor_vendido'].sum()
        threshold = total_geral * 0.01  # 1%
        pie_data = grup_fam[grup_fam['valor_vendido'] >= threshold]
        
        fig_pie = px.pie(
            pie_data,
            names='FAMILIA',
            values='valor_vendido',
            title="Participação por Família (100%)"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[2]:
        grup_vend = df_filt.groupby('vendedor').valor_vendido.sum().reset_index()
        top = grup_vend.nlargest(15, 'valor_vendido')
        fig = px.bar(top, x='vendedor', y='valor_vendido', title="Top Vendedores")
        st.plotly_chart(fig, use_container_width=True)

        # Gráfico de pizza SEM rótulos abaixo de 1%
        total_geral = grup_vend['valor_vendido'].sum()
        threshold = total_geral * 0.01  # 1%
        pie_data = grup_vend[grup_vend['valor_vendido'] >= threshold]
        
        fig_pie = px.pie(
            pie_data,
            names='vendedor',
            values='valor_vendido',
            title="Participação por Vendedor (100%)"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[3]:
        grup_cli = df_filt.groupby('cliente').valor_vendido.sum().reset_index()
        top = grup_cli.nlargest(15, 'valor_vendido')
        fig = px.bar(top, x='cliente', y='valor_vendido', title="Top Clientes")
        st.plotly_chart(fig, use_container_width=True)

        # Gráfico de pizza SEM rótulos abaixo de 1%
        total_geral = grup_cli['valor_vendido'].sum()
        threshold = total_geral * 0.01  # 1%
        pie_data = grup_cli[grup_cli['valor_vendido'] >= threshold]
        
        fig_pie = px.pie(
            pie_data,
            names='cliente',
            values='valor_vendido',
            title="Participação por Cliente (100%)"
        )
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
