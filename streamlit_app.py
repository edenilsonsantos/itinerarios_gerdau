import os
import time

import pandas as pd
import requests
import streamlit as st
import pydeck as pdk

# faz o importe de credenciais de .streamlit/secrets.toml



# =========================
# Config geral
# =========================
st.set_page_config(
    page_title="Pontos de Ônibus - Fretados",
    layout="wide",
)


st.title("🚌 Pontos de Ônibus (Fretados Gerdau)")
st.caption("Filtro por Cidade, Bairro e Sentido + mapa com pinos geográficos.")


# =========================
# Credenciais
# =========================

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))
TABLE_NAME = "pontos_de_onibus"
GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", os.getenv("GOOGLE_MAPS_API_KEY", ""))



# =========================
# Fetch Supabase
# =========================
@st.cache_data(ttl=300)
def fetch_all_rows():

    endpoint = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    params = {"select": "*"}

    r = requests.get(endpoint, headers=headers, params=params)
    r.raise_for_status()

    return pd.DataFrame(r.json())


# =========================
# Endereço
# =========================
def safe_str(x):
    return "" if x is None else str(x).strip()


def build_address(row):

    parts = [
        safe_str(row.get("rua")),
        safe_str(row.get("bairro")),
        safe_str(row.get("cidade")),
        "Brasil"
    ]

    return ", ".join([p for p in parts if p])


# =========================
# Geocoding
# =========================
@st.cache_data(ttl=86400)
def geocode_address(address, key):

    if not address:
        return None, None

    url = "https://maps.googleapis.com/maps/api/geocode/json"

    r = requests.get(url, params={"address": address, "key": key})
    data = r.json()

    if data["status"] == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]

    return None, None


def add_geocodes(df):

    df = df.copy()
    df["__address"] = df.apply(build_address, axis=1)

    lats, lons = [], []

    for addr in df["__address"]:
        lat, lon = geocode_address(addr, GOOGLE_MAPS_API_KEY)
        lats.append(lat)
        lons.append(lon)

    df["__lat"] = lats
    df["__lon"] = lons

    return df.dropna(subset=["__lat", "__lon"])


# =========================
# Dados
# =========================
df_all = fetch_all_rows()

if df_all.empty:
    st.stop()


# =========================
# SIDEBAR FILTROS
# =========================
st.sidebar.header("🔎 Filtros")

# Cidade
cidades = sorted(df_all["cidade"].dropna().unique())
cidade_sel = st.sidebar.selectbox("Cidade Origem (Onde você mora)", ["(todas)"] + cidades)

df_bairro = df_all if cidade_sel == "(todas)" else df_all[df_all["cidade"] == cidade_sel]



# =========================
# SENTIDO (IDA / VOLTA)
# =========================
cidade_label = cidade_sel if cidade_sel != "(todas)" else "cidade selecionada"

sentido_opts = [
    f"Saindo de {cidade_label}",
    f"Voltando para {cidade_label}",
]

sentido_sel = st.sidebar.radio("Sentido", sentido_opts, index=0)




# =========================
# FILTROS
# =========================

def filter_sentido(df):

    out = df.copy()

    # Sentido
    if "sentido" in out.columns:

        if sentido_sel.startswith("Saindo"):
            out = out[out["sentido"].str.lower().str.startswith("ida")]

        else:
            out = out[out["sentido"].str.lower().str.startswith("volta")]
    return out


def apply_filters(df):

    out = df.copy()

    if cidade_sel != "(todas)":
        out = out[out["cidade"] == cidade_sel]

    # Sentido
    if "sentido" in out.columns:

        if sentido_sel.startswith("Saindo"):
            out = out[out["sentido"].str.lower().str.startswith("ida")]

        else:
            out = out[out["sentido"].str.lower().str.startswith("volta")]

    if bairro_sel != "(todos)":
        out = out[out["bairro"] == bairro_sel]


    # selecionar apenas as colunas relevantes para exibição, deixar de fora ID, created_at, updated_at, e tambem nao mostrar as colunas em que a coluna toda está vazia
    out = out[["rua", "referencia", "bairro", "cidade", "sentido", "horario_1", "horario_2", "horario_3", "horario_reuniao", "codigo_linha", "linha"]]

    # if coluna reuniao estiver vazia, remover a coluna
    if out["horario_reuniao"].isna().all():
        out.drop(columns=["horario_reuniao"])

    if out["horario_2"].isna().all():
        out.drop(columns=["horario_2"])

    if out["horario_3"].isna().all():
        out.drop(columns=["horario_3"])


    out = out.reset_index(drop=True)

    return out

df_bairro = filter_sentido(df_bairro)

# Bairro
bairros = sorted(df_bairro["bairro"].dropna().unique())
bairro_sel = st.sidebar.selectbox("Bairro", ["(todos)"] + bairros)


consultar = st.sidebar.button("Consultar", type="primary")





# =========================
# EXECUÇÃO
# =========================

if consultar and cidade_sel != "(todas)":

    df_filtered = apply_filters(df_all)
    # df = df_filtered.copy()
    df = df_filtered.copy()
    df = df.reset_index(drop=True)
    # se a coluna tiver o nome "cidade" remova a coluna
    df = df.drop(columns=["cidade"], errors="ignore")

    st.subheader("📋 Resultado")
    st.table(df)
    # st.dataframe(df_filtered, use_container_width=True, height=400, hide_index=True)


    # Mostrar Mapa apenas com filtro de Bairro
    if bairro_sel != "(todos)":
        # Geocode
        with st.spinner("Geocodificando..."):
            df_geo = add_geocodes(df_filtered)

        if df_geo.empty:
            st.warning("Nenhum ponto geocodificado.")
            st.stop()

        # =========================
        # ICON LAYER
        # =========================
        icon_data = {
            "url": "https://cdn-icons-png.flaticon.com/512/3448/3448339.png",
            "width": 128,
            "height": 128,
            "anchorY": 128
        }

        df_geo["icon"] = [icon_data for _ in range(len(df_geo))]

        layer = pdk.Layer(
            "IconLayer",
            data=df_geo,
            get_icon="icon",
            get_position=["__lon", "__lat"],
            get_size=4,
            size_scale=8,
            size_min_pixels=10,
            size_max_pixels=40,
            pickable=True,
        )

        # =========================
        # VIEWPORT
        # =========================
        center_lat = df_geo["__lat"].mean()
        center_lon = df_geo["__lon"].mean()

        zoom = 14.5 if len(df_geo) > 3 else 15.5

        view_state = pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=zoom,
            pitch=0,
        )

        # =========================
        # MAPA CLARO
        # =========================
        st.subheader("🗺️ Mapa de Pontos")

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={"text": "{rua}\n{bairro}\n{cidade}\n{referencia}\nBrasil"},
                map_style="mapbox://styles/mapbox/light-v9",
            ),
            use_container_width=True,
        )
    
else:
    st.info("Selecione os filtros e clique em Consultar.")
