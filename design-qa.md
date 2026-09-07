# Original interface QA record

## 2026-09-05 — Paper evidence center

- New page preserves the existing dark console and 7-stage navigation; now 10 total navigation entries. No original-site theme/config change.
- Desktop: `docs/qa/v2-paper-1440x1000.png`; mobile: `docs/qa/v2-paper-390x844.png`. Measured document widths equal 1440 and 390 respectively. Native data grids retain the existing light-grid rendering; outer forms/download controls remain dark.
- Browser exercised local-only login, synthetic CSV upload, source form, deduplication (7→6), saved run, missing-human-evidence state, result switching and actual ZIP download; browser errors: 0.
- The downloaded ZIP passed all 33 contained-file SHA-256 checks. No real human scores or model accuracy were fabricated for UI acceptance.
- DOCX rendered to 4 A4 pages and checked page by page. Actual existing-input results and limitations are recorded in `docs/V2_PAPER_VALIDATION.md`.
- Verdict: local functional/responsive acceptance passed. Not deployed; real research claims remain subject to the evidence requirements in the validation report.

## 2026-07-27 — Visual-delivery plan QA

- Added a no-cost, deterministic pre-generation gate for all eight required V2 visual assets.
- The gate locks one canonical product identity and adds acceptance criteria for render variation, assembly plausibility, three-view geometry, CMF/presentation-board readability and usage-scene hand geometry.
- The Design and Prompt pages render the saved plan gate and its criteria without loading image bytes, so this addition does not weaken the two-second navigation rule.
- Automated evidence: `tests/v2/test_visual_quality.py` checks both a complete pass plan and an incomplete rejection plan; `tests/v2/test_generation.py` verifies the gate persists with a generated package.
- No paid provider request was made in this QA pass. Generated pixels remain pending an owner-confirmed paid final review and cannot be represented here as visually accepted.

## 2026-07-22 · V2 workflow hardening

- Desktop evidence: `docs/qa/v2-workflow-hardening-1440x1000.png`.
- Mobile evidence: `docs/qa/v2-workflow-hardening-390x844.png`.
- Viewports: 1440×1000 and 390×844; document width equaled viewport width at both sizes; browser console errors: 0.
- Live navigation timing: History → AI Images 129 ms; AI Images → History 69 ms on the local SQLite fixture. Large image bytes remain opt-in.
- Floating UI: `.v2-mascot` count 0; Streamlit Viewer/deploy badge count 0; no robot or bottom-right platform badge was visible. The theme also hides the status widget when Streamlit inserts it.
- Product workflow: native overview actions, explicit current-product selection, product-scoped progress/results/history, default one paid image, history filters/decisions/comparison/evidence, and restore-to-product assignment.
- Recovery: initialization failures show a sanitized checklist, retry and Streamlit management link without public-data fallback.
- Final result: passed locally. Production availability still depends on the deployed `V2_DATABASE_URL` credential.

**Source Visual Truth Path**
- `C:\Users\15854\.codex\generated_images\019f25ec-7980-7d52-9cef-9c4510c39bd7\ig_02a5390d07e37add016a48d53947908191b97c0469506411a2.png`

**Implementation Screenshot Path**
- `D:\智能体网站\output\ui-cloud-studio-desktop.png`
- `D:\智能体网站\output\ui-cloud-studio-mobile.png`

**Viewport**
- Desktop: 1440 x 1000
- Mobile: 390 x 900

**State**
- Initial app screen, sidebar visible on desktop and collapsed on mobile.

**Full-View Comparison Evidence**
- `D:\智能体网站\output\ui-cloud-studio-comparison.png`

**Focused Region Comparison Evidence**
- Focused review covered the hero/header, sidebar controls, knowledge overview metrics, next-action panel, tab row, and first import form in the full-view comparison. Separate focused crops were not needed because the relevant controls were legible in the desktop screenshot and the responsive structure was checked in the mobile screenshot.

