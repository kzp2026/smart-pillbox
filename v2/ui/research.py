from __future__ import annotations

import io
import json
import uuid
import zipfile

from scripts.upload_parsing import default_comment_column, read_upload_table
from v2.application.history import HistoryService
from v2.application.research import ResearchService
from v2.research.dataset import METADATA_FIELDS, PROVENANCE_FIELDS, prepare_dataset
from v2.research.report import annotation_template, review_template
from v2.ui.errors import public_error_message


PROVENANCE_LABELS = ('来源平台', '商品链接或商品 ID', '采集方式/工具版本', '采集日期',
                     '评论时间范围', '抽样方式与纳入/排除标准', '数据使用授权/公开来源说明', '匿名化人工复核说明')


def _runs(repository,product,*,research=False):
    from v2.application.runtime_state import VIEW_CACHE
    key=(str(repository.database_url),str(repository.owner_id),str(repository.schema),'paper-runs',product,research)
    def load():
        try:
            return repository.list_pipeline_runs(100,target_product=product,provider='research' if research else None,
                                                  exclude_provider=None if research else 'research')
        except TypeError:
            return [r for r in repository.list_pipeline_runs(200,target_product=product)
                    if (r.provider=='research')==research][:100]
    return VIEW_CACHE.get(key,load)


def _uploaded_rows(upload) -> list[dict]:
    if not upload: return []
    data = upload.getvalue()
    if len(data) > 10*1024*1024: raise ValueError('人工输入文件最大 10 MB。')
    frame = read_upload_table(upload.name,data)
    if len(frame)>100000: raise ValueError('人工输入条目超过 100000 行。')
    return frame.fillna('').to_dict('records')


def _prepare_form(st, repository, store, product):
    st.caption('先确认数据集，再运行实验。来源不明的数据可以做软件测试，但不能直接充当论文实证。')
    upload=st.file_uploader('上传论文评论数据',type=['csv','xlsx'],key='paper_upload',max_upload_size=50)
    source = None
    if upload:
        source = (upload.name,upload.getvalue())
    with st.expander('或从当前产品历史读取已上传文件'):
        runs=_runs(repository,product) if product.strip() else []
        source_runs=[r for r in runs if r.model=='legacy-pipeline']
        if source_runs:
            source_run=st.selectbox('评论导入批次',source_runs,format_func=lambda r:f'{r.created_at} · {r.id[:8]}')
            if st.button('读取该批次源文件'):
                artifacts=repository.list_artifacts_for_run(source_run.id)
                item=next((a for a in artifacts if a['kind']=='input'),None)
                if item:
                    st.session_state['paper_source']=(product,item['name'],store.read(item['storage_path']))
                else: st.warning('该批次没有可恢复的源文件。')
        else: st.caption('当前产品没有已归档的评论导入批次，可使用上方上传。')
    saved=st.session_state.get('paper_source')
    if source is None and saved and saved[0]==product: source=saved[1:]
    if source is None: return
    filename,data=source
    if len(data)>50*1024*1024:
        st.error('评论文件最大 50 MB。'); return
    frame=read_upload_table(filename,data)
    st.dataframe(frame.head(10),hide_index=True,use_container_width=True)
    columns=list(frame.columns)
    if not columns: st.error('文件没有列。'); return
    with st.form('paper_dataset_form'):
        selected=st.selectbox('论文评论内容列',columns,index=columns.index(default_comment_column(frame)))
        mappings={'comment':selected}
        for field,label in zip(METADATA_FIELDS,('评分','日期','版本','渠道')):
            choice=st.selectbox(f'{label}列（论文元数据，可不选）',['（不选）']+columns)
            if choice!='（不选）': mappings[field]=choice
        provenance={key:st.text_input(label,key='paper_provenance_'+key) for key,label in zip(PROVENANCE_FIELDS,PROVENANCE_LABELS)}
        min_length=st.number_input('最短评论长度',min_value=1,max_value=100,value=2)
        dedup=st.checkbox('去除清洗后完全重复的评论',value=True)
        st.caption('自动遮盖手机号/邮箱；不保留账号列。公开前仍须人工检查姓名、地址等信息。')
        if st.form_submit_button('准备并检查数据集'):
            dataset=prepare_dataset(frame,data,filename,mappings,provenance,int(min_length),dedup)
            st.session_state['paper_dataset']=dataset
            st.session_state['paper_dataset_product']=product
            st.session_state.pop('paper_result',None)
            st.success('数据集已准备；点击运行后才会持久保存为正式实验。')


