"""Streamlit controls for the formal reproducible experiment runner."""
from __future__ import annotations

import copy
import io
import tempfile
import uuid
from pathlib import Path

from v2.application.experiment import ExperimentService, load_example_config, load_research_config
from v2.ui.errors import public_error_message


STATUS_LABELS = (
    ("method_version", "方法版本"), ("actual_algorithm", "实际算法"),
    ("evidence_count", "证据数"), ("approved_mapping_count", "已审核映射数"),
    ("generation_mode", "生成模式"),
    ("independent_evaluation_completed", "独立评价完成"),
    ("closed_loop_validated", "闭环验证完成"),
)


def default_comment_column_index(columns: list[str]) -> int:
    for candidate in ('评论', '评论内容', '评价内容', '评论文本', 'content', 'comment', 'text', 'review'):
        for index, column in enumerate(columns):
            if column.strip().lower() == candidate:
                return index
    return 0


def _write_upload(root: Path, upload, stem: str) -> Path | None:
    if upload is None:
        return None
    suffix = Path(upload.name).suffix.lower()
    path = root / f"{stem}{suffix}"
    path.write_bytes(upload.getvalue())
    return path


def _show_status(st, result: dict) -> None:
    if result.get("generation_mode") == "test":
        st.warning("TEST / fake 模式：仅验证论文复现流程，不代表设计质量或论文结论。")
    elif result.get("run_status") == "paused":
        st.info("研究准备已停在图谱阶段；未调用文字模型，可下载归档进行人工映射审核。")
    st.dataframe([{"字段": label, "状态": str(result.get(key))} for key, label in STATUS_LABELS],
                 hide_index=True, width="stretch")