**Findings**
- No actionable P0/P1/P2 issues remain.
- Fonts and typography: implemented hierarchy now matches the selected direction closely enough for Streamlit, with the oversized title wrap fixed.
- Spacing and layout rhythm: the app uses the same light control-panel structure, left sidebar, status pills, process chips, metric grid, and right action panel. Streamlit's native multipage sidebar and toolbar remain as expected product constraints.
- Colors and visual tokens: light blue, white, navy, cyan, and green status tones are consistent with the selected Cloud Knowledge Studio direction.
- Image quality and asset fidelity: the selected visual target does not require product imagery; no placeholder image assets were introduced.
- Copy and content: visible modules and controls preserve the existing app functionality, including the 11 legacy modules and the Aliyun/DashScope rendering entry.

**Patches Made Since Previous QA Pass**
- Reduced and prioritized the hero title styling so it no longer breaks a single character onto a new line.
- Increased form input and placeholder contrast so sidebar and main form fields are readable on the light theme.

**Implementation Checklist**
- Keep all existing data, import, generation, analysis, download, Supabase, and DashScope flows unchanged.
- Preserve the legacy module tabs.
- Push the visual update after tests pass.

**Follow-Up Polish**
- A future pass can replace Streamlit's native multipage navigation with a custom navigation shell if the app moves away from Streamlit defaults.

final result: passed

---

# V2 Design QA

## 2026-07-23 · Navigation, graph and background-image QA

- AI image calls now start in a process-local background job; the page returns immediately with queued/progress status instead of waiting for each provider poll. The regression test verifies job submission returns in under 0.2 seconds.
- AI Images, graph and design pages no longer preload artifact bytes. Image bytes remain behind the existing preview action; graph/design archives require explicit load.
- Every newly generated text package persists a requirement → function → structure snapshot. Historical runs without the snapshot receive a compatible read-only view from their saved demand and constraints.
- Navigation avoids the unneeded global workspace query outside the overview page. Local V2 regression suite: 107 passed.

## 2026-07-25 路 Semantic graph and responsive generation QA

- The requirement-function-structure graph removes duplicate requirement titles, preserves merged user evidence, and maps every requirement to a specific function and physical structure. Existing generic snapshots are rebuilt read-only when opened.
- Product-scoped run lists are shared across graph, design, prompt and image pages for 300 seconds and invalidated immediately after writes. This removes repeated list reads caused only by page-specific display limits.
- Confirming a design task now returns after creation and starts text generation in a background registry; image work begins only after the persisted text package is ready. Page navigation no longer waits for DeepSeek or DashScope network calls.
- Leaving the image page clears its explicit preview flag. Returning through normal navigation therefore never reloads large image bytes; the user explicitly chooses to load a preview again.
- The no-cost end-to-end acceptance run seeds four evidence-backed needs, persists a 达标 design package, verifies four distinct requirement/function/structure mappings, and verifies the complete eight-image delivery plan without calling the paid provider.
- Streamlit AppTest measures every navigation switch under two seconds in the local private-database journey; the background-job submission regression test enforces a sub-0.2-second return.

**Final result: PASSED**

## Visual source

- Reference: `C:/Users/15854/AppData/Local/Temp/codex-clipboard-90f8cae9-bd85-4a4b-acb9-16ca5ac484a4.png`
- Desktop capture: `docs/qa/v2-desktop-1440x1000.png`
- Mobile capture: `docs/qa/v2-mobile-390x844.png`

The reference and final desktop capture were reviewed together in one comparison pass.

## Desktop — 1440 × 1000

- Viewport reported `1440 × 1000`.
- Main client width and scroll width both reported `1130 px`; no horizontal overflow.
- Permanent left rail, top service pills, seven-stage process, four metric cards, action cards, results area, dark navy circuit background and bottom-right assistant all match the supplied visual direction.
- Top white Streamlit chrome was removed after browser inspection.
- Empty-state content remains intentionally visible until the approved migration is executed; migrated products, counts, history and images populate the same regions.

## Mobile — 390 × 844

- Viewport reported `390 × 844`.
- Main client width and scroll width both reported `380 px`; no page-level horizontal overflow.
- Metric and action cards stack to one column.
- Seven-stage rail remains horizontally scrollable without forcing page overflow.
- A sticky mobile navigation selector is present because Streamlit collapses the desktop sidebar at this breakpoint.
- Login, main content and bottom-right assistant remain readable without clipped primary controls.

## Functional visual checks