def _schemes(st,repository,store,product):
    candidates=[r for r in _runs(repository,product)
                if r.provider!='research' and r.model!='legacy-pipeline'] if product.strip() else []
    selected=st.multiselect('关联待评价的设计方案（同一产品）',candidates,
                            format_func=lambda r:f'{r.created_at} · {r.id[:8]}')
    schemes=[]
    for run in selected:
        detail=HistoryService(repository,store).reopen(run.id)
        # Include immutable result and evidence, so ratings remain interpretable after later changes.
        schemes.append(dict(scheme_id=run.id,product=run.target_product,provider=run.provider,model=run.model,
                            result=detail.result,context=detail.context))
    return schemes


def _show_result(st,experiment,service):
    st.markdown('#### 本次论文证据检查')
    st.caption(f"运行 ID：{experiment['manifest']['run_id']} · 所属产品：{experiment['product']}")
    st.dataframe(experiment['readiness'],hide_index=True,use_container_width=True)
    choice=st.selectbox('查看实验结果',['数据集卡','关键词与主题','需求证据映射','算法对照','人工评价','复现与下载'],key='paper_result_section')
    analysis=experiment['analysis']
    if choice=='数据集卡':
        st.json(experiment['dataset']['card'])
        st.dataframe(experiment['dataset']['records'][:100],hide_index=True,use_container_width=True)
    elif choice=='关键词与主题':
        st.caption('当前为中文字符 n-gram TF-IDF + KMeans，不是 BERTopic；主题编号不等于人工标签。')
        st.json(analysis['methods'])
        st.dataframe(analysis['keywords'],hide_index=True,use_container_width=True)
        st.dataframe(analysis['topics'][:100],hide_index=True,use_container_width=True)
    elif choice=='需求证据映射':
        st.metric('规则命中评论覆盖率（非准确率）',f"{analysis['evidence_coverage']:.1%}")
        st.caption('下表为人工规则候选映射，每条保留评论 ID 与证据；没有命中不补造需求。')
        st.dataframe(analysis['mappings'][:200],hide_index=True,use_container_width=True)
    elif choice=='算法对照':
        st.dataframe(experiment['evaluation']['metrics'],hide_index=True,use_container_width=True)
        st.dataframe(experiment['evaluation']['confusion'],hide_index=True,use_container_width=True)
        for note in experiment['evaluation']['notes']: st.caption(note)
    elif choice=='人工评价':
        st.caption('真实评价按专家/用户分开汇总；评分 1–5，单人评分没有样本标准差。不沿用系统自检分。')
        st.dataframe(experiment['review_summary'],hide_index=True,use_container_width=True)
    else:
        st.json(experiment['manifest'])
        if st.button('复现此实验并保存新版本'):
            result=service.replay(experiment['manifest']['run_id'])
            st.session_state['paper_result']=result
            same=all(result['analysis'][k]==experiment['analysis'][k] for k in ('predictions','topics','mappings'))
            st.success('复现完成：预测、主题和证据映射一致。' if same else '复现完成，但结果发生变化，请对照依赖和源码摘要。')
        if st.button('准备论文报告与完整证据包'):
            archive=service.download(experiment['manifest']['run_id'])
            st.session_state['paper_download']=(experiment['manifest']['run_id'],archive)
        prepared=st.session_state.get('paper_download')
        if prepared and prepared[0]==experiment['manifest']['run_id']:
            st.download_button('下载完整证据包 ZIP',prepared[1],file_name=f"paper-{prepared[0][:8]}.zip",mime='application/zip')
            with zipfile.ZipFile(io.BytesIO(prepared[1])) as archive:
                for name in ('论文实验报告.docx','charts.png','comparison.csv','manifest.json'):
                    st.download_button(f'下载 {name}',archive.read(name),file_name=name)
    if not experiment['evaluation']['metrics']:
        st.info('未提供真实人工 test 标注：不能据此声称算法准确率或效果提升。')
    if not experiment['review_summary']:
        st.info('未提供真实专家/用户评价：当前仅支持系统流程与案例结果展示。')