def render_experiment(st, repository, store, active_product: str = "") -> None:
    service = ExperimentService(repository, store)
    st.caption("clean → topics → requirements → mapping → graph → generation → evaluation → report；研究模式可先停在图谱阶段，不产生模型费用。")
    source_files = st.file_uploader("评论数据 CSV/XLSX（可多选）", type=["csv", "xlsx"], key="repro_source", accept_multiple_files=True)
    product = st.text_input("实验产品名", value=active_product, key="repro_product")
    algorithm = st.selectbox("主题算法", ["kmeans_tfidf", "bertopic"], key="repro_algorithm")
    mode = st.selectbox("运行模式", ["test", "research"], key="repro_mode",
                        format_func=lambda value: "测试（fake）" if value == "test" else "正式研究准备")
    if mode == "research":
        st.selectbox("真实文字模型（仅记录选择；网页准备阶段不会调用）", ["deepseek"], key="repro_provider")
        st.caption("网页仅准备到 graph 并导出人工审核材料。真实 A/B/C 生成请使用 CLI，并显式传入付费授权。")
    mapping = st.file_uploader("映射审核文件（可选）", type=["csv", "xlsx", "json"], key="repro_mapping")
    comment_column = None
    columns = []
    combined_frame = None
    if source_files:
        try:
            import pandas as pd
            frames = []
            for f in source_files:
                if f.name.lower().endswith('.xlsx'):
                    frames.append(pd.read_excel(io.BytesIO(f.getvalue())))
                else:
                    frames.append(pd.read_csv(io.BytesIO(f.getvalue()), encoding='utf-8-sig'))
            combined_frame = pd.concat(frames, ignore_index=True)
            columns = [str(column) for column in combined_frame.columns]
            st.caption(f'已上传 {len(source_files)} 个文件，共 {len(combined_frame)} 行。')
            comment_column = st.selectbox("评论内容列", columns, index=default_comment_column_index(columns), key="repro_comment_column") if columns else None
        except Exception as exc:
            st.error(public_error_message("无法读取评论文件", exc, guidance="请检查文件格式与表头后重试。"))
    source = source_files[0] if source_files else None
    if "v2_repro_request_id" not in st.session_state:
        st.session_state["v2_repro_request_id"] = uuid.uuid4().hex
    if st.button("新建实验请求", help="生成新的请求编号；相同请求编号的重复提交会返回原运行。"):
        st.session_state["v2_repro_request_id"] = uuid.uuid4().hex
        st.session_state.pop("v2_repro_result", None)
        st.session_state.pop("v2_repro_download", None)
        st.rerun()
    action_label = "准备研究材料（停在图谱）" if mode == "research" else "运行测试复现实验"
    if st.button(action_label, type="primary", disabled=not source_files or not product.strip() or not comment_column):
        try:
            with tempfile.TemporaryDirectory(prefix="v2-repro-input-") as temporary:
                root = Path(temporary)
                if combined_frame is not None:
                    input_path = root / "comments.csv"
                    combined_frame.to_csv(input_path, index=False, encoding='utf-8-sig')
                else:
                    input_path = _write_upload(root, source, "comments")
                config = copy.deepcopy(load_research_config() if mode == "research" else load_example_config())
                config["product_name"] = product.strip()
                config["cleaning"]["comment_column"] = comment_column
                config["topic"]["algorithm"] = algorithm
                result = service.run(config, input_path,
                                     mapping_review=_write_upload(root, mapping, "mapping_review"),
                                     request_id=st.session_state["v2_repro_request_id"],
                                     stop_after="graph" if mode == "research" else None)
            st.session_state["v2_repro_result"] = result
            st.session_state.pop("v2_repro_download", None)
            st.session_state["v2_active_product"] = product.strip()
            st.rerun()
        except Exception as exc:
            st.error(public_error_message("正式复现实验未完成", exc, guidance="请检查列选择、算法依赖和审核文件。"))
    result = st.session_state.get("v2_repro_result")
    if result and result.get("pipeline_run_id") and result.get("product") == product.strip():
        _show_status(st, result)
        if st.button("准备完整复现运行 ZIP"):
            try: st.session_state["v2_repro_download"] = (result["pipeline_run_id"], service.download(result["pipeline_run_id"]))
            except Exception as exc: st.error(public_error_message("归档暂不可下载", exc))
        prepared = st.session_state.get("v2_repro_download")
        if prepared and prepared[0] == result["pipeline_run_id"]:
            st.download_button("下载完整复现运行 ZIP", prepared[1],
                               file_name=f"paper-repro-{result['pipeline_run_id'][:8]}.zip", mime="application/zip")
    runs = repository.list_pipeline_runs(100, target_product=product.strip(), provider="research") if product.strip() else []
    repro_runs = [run for run in runs if run.model in ("paper-repro-v2.0", "paper-repro-v2.1")]
    if repro_runs:
        selected = st.selectbox("历史正式复现实验", repro_runs,
                                format_func=lambda run: f"{run.created_at} · {run.id[:8]}")
        if st.button("重新打开正式复现实验"):
            try:
                reopened = service.load(selected.id)
                st.session_state["v2_repro_result"] = {**reopened, "pipeline_run_id": selected.id}
                st.session_state.pop("v2_repro_download", None)
                st.session_state["v2_active_product"] = reopened["product"]
                st.rerun()
            except Exception as exc: st.error(public_error_message("历史实验无法打开", exc))
        review_upload = st.file_uploader("为该既存运行导入独立评价（生成评价子运行）",
                                         type=["csv", "xlsx", "json"], key="repro_child_reviews")
        if st.button("生成评价子运行", disabled=review_upload is None):
            try:
                with tempfile.TemporaryDirectory(prefix="v2-review-input-") as temporary:
                    review_path = _write_upload(Path(temporary), review_upload, "reviews")
                    child = service.rerun_with_reviews(selected.id, review_path)
                st.session_state["v2_repro_result"] = child
                st.session_state.pop("v2_repro_download", None)
                st.session_state["v2_active_product"] = child["product"]
                st.rerun()
            except Exception as exc:
                st.error(public_error_message("评价子运行未完成", exc,
                                               guidance="请使用父运行盲评模板中的 scheme_id，并检查评分范围。"))
        changes_upload = st.file_uploader("上传 V1 修改记录并生成 V2",
                                          type=["csv", "xlsx", "json"], key="repro_child_changes")
        if st.button("生成 V2 子运行", disabled=changes_upload is None):
            try:
                with tempfile.TemporaryDirectory(prefix="v2-changes-input-") as temporary:
                    changes_path = _write_upload(Path(temporary), changes_upload, "changes")
                    child = service.rerun_with_changes(selected.id, changes_path)
                st.session_state["v2_repro_result"] = child
                st.session_state.pop("v2_repro_download", None)
                st.session_state["v2_active_product"] = child["product"]
                st.rerun()
            except Exception as exc:
                st.error(public_error_message("V2 子运行未完成", exc,
                                               guidance="请使用父运行方案 ID 填写修改记录，并检查修改理由。"))
