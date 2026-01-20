import streamlit as st
import pandas as pd
import json
from pathlib import Path

# ===================== CONFIG BÁSICA =====================
st.set_page_config(page_title="Painel de Bônus - Starcheck (T4)", layout="wide")
st.title("🚀 Painel de Bônus Trimestral - Starcheck")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# ===================== MAPA DE SUPERVISORAS =====================
# Peso relativo de PRODUÇÃO por cidade, somando ~0.20 (20%) por supervisora
SUPERVISORAS_CIDADES = {
    "SAMMYRA JISELE BRITO REIS": {"BACABAL": 0.10, "CODÓ": 0.10},
    "GEISE ALINE MACEDO DE MEDEIROS": {"BALSAS": 0.10, "PINHEIRO": 0.10},
    "CHRISTIANE SILVA GUIMARÃES": {"SÃO LUIS": 0.10, "CAXIAS": 0.10},
    "ELIVANDY CRUZ DA SILVA": {
        "BACABAL": 0.0333, "CODÓ": 0.0333, "BALSAS": 0.0333,
        "PINHEIRO": 0.0333, "SÃO LUIS": 0.0333, "CAXIAS": 0.0333
    }
}

# ===================== CARREGAMENTO ======================
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

try:
    PESOS = load_json(DATA_DIR / "pesos_starcheck.json")
    INDICADORES = load_json(DATA_DIR / "empresa_indicadores_starcheck.json")
except Exception as e:
    st.error(f"Erro ao carregar JSONs: {e}")
    st.stop()

MESES = ["TRIMESTRE", "JULHO", "AGOSTO", "SETEMBRO"]
filtro_mes = st.radio("📅 Selecione o mês:", MESES, horizontal=True)

def ler_planilha(mes: str) -> pd.DataFrame:
    return pd.read_excel(DATA_DIR / "RESUMO PARA PAINEL - STARCHECK.xlsx", sheet_name=mes)

def up(x):
    return "" if pd.isna(x) else str(x).strip().upper()

def texto_obs(valor):
    """Normaliza observação: esconde NaN/None/vazio."""
    if pd.isna(valor):
        return ""
    s = str(valor).strip()
    if s.lower() in ["none", "nan", ""]:
        return ""
    return s

def int_safe(x):
    try:
        return int(float(x))
    except Exception:
        return 0

# ===================== REGRAS (por mês) ==================
LIMITE_TOTAL = 7
LIMITE_GRAVES = 5

def pct_qualidade_vistoriador(erros_total: float, erros_graves: float) -> float:
    """
    Retorna fração 0.0, 0.5 ou 1.0 para o indicador 'Qualidade' do Vistoriador.
    - 1.0: <=7 totais e <=5 graves
    - 0.5: estoura apenas um dos limites
    - 0.0: estoura os dois limites
    """
    et = 0 if pd.isna(erros_total) else float(erros_total)
    eg = 0 if pd.isna(erros_graves) else float(erros_graves)
    total_ok = et <= LIMITE_TOTAL
    graves_ok = eg <= LIMITE_GRAVES
    if total_ok and graves_ok:
        return 1.0
    if (not total_ok and graves_ok) or (total_ok and not graves_ok):
        return 0.5
    return 0.0

def elegivel(valor_meta, obs):
    obs_u = up(obs)
    if pd.isna(valor_meta) or float(valor_meta) == 0:
        return False, "Sem elegibilidade no mês (tempo de casa / sem meta)"
    if "LICEN" in obs_u:
        return False, "Licença no mês"
    return True, ""