- Private login renders before any business-data connection.
- Correct login opens the private dashboard.
- All nine navigation pages render without Streamlit exceptions.
- Desktop and mobile navigation controls are synchronized.
- Service values are masked; no API key or password hash is rendered.
- Buttons use Streamlit Material icons; generated background, brand mark and assistant are real raster assets.

## Accepted data-dependent differences

- The reference contains populated products and generated images. The QA database is intentionally empty, so the final capture shows empty-state copy instead of fabricated records.
- After migration, real products, comments, requirements, historical runs, documents and image artifacts occupy the preserved overview and result regions.

---

# V2 Navigation, DashScope Key & Native Control QA — 2026-07-18

**Final result: PASSED**

## Evidence

- Desktop import controls: `docs/qa/v2-import-controls-1440x1000.png`
- Mobile DashScope key settings: `docs/qa/v2-key-settings-390x844.png`
- Desktop viewport: 1440 × 1000
- Mobile viewport: 390 × 844
- State: authenticated single-user V2 with local private SQLite QA data and no provider key.

## Performance checks

- Navigation progress counts now use one `workspace_snapshot()` connection/query instead of per-table queries.
- Workspace snapshot, product list, run list and same-run detail are reused for 30 seconds and invalidated after writes or logout.
- Runtime background, logo and mascot use WebP data URIs totaling 66,699 characters instead of roughly 5 MB of PNG base64 per rerun; source PNGs remain preserved.
- Warm local Chromium switch from overview to import completed in 832 ms. This is local interaction evidence; Supabase improvement is enforced separately by the single-query and cache tests.

## Visual and security checks

- Upload button computed style: blue `rgb(10, 86, 189)`, light text `rgb(238, 248, 255)`, cyan border `rgb(45, 169, 255)`; no white button remains.
- Password visibility, download, link, form submit, primary, secondary, disabled, code-copy and dropdown controls share the dark console palette with visible hover/focus treatment.
- DashScope shortcut is visible in the desktop sidebar. Settings shows only `V2_IMAGE_PROVIDER`, `V2_IMAGE_MODEL` and placeholder `V2_IMAGE_API_KEY`; no DeepSeek key prompt and no current key/password value appears.
- Desktop document width: client 1440 px / scroll 1440 px. Mobile: client 390 px / scroll 390 px. No page-level horizontal overflow.
- Fixed assistant is hidden below 560 px so it cannot cover the key action or other mobile controls.
- Browser console: 0 errors, 0 warnings for the final QA run.

---

# V2 Expander Header Dark Theme QA — 2026-07-22

**Deployment result: PASSED**

## Evidence

- Pre-fix production screenshot: `C:/Users/15854/AppData/Local/Temp/codex-clipboard-1faf7350-1603-41ac-b109-fd077845e97d.png`
- Affected control: Streamlit expander header, including the expanded “工业设计约束” panel.
- Production URL returned HTTP 200 after the update: `https://smart-pillbox-ri94raugwzuqchyjdh4tcu.streamlit.app/`

## Checks

- Expander summary now has an explicit dark `#081a38` background and light theme text.
- Hover uses `#0a2a54`; the open state keeps the same dark palette and gains a themed divider.
- Nested label text and disclosure icons inherit the dark-theme foreground color.
- The regression test covers default, hover and icon selectors so future Streamlit theme changes cannot silently restore a white header.
- Theme tests: 7 passed. Repository full suite: 169 passed. Original-site freeze: passed.

---

# V2 Demand Workflow Persistence QA — 2026-07-22

**Local journey result: PASSED**

## Evidence

- User-reported state-loss screen: `C:/Users/15854/AppData/Local/Temp/codex-clipboard-4fc2cbb5-f5e0-424e-8b23-4910a0e2eb3a.png`
- AppTest journey: enter product and requirement → switch to overview → return to demand → generate a zero-image run → open Design and Prompt pages.

## Checks

- Product name, requirement, eight industrial-design constraints, selected provider/model and image count are copied into a durable session draft whenever the input changes, then restored when the page remounts.
- A confirmed run is selected before the text or image call starts. If image generation fails, the saved design text and Prompt remain available as a partial run.
- The default paid delivery is eight distinct tasks: product render ×2, exploded view, detail view, orthographic three-view, design board and usage scene ×2. Every paid run still requires the existing explicit confirmation.
- Text inputs and textareas now use a high-contrast white caret on the dark canvas.


