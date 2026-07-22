from __future__ import annotations

import base64
import html
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Mapping


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"


def asset_data_uri(path: str | Path) -> str:
    asset = Path(path)
    mime = "image/webp" if asset.suffix.lower() == ".webp" else (
        mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
    )
    encoded = base64.b64encode(asset.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@lru_cache(maxsize=1)
def default_asset_urls() -> dict[str, str]:
    return {
        "background": asset_data_uri(ASSET_DIR / "studio-background.webp"),
        "logo": asset_data_uri(ASSET_DIR / "ai-brand-mark.webp"),
    }


def build_theme_css(asset_urls: Mapping[str, str]) -> str:
    background = html.escape(asset_urls["background"], quote=True)
    logo = html.escape(asset_urls["logo"], quote=True)
    return f"""
<style>
:root {{
  --v2-ink: #030817;
  --v2-surface: rgba(5, 17, 40, 0.92);
  --v2-panel: rgba(7, 24, 52, 0.88);
  --v2-line: rgba(67, 139, 229, 0.25);
  --v2-line-strong: rgba(36, 215, 223, 0.52);
  --v2-blue: #168bff;
  --v2-cyan: #24d7df;
  --v2-violet: #8b5cf6;
  --v2-green: #31d98b;
  --v2-amber: #f4a340;
  --v2-text: #eef7ff;
  --v2-muted: #8da5c2;
  --v2-danger: #ff6b81;
  --v2-radius: 14px;
}}

html {{ color-scheme: dark; }}

html, body, [class*="css"] {{
  font-family: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
}}

.stApp {{
  color: var(--v2-text);
  background-color: var(--v2-ink);
  background-image: url("{background}");
  background-repeat: no-repeat;
  background-position: center top;
  background-size: cover;
  background-attachment: fixed;
}}

[data-testid="stHeader"] {{
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  background: transparent !important;
}}

[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stViewerBadge"],
[data-testid="stAppDeployButton"],
[data-testid="manage-app-button"],
[data-testid="stMainMenu"],
[data-testid="stToolbarActions"],
[class*="viewerBadge"],
[class*="ViewerBadge"],
[class*="deployButton"],
[class*="DeployButton"],
iframe[title="streamlit_status"],
#MainMenu,
footer {{
  display: none !important;
  visibility: hidden !important;
  width: 0 !important;
  height: 0 !important;
  overflow: hidden !important;
}}

[data-testid="stAppViewContainer"] > .main {{
  background: rgba(3, 8, 23, 0.58);
}}

[data-testid="stMainBlockContainer"] {{
  max-width: 1760px;
  padding: 1.25rem 1.5rem 4.5rem;
}}

[data-testid="stSidebar"] {{
  width: 288px;
  min-width: 288px;
  background: rgba(3, 13, 31, 0.97);
  border-right: 1px solid var(--v2-line);
}}

[data-testid="stSidebarContent"] {{
  padding: 1rem 0.85rem 1.5rem;
}}

[data-testid="stSidebarCollapsedControl"] {{
  color: var(--v2-cyan);
  background: #081a38;
  border: 1px solid var(--v2-line);
}}

.st-key-v2_mobile_nav {{ display: none; }}

h1, h2, h3, h4, h5, h6, p, label, .stMarkdown {{
  color: var(--v2-text);
}}

h1 {{
  font-size: clamp(1.42rem, 2.15vw, 2.15rem) !important;
  letter-spacing: 0.01em;
}}

.v2-brand {{
  display: flex;
  align-items: center;
  gap: 13px;
  margin-bottom: 15px;
}}

.v2-brand-mark {{
  flex: 0 0 54px;
  width: 54px;
  height: 54px;
  border-radius: 14px;
  background-image: url("{logo}");
  background-position: center;
  background-size: cover;
  box-shadow: 0 0 28px rgba(22, 139, 255, 0.38);
}}

.v2-brand-copy strong {{
  display: block;
  color: #f7fbff;
  font-size: 1rem;
  line-height: 1.35;
}}

.v2-brand-copy span {{
  color: var(--v2-muted);
  font-size: 0.72rem;
}}

.v2-topbar, .v2-panel, .v2-process, .v2-login-card {{
  background: var(--v2-surface);
  border: 1px solid var(--v2-line);
  border-radius: var(--v2-radius);
  box-shadow: 0 18px 58px rgba(0, 0, 0, 0.26);
}}

.v2-topbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 14px 17px;
  margin-bottom: 12px;
}}

.v2-topbar-title {{
  min-width: 240px;
}}

.v2-topbar-title strong {{
  display: block;
  font-size: 1.04rem;
  letter-spacing: 0.03em;
}}

.v2-topbar-title span {{
  color: var(--v2-muted);
  font-size: 0.77rem;
}}

.v2-status-row {{
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}}

.v2-status-pill {{
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 32px;
  padding: 5px 11px;
  color: #cfdef2;
  font-size: 0.76rem;
  white-space: nowrap;
  background: #071a38;
  border: 1px solid rgba(86, 137, 211, 0.25);
  border-radius: 999px;
}}

.v2-status-pill b {{ color: #f5f9ff; }}
.v2-status-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--v2-green); box-shadow: 0 0 11px rgba(49, 217, 139, 0.84); }}
.v2-status-dot.violet {{ background: var(--v2-violet); box-shadow: 0 0 11px rgba(139, 92, 246, 0.84); }}
.v2-status-dot.amber {{ background: var(--v2-amber); box-shadow: 0 0 11px rgba(244, 163, 64, 0.76); }}
.v2-status-dot.off {{ background: var(--v2-danger); box-shadow: 0 0 11px rgba(255, 107, 129, 0.72); }}

.v2-current-context {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  margin: -4px 0 12px;
  color: #cfe1f8;
  background: rgba(5, 19, 43, 0.88);
  border: 1px solid rgba(67, 139, 229, 0.26);
  border-radius: 11px;
}}
.v2-current-context span {{
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 3px 9px;
  background: rgba(8, 28, 61, 0.76);
  border: 1px solid rgba(86, 137, 211, 0.2);
  border-radius: 999px;
  font-size: 0.75rem;
}}
.v2-current-context b {{ color: #ffffff; }}
.v2-current-key {{
  color: #cffff0;
  border-color: rgba(49, 217, 139, 0.32) !important;
}}
.v2-current-key.warn {{
  color: #ffd8a6;
  border-color: rgba(244, 163, 64, 0.45) !important;
}}

.v2-process {{
  display: grid;
  grid-template-columns: repeat(7, minmax(90px, 1fr));
  gap: 0;
  padding: 13px 10px 11px;
  margin: 0 0 12px;
  overflow-x: auto;
}}

.v2-process-step {{
  position: relative;
  min-width: 98px;
  text-align: center;
  color: var(--v2-muted);
}}

.v2-process-step::after {{
  content: "";
  position: absolute;
  z-index: 0;
  top: 15px;
  left: calc(50% + 18px);
  width: calc(100% - 36px);
  height: 1px;
  background: rgba(111, 139, 176, 0.36);
}}

.v2-process-step:last-child::after {{ display: none; }}

.v2-process-index {{
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 31px;
  height: 31px;
  margin: 0 auto 7px;
  color: #bfd0e5;
  font-size: 0.76rem;
  font-weight: 800;
  background: #101a2e;
  border: 1px solid #33445e;
  border-radius: 50%;
}}

.v2-process-step.active {{ color: #ffffff; }}
.v2-process-step.active .v2-process-index {{
  color: #ffffff;
  background: #1268db;
  border-color: #46b5ff;
  box-shadow: 0 0 22px rgba(22, 139, 255, 0.72);
}}
.v2-process-step.done .v2-process-index {{
  color: #ffffff;
  background: #147b57;
  border-color: var(--v2-green);
}}
.v2-process-label {{ display: block; font-size: 0.71rem; line-height: 1.35; }}

.v2-panel {{
  padding: 16px;
  margin-bottom: 12px;
}}

.v2-panel-title {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 13px;
}}
.v2-panel-title strong {{ font-size: 1rem; }}
.v2-panel-title span {{ color: var(--v2-muted); font-size: 0.75rem; }}

.v2-metrics {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}}

.v2-metric {{
  min-height: 112px;
  padding: 14px;
  background: #071b3b;
  border: 1px solid rgba(22, 139, 255, 0.45);
  border-radius: 12px;
  box-shadow: inset 0 0 18px rgba(22, 139, 255, 0.06);
}}
.v2-metric.cyan {{ background: #062433; border-color: rgba(36, 215, 223, 0.48); }}
.v2-metric.violet {{ background: #17143a; border-color: rgba(139, 92, 246, 0.55); }}
.v2-metric.amber {{ background: #2b2015; border-color: rgba(244, 163, 64, 0.56); }}
.v2-metric-label {{ color: #a9bdd4; font-size: 0.75rem; }}
.v2-metric-value {{ display: block; margin: 7px 0 2px; color: #ffffff; font-size: 1.72rem; font-weight: 800; line-height: 1; }}
.v2-metric-hint {{ color: var(--v2-muted); font-size: 0.69rem; }}

.v2-action-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}}
.v2-action-card {{
  min-height: 128px;
  padding: 18px;
  background: #071f3a;
  border: 1px solid rgba(36, 215, 223, 0.36);
  border-radius: 12px;
}}
.v2-action-card.violet {{ background: #19163b; border-color: rgba(139, 92, 246, 0.5); }}
.v2-action-card.green {{ background: #0d2b28; border-color: rgba(49, 217, 139, 0.42); }}
.v2-action-card.amber {{ background: #2b2118; border-color: rgba(244, 163, 64, 0.47); }}
.v2-action-card strong {{ display: block; margin-bottom: 5px; }}
.v2-action-card span {{ color: var(--v2-muted); font-size: 0.75rem; }}

.v2-product-row {{
  display: grid;
  grid-template-columns: minmax(160px, 1.5fr) repeat(3, minmax(88px, 0.7fr));
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  margin-top: 7px;
  background: #081a35;
  border: 1px solid rgba(92, 132, 186, 0.23);
  border-radius: 9px;
}}
.v2-product-row strong {{ font-size: 0.82rem; }}
.v2-product-row span {{ color: var(--v2-muted); font-size: 0.72rem; }}

.v2-empty {{
  padding: 24px;
  text-align: center;
  color: var(--v2-muted);
  background: rgba(7, 23, 50, 0.68);
  border: 1px dashed rgba(95, 146, 213, 0.32);
  border-radius: 10px;
}}

.v2-login-shell {{
  display: grid;
  place-items: center;
  min-height: 74vh;
}}
.v2-login-card {{
  width: min(100%, 480px);
  padding: 28px;
  text-align: center;
}}
.v2-login-logo {{
  width: 84px;
  height: 84px;
  margin: 0 auto 16px;
  background-image: url("{logo}");
  background-position: center;
  background-size: cover;
  border-radius: 20px;
  box-shadow: 0 0 34px rgba(22, 139, 255, 0.44);
}}
.v2-login-head {{ text-align: center; padding: 10px 0 4px; }}
.v2-login-head p {{ color: var(--v2-muted); font-size: 0.8rem; }}

[data-testid="stForm"], [data-testid="stExpander"], [data-testid="stDataFrame"], [data-testid="stFileUploaderDropzone"] {{
  background: rgba(6, 20, 45, 0.9);
  border: 1px solid var(--v2-line) !important;
  border-radius: 12px !important;
}}

[data-testid="stExpander"] details > summary {{
  color: var(--v2-text) !important;
  background: #081a38 !important;
  border-radius: 11px !important;
}}

[data-testid="stExpander"] details[open] > summary {{
  border-bottom: 1px solid var(--v2-line) !important;
  border-radius: 11px 11px 0 0 !important;
}}

[data-testid="stExpander"] details > summary:hover {{
  color: #ffffff !important;
  background: #0a2a54 !important;
}}

[data-testid="stExpander"] details > summary p,
[data-testid="stExpander"] details > summary span,
[data-testid="stExpander"] details > summary svg {{
  color: inherit !important;
  fill: currentColor !important;
}}

[data-testid="stMetric"] {{
  padding: 12px;
  background: rgba(7, 25, 53, 0.9);
  border: 1px solid var(--v2-line);
  border-radius: 12px;
}}

.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button,
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stLinkButton"] a {{
  min-height: 40px;
  color: #eef8ff !important;
  font-weight: 700;
  background: #0a56bd !important;
  border: 1px solid #2da9ff !important;
  border-radius: 9px !important;
  box-shadow: 0 0 18px rgba(22, 139, 255, 0.18);
  touch-action: manipulation;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stFileUploaderDropzone"] button:hover,
[data-testid="stLinkButton"] a:hover {{
  color: #ffffff !important;
  background: #116edb !important;
  border-color: var(--v2-cyan) !important;
}}

.stButton > button[kind="secondary"], .stDownloadButton > button[kind="secondary"] {{
  background: #0b1b34 !important;
  border-color: rgba(108, 151, 210, 0.43) !important;
}}

.stButton > button:disabled,
.stDownloadButton > button:disabled,
[data-testid="stFormSubmitButton"] > button:disabled {{
  color: #667c98 !important;
  background: #08152a !important;
  border-color: rgba(91, 121, 160, 0.28) !important;
  box-shadow: none;
}}

[data-testid="stFileUploaderDropzone"] {{
  color: var(--v2-text) !important;
}}

[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] span {{
  color: var(--v2-muted) !important;
}}

[data-baseweb="input"] button {{
  color: #cde8ff !important;
  background: #081a38 !important;
  border-left: 1px solid rgba(90, 139, 203, 0.42) !important;
}}

[data-baseweb="input"] button:hover {{
  color: #ffffff !important;
  background: #0a2a54 !important;
}}

[data-testid="stCode"], [data-testid="stCode"] pre {{
  color: #dff2ff !important;
  background: #06152e !important;
  border-color: rgba(90, 139, 203, 0.42) !important;
}}

[data-testid="stCode"] button {{
  color: #cde8ff !important;
  background: #0b1b34 !important;
  border: 1px solid rgba(108, 151, 210, 0.43) !important;
}}

[data-testid="stCode"] button:hover {{
  color: #ffffff !important;
  background: #0a2a54 !important;
  border-color: var(--v2-cyan) !important;
}}

button:focus-visible, input:focus-visible, textarea:focus-visible, [tabindex]:focus-visible {{
  outline: 3px solid rgba(36, 215, 223, 0.62) !important;
  outline-offset: 2px !important;
}}

input, textarea, [data-baseweb="select"] > div {{
  color: #f2f8ff !important;
  background: #06152e !important;
  border-color: rgba(90, 139, 203, 0.42) !important;
}}

[data-baseweb="popover"], [role="listbox"], [role="option"] {{
  color: var(--v2-text) !important;
  background-color: #07152e !important;
}}

[role="option"]:hover, [role="option"][aria-selected="true"] {{
  background-color: #0a2a54 !important;
}}

[data-baseweb="tab-list"] {{
  gap: 6px;
  border-bottom: 1px solid var(--v2-line);
}}
[data-baseweb="tab"] {{
  color: var(--v2-muted);
  background: #08182f;
  border-radius: 8px 8px 0 0;
}}
[aria-selected="true"][data-baseweb="tab"] {{
  color: #ffffff;
  background: #0a2a54;
}}

[data-testid="stAlert"] {{
  color: var(--v2-text);
  background: rgba(7, 25, 53, 0.94);
  border: 1px solid var(--v2-line);
}}

@media (max-width: 900px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 0.9rem 0.85rem 4rem; }}
  .v2-topbar {{ align-items: flex-start; flex-direction: column; }}
  .v2-status-row {{ justify-content: flex-start; }}
  .v2-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}

@media (max-width: 560px) {{
  [data-testid="stSidebar"] {{ width: min(88vw, 300px); min-width: min(88vw, 300px); }}
  .v2-status-pill {{ font-size: 0.68rem; }}
  .v2-process {{ grid-template-columns: repeat(7, 104px); }}
  .v2-metrics, .v2-action-grid {{ grid-template-columns: 1fr; }}
  .v2-product-row {{ grid-template-columns: 1fr 1fr; gap: 7px; }}
  .v2-login-card {{ padding: 20px 16px; }}
  .st-key-v2_mobile_nav {{
    display: block;
    position: sticky;
    z-index: 990;
    top: 0;
    padding: 8px 10px;
    margin: -0.9rem -0.85rem 10px;
    background: rgba(3, 13, 31, 0.97);
    border-bottom: 1px solid var(--v2-line);
  }}
}}
</style>
"""


def inject_theme(st_module=None) -> None:
    if st_module is None:
        import streamlit as st_module

    st_module.markdown(build_theme_css(default_asset_urls()), unsafe_allow_html=True)