# ===================== CÁLCULO MENSAL ====================
def calcula_mes(df_mes: pd.DataFrame, nome_mes: str) -> pd.DataFrame:
    """Aplica as regras para UM mês e devolve colunas calculadas + 'perdeu_itens'."""
    ind_mes = INDICADORES[nome_mes]
    df = df_mes.copy()

    # normalizações auxiliares
    df["_FUNCAO_UP"] = df["FUNÇÃO"].apply(up)
    df["_CIDADE_UP"] = df["CIDADE"].apply(up)
    df["_NOME_UP"]   = df["NOME"].apply(up)

    def calcula_recebido(row):
        func = up(row["FUNÇÃO"])
        cidade = up(row["CIDADE"])
        nome  = up(row.get("NOME", ""))
        obs = row.get("OBSERVAÇÃO", "")
        valor_meta = row.get("VALOR MENSAL META", 0)

        ok, motivo = elegivel(valor_meta, obs)
        perdeu_itens = []  # lista textual do que não recebeu no mês

        if not ok:
            return pd.Series({
                "MES": nome_mes,
                "META": 0.0, "RECEBIDO": 0.0, "PERDA": 0.0, "%": 0.0,
                "_badge": motivo or "Inelegível",
                "_obs": texto_obs(obs),
                "perdeu_itens": perdeu_itens
            })

        # pega pesos da função
        metainfo = PESOS.get(func, {})
        total_func = float(metainfo.get("total", valor_meta if pd.notna(valor_meta) else 0))
        itens = metainfo.get("metas", {})

        recebido = 0.0
        perdas = 0.0

        for item, peso in itens.items():
            parcela = total_func * float(peso)

            # PRODUÇÃO
            if item.startswith("Produção"):
                func_up = func
                # Regra especial: supervisoras perdem somente pelas cidades sob sua responsabilidade
                if func_up == "SUPERVISOR" and nome in SUPERVISORAS_CIDADES:
                    cidades_resp = SUPERVISORAS_CIDADES[nome]
                    base_soma = sum(cidades_resp.values()) or 1.0
                    perda_total = 0.0
                    perdas_cidades = []
                    for cidade_resp, peso_cid in cidades_resp.items():
                        bateu = ind_mes["producao_por_cidade"].get(cidade_resp, True)
                        # parcela atribuída à cidade = parcela_total * (peso_da_cidade / soma_pesos)
                        parcela_cidade = parcela * (peso_cid / base_soma)
                        if not bateu:
                            perda_total += parcela_cidade
                            perdas_cidades.append(cidade_resp)
                    recebido += parcela - perda_total
                    perdas += perda_total
                    if perdas_cidades:
                        perdeu_itens.append("Produção – " + ", ".join(perdas_cidades))
                else:
                    # regra padrão: pela cidade do colaborador
                    bateu_prod = ind_mes["producao_por_cidade"].get(cidade, True)
                    if bateu_prod:
                        recebido += parcela
                    else:
                        perdas += parcela
                        perdeu_itens.append("Produção – " + cidade.title())
                continue

            # QUALIDADE
            if item == "Qualidade":
                if func == "VISTORIADOR":
                    et = int_safe(row.get("ERROS TOTAL", 0))
                    eg = int_safe(row.get("ERROS GG", 0))
                    frac = pct_qualidade_vistoriador(et, eg)

                    if frac == 1.0:
                        recebido += parcela
                        # mantemos a contagem apenas para transparência (não será exibida como 'não entregue')
                        perdeu_itens.append(f"Qualidade (100%) — erros: {et} | graves: {eg}")
                    elif frac == 0.5:
                        recebido += parcela * 0.5
                        perdas += parcela * 0.5
                        perdeu_itens.append(f"Qualidade (50%) — erros: {et} | graves: {eg}")
                    else:
                        perdas += parcela
                        perdeu_itens.append(f"Qualidade (0%) — erros: {et} | graves: {eg}")
                else:
                    if not ind_mes["qualidade"]:
                        perdas += parcela
                        perdeu_itens.append("Qualidade")
                    else:
                        recebido += parcela
                continue

            # LUCRATIVIDADE (ligada a Financeiro)
            if item == "Lucratividade":
                if ind_mes["financeiro"]:
                    recebido += parcela
                else:
                    perdas += parcela
                    perdeu_itens.append("Lucratividade")
                continue

            # Demais itens: todos batidos conforme os seus resumos
            recebido += parcela

        meta = total_func
        perc = 0.0 if meta == 0 else (recebido / meta) * 100.0

        return pd.Series({
            "MES": nome_mes,
            "META": meta,
            "RECEBIDO": recebido,
            "PERDA": perdas,
            "%": perc,
            "_badge": "",
            "_obs": texto_obs(obs),
            "perdeu_itens": perdeu_itens
        })

    calc = df.apply(calcula_recebido, axis=1)
    return pd.concat([df.reset_index(drop=True), calc], axis=1)