## 2026-09-06 · paper-repro-v2.0 本地验收

- 参考：已有深海军蓝V2控制台，保留布局、导航与私有服务边界。测试账号为本地SIM fixture，数据库与归档独立于用户数据。
- 桌面1440×1000：docs/qa/v2-repro-desktop-1440x1000.png；手机390×844：docs/qa/v2-repro-mobile-390x844.png；原站：docs/qa/original-repro-smoke-1440x1000.png。新截图单独命名，没有覆盖既有截图。
- 实际流程：登录 → 论文实验中心 → 上传510条评论（默认列为评论） → fake正式运行 → 重开既存运行 → 下载ZIP。91个归档文件逐一哈希校验通过。
- 状态显示：paper-repro-v2.0、KMeans+TF-IDF、500证据、0审核、fake、独立评价False、闭环False；legacy辅助工具单独标识。
- 浏览器复现历史重开后状态延迟；新增AppTest RED后补充立即rerun，浏览器和AppTest均验证通过。
- 手机先收起侧栏再查看结果，文档宽度390/视口390；桌面宽1440，无横向溢出。初次直接缩窄的侧栏展开截图保留为过程记录，不作为无遮挡验收图。
- 全屏及重点区域检查：输入、真实算法、警示、七项状态、下载/历史/回评入口可读；桌面与手机均保留现有风格。浏览器控制台错误0、警告0。
- 验证范围为本地隔离环境；生产登录、云数据库/Storage与付费图片服务没有调用或部署。完整测试和运行路径见 experiment/verification/DELIVERY.md。

## 2026-09-07 · paper-repro-v2.1 正式研究准备态

- V2 论文实验区新增 test 与 research 两种明确模式；research 显示 DeepSeek 真实 provider 选择，但网页唯一主操作为“准备研究材料（停在图谱）”。
- graph 准备完成后状态明确显示 paused，未调用文字模型；归档可下载供人工映射审核。页面没有真实生成按钮，因此本轮未产生收费调用。
- 同一页面请求编号重复提交复用原运行；“新建实验请求”生成新编号，避免同配置的新实验误开旧方案。
- paper-repro-v2.0 历史继续出现在正式实验历史中并可只读打开；v2.1 的 paused、failed 和 completed 记录均可重开或下载已有归档。
- 本次为逻辑与 AppTest 验收，未更新既有桌面/移动正式截图；生产服务、数据库、Storage、真实 DeepSeek 与部署均未调用。

### 本轮补充的实际浏览器验收

- 已在独立 SQLite/SIM 测试账号中完成：登录 → 上传510条评论 → 正式研究准备 → graph暂停 → 下载ZIP → 历史重开。下载归档62个文件哈希验证通过，含10个人工材料文件，500条有效评论，外部API调用0次。记录：`experiment/verification/browser_30c1aa61/download_verification.json`。
- 本轮新截图：`docs/qa/v2-preparation-desktop-1440x1000.png`、`docs/qa/v2-preparation-mobile-390x844.png`、`docs/qa/original-preparation-smoke-1440x1000.png`。原有v2.0截图保留。桌面检查了状态、归档和历史入口；移动截图证明表单与暂停提示可读，没有横向溢出，不能据此声称所有状态字段都在同一屏可见。
- 从展开桌面侧栏直接缩窄时，曾出现侧栏遮挡；重新进入移动布局后侧栏关闭。最后截图采用实际无遮挡状态。对已隐藏且位于视口外的收起按钮进行点击曾超时，该操作不计为通过；相关过程截图保留在浏览器验收目录。
- 原站首页实际渲染成功；浏览器控制台错误0、警告0。上述只验证本地隔离流程；真实DeepSeek、生产登录、云数据库、Storage与付费图片均未验证。启动的本轮专用服务在验收后停止。

## 2026-09-08 发布核验标识

- 登录页在原有隐私说明下显示公开研究方法版本paper-repro-v2.1，沿用现有caption样式，未改变布局、登录或数据库行为。
- tests.v2.test_research_release以AppTest验证版本可见且不初始化私有仓库；根部署依赖显式声明jsonschema/scipy/threadpoolctl。浏览器云端状态与推送commit另记在本次发布报告，不沿用上一轮截图冒充上线结果。
