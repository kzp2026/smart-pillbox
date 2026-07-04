from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.product_knowledge_base import ProductKnowledgeBase, normalize_database_url


st.set_page_config(page_title="产品管理", page_icon="🛠️", layout="wide")


st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 15% 10%, rgba(41, 121, 255, 0.12), transparent 26%),
            radial-gradient(circle at 90% 0%, rgba(0, 200, 190, 0.12), transparent 24%),
            linear-gradient(135deg, #f7fbff 0%, #eef6ff 44%, #f9fcff 100%);
        color: #0b1736;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(10, 27, 62, 0.96), rgba(22, 53, 94, 0.94));
    }
    section[data-testid="stSidebar"] * {
        color: #f7fbff !important;
    }
    div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stMetric"]) {
        border: 1px solid rgba(79, 139, 255, 0.18);
        border-radius: 14px;
        padding: 12px 16px;
        background: rgba(255, 255, 255, 0.76);
        box-shadow: 0 18px 50px rgba(31, 70, 130, 0.08);
    }
    div[data-testid="stDataFrame"], div[data-testid="stForm"] {
        border: 1px solid rgba(79, 139, 255, 0.18);
        border-radius: 14px;
        padding: 10px;
        background: rgba(255, 255, 255, 0.78);
        box-shadow: 0 18px 50px rgba(31, 70, 130, 0.08);
    }
    .stButton > button {
        border-radius: 10px;
        border: 1px solid rgba(46, 111, 255, 0.28);
        background: linear-gradient(135deg, #2764ff, #13b9d6);
        color: #ffffff;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value or "").strip()


def get_database_url() -> str:
    return get_secret("PRODUCT_KB_DATABASE_URL") or get_secret("DATABASE_URL") or normalize_database_url()


@st.cache_resource(show_spinner=False)
def get_kb(database_url: str, owner_id: str) -> ProductKnowledgeBase:
    kb = ProductKnowledgeBase(database_url=database_url, owner_id=owner_id)
    kb.initialize()
    return kb


st.title("产品管理")
st.caption("在这里修改知识库里的产品名称、品类和备注；删除会同时移除该产品下的评论批次、评论和需求证据。")

with st.sidebar:
    st.header("数据源")
    owner_id = st.text_input("私人库 ID", value="private", help="当前先给你个人使用；后期共享时可扩展为登录用户 ID。")
    database_url = get_database_url()
    storage_type = "Supabase/PostgreSQL" if database_url.startswith(("postgresql://", "postgres://")) else "本地 SQLite"
    st.metric("当前存储", storage_type)
    st.caption("线上部署时会读取 Streamlit Cloud Secrets 中的连接串。")

kb = get_kb(database_url, owner_id)
products = kb.list_products()

if not products:
    st.info("知识库还没有产品数据。请先回到主页面导入评论资产。")
    st.stop()

summary_cols = st.columns(3)
summary_cols[0].metric("产品数", len(products))
summary_cols[1].metric("评论数", sum(int(product.get("comment_count") or 0) for product in products))
summary_cols[2].metric("需求证据数", sum(int(product.get("requirement_count") or 0) for product in products))

table = pd.DataFrame(products).rename(
    columns={
        "id": "ID",
        "name": "产品名称",
        "category": "产品品类",
        "description": "备注",
        "comment_count": "评论数",
        "requirement_count": "需求证据数",
        "created_at": "创建时间",
        "updated_at": "更新时间",
    }
)
visible_columns = ["ID", "产品名称", "产品品类", "评论数", "需求证据数", "更新时间"]
st.dataframe(table[visible_columns], use_container_width=True, hide_index=True)

selected_label = st.selectbox(
    "选择要管理的产品",
    [f"{product['id']} · {product['name']}" for product in products],
)
selected_product_id = int(selected_label.split(" · ", 1)[0])
selected_product = next(product for product in products if int(product["id"]) == selected_product_id)

with st.form(f"edit_product_{selected_product_id}"):
    col_name, col_category = st.columns([1.2, 1])
    edited_name = col_name.text_input("产品名称", value=str(selected_product.get("name") or ""))
    edited_category = col_category.text_input("产品品类", value=str(selected_product.get("category") or ""))
    edited_description = st.text_area("备注", value=str(selected_product.get("description") or ""), height=96)
    submitted = st.form_submit_button("保存产品信息", use_container_width=True)

if submitted:
    try:
        if kb.update_product(selected_product_id, edited_name, edited_category, edited_description):
            st.cache_resource.clear()
            st.success("产品信息已保存。")
            st.rerun()
        else:
            st.error("未找到该产品，可能已被删除或不属于当前私人库 ID。")
    except ValueError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"保存失败：{exc}")

with st.expander("删除产品数据", expanded=False):
    st.warning("删除后会移除该产品、评论批次、评论和需求证据。已生成的设计记录不会自动删除。")
    confirm_text = st.text_input(f"如需删除，请输入产品名称：{selected_product['name']}")
    delete_disabled = confirm_text != selected_product["name"]
    if st.button("确认删除该产品", type="primary", disabled=delete_disabled, use_container_width=True):
        try:
            if kb.delete_product(selected_product_id):
                st.cache_resource.clear()
                st.success("产品及其评论资产已删除。")
                st.rerun()
            else:
                st.error("未找到该产品，可能已被删除或不属于当前私人库 ID。")
        except Exception as exc:
            st.error(f"删除失败：{exc}")