def render_research(st,repository,store,active_product=''):
    st.markdown('### 论文实验中心')
    st.warning('软件测试通过不等于论文结论成立；系统不自动生成“专家高分”或保证论文可发表。')
    st.caption('流程：数据集卡 → 离线分析 → 独立人工标注 → 同集对照 → 真实评价 → 证据报告。无外部模型调用或付费。')
    with st.expander('正式论文复现实验（共享 CLI 核心）', expanded=True):
        from v2.ui.experiment import render_experiment
        render_experiment(st, repository, store, active_product)
    st.info('以下为 legacy 辅助标注与历史兼容工具；论文正式实验请使用上方共享 CLI 核心入口。旧分析记录不得与新的正式 run 混用。')
    product=st.text_input('论文实验产品名称',value=active_product,key='paper_product')
    service=ResearchService(repository,store)
    try:
        with st.expander('1 · 数据来源、字段与清洗',expanded='paper_dataset' not in st.session_state):
            _prepare_form(st,repository,store,product)
        dataset=st.session_state.get('paper_dataset')
        dataset_product=st.session_state.get('paper_dataset_product',product)
        if dataset and dataset_product==product:
            st.caption('清洗统计：'+json.dumps(dataset['card']['counts'],ensure_ascii=False))
            st.download_button('下载人工标注模板（不含算法预测）',annotation_template(dataset['records']),file_name='annotation_template.csv',mime='text/csv')
            with st.expander('2 · 分析参数与真实人工证据',expanded=True):
                first,second=st.columns(2)
                seed=first.number_input('随机种子',min_value=0,max_value=4294967295,value=42)
                n_topics=second.number_input('KMeans 主题数',min_value=1,max_value=30,value=6)
                snow=st.checkbox('同时运行 SnowNLP 预训练基线',value=False)
                st.caption('自动比较规则情感、加入否定规则的情感方法；需求比较完整规则与仅首命中消融。没有人工真值时仅输出预测。')
                st.markdown('**人工标签约定**：task 为 sentiment / requirement；label 为中文标签，多需求用 | 分隔。split 为 train/dev/test，只评价 test。')
                st.caption('情感：正面/中性/负面。需求：提醒反馈/安全可靠/操作便利/容量收纳/外观质感/价格服务/无明确需求。先盲标与仲裁，再导入一条最终真值。')
                gold=st.file_uploader('导入最终人工标注 CSV/XLSX',type=['csv','xlsx'],key='paper_gold',max_upload_size=10)
                external=st.file_uploader('导入候选算法预测（可选 CSV/XLSX）',type=['csv','xlsx'],key='paper_predictions',max_upload_size=10)
                st.caption('候选预测列：comment_id、task、method、prediction；必须覆盖对应任务所有 test ID。禁止把人工标签直接作为预测。')
                method_notes=st.text_area('候选算法复现说明（导入预测时必填）',help='写明模型/算法版本、参数、随机种子、Prompt 版本、训练数据范围和原运行标识。外部模型不会在此自动重跑。')
                schemes=_schemes(st,repository,store,product)
                if schemes: st.download_button('下载真实评价模板',review_template(schemes),file_name='review_template.csv',mime='text/csv')
                st.caption('评价量表：需求匹配度、操作便利性、结构合理性、创新性、工程可行性。1=明显不满足，3=基本满足，5=充分满足；仅接受整数 1–5。')
                reviews=st.file_uploader('导入专家/用户真实评分 CSV/XLSX',type=['csv','xlsx'],key='paper_reviews',max_upload_size=10)
                confirmed=st.checkbox('我确认标签/评分来自真实人工，test 未用于训练调参，评审者 ID 已匿名化',key='paper_human_confirmed')
                if st.button('运行并保存论文实验',type='primary',disabled=not product.strip()):
                    with st.spinner('正在本地分析、校验并生成证据报告……'):
                        experiment=service.run(product,dataset,dict(seed=int(seed),n_topics=int(n_topics),use_snownlp=snow),
                                               _uploaded_rows(gold),_uploaded_rows(reviews),schemes,confirmed,
                                               external_predictions=_uploaded_rows(external),method_notes=method_notes)
                    st.session_state['paper_result']=experiment
                    if st.session_state.get('v2_active_product') != product:
                        st.session_state.pop('v2_current_run_id',None)
                    st.session_state['v2_active_product']=product
                    from v2.application.runtime_state import VIEW_CACHE
                    VIEW_CACHE.invalidate()
                    st.success('论文实验已保存，缺失研究证据已在下方列出。')
        elif dataset: st.info('当前数据集属于其他产品，请为本产品重新准备数据，防止串用。')
        with st.expander('历史论文实验（当前产品）'):
            runs=_runs(repository,product,research=True) if product.strip() else []
            if runs:
                selected=st.selectbox('选择论文实验',runs,format_func=lambda r:f'{r.created_at} · {r.id[:8]} · {r.status.value}')
                if st.button('打开论文实验'):
                    st.session_state['paper_result']=service.load(selected.id)
            else: st.caption('尚无已保存的论文实验。')
        experiment=st.session_state.get('paper_result')
        if experiment and experiment['product']==product: _show_result(st,experiment,service)
    except (ValueError,KeyError) as exc:
        st.error(public_error_message('实验输入校验未通过',exc,guidance='请检查列名、标签、评分范围、重复 ID 与来源声明。'))
    except Exception as exc:
        st.error(public_error_message('论文实验暂未完成',exc,guidance='请确认 requirements.txt 依赖已安装，或从历史检查失败运行后重试。'))