# ===================== LER DADOS (MÊS OU TRIMESTRE) =====================
if filtro_mes == "TRIMESTRE":
    try:
        df_j = ler_planilha("JULHO")
        df_a = ler_planilha("AGOSTO")
        df_s = ler_planilha("SETEMBRO")
        st.success("✅ Planilhas carregadas: JULHO, AGOSTO e SETEMBRO!")
    except Exception as e:
        st.error(f"Erro ao ler a planilha: {e}")
        st.stop()

    dados_j = calcula_mes(df_j, "JULHO")
    dados_a = calcula_mes(df_a, "AGOSTO")
    dados_s = calcula_mes(df_s, "SETEMBRO")

    dados_full = pd.concat([dados_j, dados_a, dados_s], ignore_index=True)

    # agrega por colaborador (soma meta/recebido/perda, % = recebido/meta)
    group_cols = ["CIDADE", "NOME", "FUNÇÃO", "DATA DE ADMISSÃO", "TEMPO DE CASA"]
    agg = (dados_full
           .groupby(group_cols, dropna=False)
           .agg({
               "META": "sum",
               "RECEBIDO": "sum",
               "PERDA": "sum",
               "_obs": lambda x: ", ".join(sorted({s for s in x if s})),
               "_badge": lambda x: " / ".join(sorted({s for s in x if s}))
            })
           .reset_index())

    agg["%"] = agg.apply(lambda r: 0.0 if r["META"] == 0 else (r["RECEBIDO"] / r["META"]) * 100.0, axis=1)

    # indicadores perdidos agregados por pessoa (rótulo inclui o MÊS)
    perdas_por_pessoa = (
        dados_full
        .assign(_lost=lambda d: d.apply(
            lambda r: [f"{it} ({r['MES']})" for it in r["perdeu_itens"]],
            axis=1))
        .groupby(group_cols, dropna=False)["_lost"]
        .sum()
        .apply(lambda L: ", ".join(sorted(set(L))))
        .reset_index()
        .rename(columns={"_lost": "INDICADORES_NAO_ENTREGUES"})
    )

    dados_calc = agg.merge(perdas_por_pessoa, on=group_cols, how="left")
    dados_calc["INDICADORES_NAO_ENTREGUES"] = dados_calc["INDICADORES_NAO_ENTREGUES"].fillna("")

else:
    try:
        df_mes = ler_planilha(filtro_mes)
        st.success(f"✅ Planilha carregada com sucesso ({filtro_mes})!")
    except Exception as e:
        st.error(f"Erro ao ler a planilha: {e}")
        st.stop()

    dados_calc = calcula_mes(df_mes, filtro_mes)
    # monta string simples com os itens perdidos no mês
    dados_calc["INDICADORES_NAO_ENTREGUES"] = dados_calc["perdeu_itens"].apply(
        lambda L: ", ".join(L) if isinstance(L, list) and L else ""
    )

# ===================== FILTROS DE TELA =====================
st.markdown("### 🔎 Filtros")

col1, col2, col3, col4 = st.columns(4)
with col1:
    filtro_nome = st.text_input("Buscar por nome (contém)", "")
with col2:
    funcoes_validas = [f for f in dados_calc["FUNÇÃO"].dropna().unique() if up(f) in PESOS.keys()]
    filtro_funcao = st.selectbox("Função", options=["Todas"] + sorted(funcoes_validas))
