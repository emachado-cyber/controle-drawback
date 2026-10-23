import streamlit as st
import pandas as pd
import pdfplumber
import re
import json
import os

st.set_page_config(page_title="Controle Drawback - Barbieri do Brasil", page_icon="📦", layout="wide")

DATA_FILE = "dados_drawback.json"

def carregar_dados():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"atos": [], "exportacoes": []}

def salvar_dados(dados):
    with open(DATA_FILE, "w") as f:
        json.dump(dados, f, indent=4)

if "db" not in st.session_state:
    st.session_state.db = carregar_dados()

def extrair_dados_ac(pdf_file, tipo_origem):
    texto = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() or ""
    
    num_ac = re.search(r'(\d{11})', texto)
    compra_kg = re.search(r'Quantidade:\s*([\d\.,]+)', texto)
    
    num_ac_val = num_ac.group(1) if num_ac else "AC_DESCONHECIDO"
    qtd_compra = float(compra_kg.group(1).replace('.', '').replace(',', '.')) if compra_kg else 0.0
    
    fator_perda = 0.07 if tipo_origem == "Importada (7%)" else 0.03
    saldo_util = qtd_compra * (1.0 - fator_perda)
    
    return {
        "numero_ac": num_ac_val,
        "origem": tipo_origem,
        "compra_kg": qtd_compra,
        "perda_aplicada": f"{fator_perda*100:.0f}%",
        "saldo_util_kg": saldo_util,
        "utilizado_kg": 0.0,
        "saldo_disponivel_kg": saldo_util,
        "status": "Ativo"
    }

def extrair_dados_due(pdf_file):
    texto = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() or ""
            
    num_due = re.search(r'DU-E\s*([\w\d-]+)', texto)
    peso_liquido = re.search(r'Peso líquido\s*KG\s*([\d\.,]+)', texto)
    
    due_val = num_due.group(1) if num_due else "DUE_DESCONHECIDA"
    peso_val = float(peso_liquido.group(1).replace('.', '').replace(',', '.')) if peso_liquido else 0.0
        
    return {"due": due_val, "peso_kg": peso_val}

st.title("📦 Sistema de Controle Automatizado de Drawback")
st.caption("Barbieri do Brasil Indústria e Comércio de Perfis Ltda.")
st.divider()

st.sidebar.header("📥 Importar Documento")
tipo_doc = st.sidebar.selectbox("Tipo de Documento:", ["Ato Concessório (AC)", "Declaração de Exportação (DU-E)"])

if tipo_doc == "Ato Concessório (AC)":
    origem_bobina = st.sidebar.radio("Origem da Bobina:", ["Importada (7%)", "Nacional (3%)"])

arquivo = st.sidebar.file_uploader("Selecione o ficheiro PDF", type=["pdf"])

if arquivo and st.sidebar.button("Processar e Carregar"):
    if tipo_doc == "Ato Concessório (AC)":
        dados_ac = extrair_dados_ac(arquivo, origem_bobina)
        st.session_state.db["atos"].append(dados_ac)
        salvar_dados(st.session_state.db)
        st.sidebar.success(f"Ato {dados_ac['numero_ac']} registado!")
    else:
        dados_due = extrair_dados_due(arquivo)
        st.session_state.db["exportacoes"].append(dados_due)
        salvar_dados(st.session_state.db)
        st.sidebar.success(f"DU-E {dados_due['due']} lida ({dados_due['peso_kg']:,.2f} KG)!")

atos_df = pd.DataFrame(st.session_state.db["atos"])

if not atos_df.empty:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Compras (KG)", f"{atos_df['compra_kg'].sum():,.2f}")
    col2.metric("Saldo Útil (KG)", f"{atos_df['saldo_util_kg'].sum():,.2f}")
    col3.metric("Total Exportado (KG)", f"{atos_df['utilizado_kg'].sum():,.2f}")
    col4.metric("Saldo Disponível (KG)", f"{atos_df['saldo_disponivel_kg'].sum():,.2f}")
    
    st.divider()
    st.subheader("📋 Resumo de Atos Concessórios")
    st.dataframe(atos_df.style.format({
        "compra_kg": "{:,.2f} kg",
        "saldo_util_kg": "{:,.2f} kg",
        "utilizado_kg": "{:,.2f} kg",
        "saldo_disponivel_kg": "{:,.2f} kg"
    }), use_container_width=True)

if not atos_df.empty and st.session_state.db["exportacoes"]:
    st.divider()
    st.subheader("⚡ Dar Baixa de Exportação (DU-E)")
    due_df = pd.DataFrame(st.session_state.db["exportacoes"])
    
    col_a, col_b = st.columns(2)
    with col_a:
        ac_sel = st.selectbox("Selecione o Ato Concessório:", atos_df["numero_ac"].unique())
    with col_b:
        due_sel = st.selectbox("Selecione a DU-E:", due_df["due"].unique())
        
    if st.button("Confirmar Baixa do Saldo"):
        peso_due = due_df[due_df["due"] == due_sel]["peso_kg"].values[0]
        for ac in st.session_state.db["atos"]:
            if ac["numero_ac"] == ac_sel:
                ac["utilizado_kg"] += peso_due
                ac["saldo_disponivel_kg"] = ac["saldo_util_kg"] - ac["utilizado_kg"]
                if ac["saldo_disponivel_kg"] <= 0:
                    ac["status"] = "Baixado"
        salvar_dados(st.session_state.db)
        st.success(f"Foram abatidos {peso_due:,.2f} KG do Ato {ac_sel}!")
        st.rerun()
