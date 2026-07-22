# Original interface QA record

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