with col3:
    cidades = ["Todas"] + sorted(dados_calc["CIDADE"].dropna().unique())
    filtro_cidade = st.selectbox("Cidade", cidades)
with col4:
    tempos = ["Todos"] + sorted(dados_calc["TEMPO DE CASA"].dropna().unique())
    filtro_tempo = st.selectbox("Tempo de casa", tempos)

dados_view = dados_calc.copy()
if filtro_nome:
    dados_view = dados_view[dados_view["NOME"].str.contains(filtro_nome, case=False, na=False)]
if filtro_funcao != "Todas":
    dados_view = dados_view[dados_view["FUNÇÃO"] == filtro_funcao]
if filtro_cidade != "Todas":
    dados_view = dados_view[dados_view["CIDADE"] == filtro_cidade]
if filtro_tempo != "Todos":
    dados_view = dados_view[dados_view["TEMPO DE CASA"] == filtro_tempo]

# ===================== RESUMO GERAL =====================
st.markdown("### 📊 Resumo Geral")
colA, colB, colC = st.columns(3)
with colA:
    st.success(f"💰 **Total possível:** R$ {dados_view['META'].sum():,.2f}")
with colB:
    st.info(f"📈 **Recebido:** R$ {dados_view['RECEBIDO'].sum():,.2f}")
with colC:
    st.error(f"📉 **Deixou de ganhar:** R$ {dados_view['PERDA'].sum():,.2f}")

# ===================== CARDS =====================
st.markdown("### 👥 Colaboradores")
cols = st.columns(3)

# Ordenação (por % desc)
dados_view = dados_view.sort_values(by="%", ascending=False)

for idx, row in dados_view.iterrows():
    pct = float(row["%"])
    meta = float(row["META"])
    recebido = float(row["RECEBIDO"])
    perdido = float(row["PERDA"])
    badge = row.get("_badge", "")
    obs_txt = texto_obs(row.get("_obs", ""))
    perdidos_txt = texto_obs(row.get("INDICADORES_NAO_ENTREGUES", ""))

    is_vist = up(row["FUNÇÃO"]) == "VISTORIADOR"
    erros_total_card = int_safe(row.get("ERROS TOTAL", 0)) if is_vist else 0
    erros_gg_card = int_safe(row.get("ERROS GG", 0)) if is_vist else 0

    bg = "#f9f9f9" if not badge else "#eeeeee"

    with cols[idx % 3]:
        st.markdown(f"""
        <div style="border:1px solid #ccc;padding:16px;border-radius:12px;margin-bottom:12px;background:{bg}">
            <h4 style="margin:0">{str(row['NOME']).title()}</h4>
            <p style="margin:4px 0;"><strong>{row['FUNÇÃO']}</strong> — {row['CIDADE']}</p>
            <p style="margin:4px 0;">
                <strong>Meta {'Trimestral' if filtro_mes=='TRIMESTRE' else 'Mensal'}:</strong> R$ {meta:,.2f}<br>
                <strong>Recebido:</strong> R$ {recebido:,.2f}<br>
                <strong>Deixou de ganhar:</strong> R$ {perdido:,.2f}<br>
                <strong>Cumprimento:</strong> {pct:.1f}%
            </p>
            <div style="height: 10px; background: #ddd; border-radius: 5px; overflow: hidden;">
                <div style="width: {pct:.1f}%; background: black; height: 100%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if badge:
            st.markdown(
                f"<div style='margin-top:8px;padding:6px 10px;border-radius:999px;display:inline-block;background:#444;color:#fff;font-size:12px;'>{badge}</div>",
                unsafe_allow_html=True
            )
        if obs_txt:
            st.caption(f"Obs.: {obs_txt}")

        # Só mostra 'não entregues' se houver de fato perda (evita 100%)
        if perdidos_txt and "100%" not in perdidos_txt:
            st.caption(f"🔻 Indicadores não entregues: {perdidos_txt}")

        if is_vist:
            st.caption(f"🧪 Qualidade — erros totais: {erros_total_card} | graves/gravíssimos: {erros_gg_card}")