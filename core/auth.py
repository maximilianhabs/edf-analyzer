"""Cookie-basiertes Login-Gate für EDF Analyzer.

Ersetzt Caddy basicauth — funktioniert zuverlässig auf iOS Safari.
Nutzt extra-streamlit-components für echte Cookie-Persistenz (30 Tage).
"""

import hashlib
import hmac
import os
import time
import streamlit as st

# ── Konfiguration ──────────────────────────────────────────────────────────────
_PASSWORD   = os.environ.get("EDF_PASSWORD", "[REDACTED_PASSWORD]")
_COOKIE_KEY = "edf_auth_v1"
_COOKIE_EXP = 30  # Tage

def _sign(password: str, day: str) -> str:
    secret = hashlib.sha256((_PASSWORD + "edf_salt_v1").encode()).digest()
    return hmac.new(secret, (password + day).encode(), hashlib.sha256).hexdigest()[:40]

def _valid_cookie(value: str) -> bool:
    """Token für heute und gestern akzeptieren (toleriert Mitternacht)."""
    now = int(time.time()) // 86400
    for d in (now, now - 1):
        if hmac.compare_digest(value, _sign(_PASSWORD, str(d))):
            return True
    return False

def _fresh_token() -> str:
    return _sign(_PASSWORD, str(int(time.time()) // 86400))


def require_login() -> bool:
    """Prüft Auth. Gibt True zurück wenn eingeloggt, sonst Login-Formular."""

    # 1. Session bereits authentifiziert
    if st.session_state.get("_edf_auth"):
        return True

    # 2. Cookie prüfen
    try:
        from extra_streamlit_components import CookieManager
        cm = CookieManager(key="edf_cookie_mgr")
        cookie_val = cm.get(_COOKIE_KEY)
        if cookie_val and _valid_cookie(cookie_val):
            st.session_state["_edf_auth"] = True
            return True
    except Exception:
        pass  # extra_streamlit_components nicht verfügbar → nur Session

    # 3. Login-Formular zeigen
    _render_login()
    return False


def _render_login():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@40,400,0,0');

    /* Sidebar + Header bei Login ausblenden */
    [data-testid="stSidebar"],
    header[data-testid="stHeader"],
    [data-testid="stToolbar"],
    footer { display: none !important; }

    /* Vollbild-Zentrierung */
    .block-container { padding-top: 0 !important; }

    .login-outer {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 88vh;
    }
    .login-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 44px 40px 36px;
        max-width: 360px;
        width: 100%;
        box-shadow: 0 4px 28px rgba(0,0,0,0.08);
        text-align: center;
    }
    .login-icon {
        font-family: 'Material Symbols Outlined';
        font-size: 2.6rem;
        color: #0071e3;
        margin-bottom: 8px;
        line-height: 1;
    }
    .login-title { font-size: 1.3rem; font-weight: 700; color: #1c2833; margin-bottom: 4px; }
    .login-sub   { font-size: 0.82rem; color: #7f8c8d; margin-bottom: 28px; }

    @media (max-width: 480px) {
        .login-card  { padding: 32px 20px 28px; border-radius: 14px; }
        .login-title { font-size: 1.15rem; }
    }
    </style>

    <div class="login-outer">
      <div class="login-card">
        <div class="login-icon">neurology</div>
        <div class="login-title">EDF Analyzer</div>
        <div class="login-sub">Neuro-Vibe · Zugang geschützt</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Zentriertes Formular unter der Karte. WICHTIG: st.form statt einzelner
    # text_input+button — bei zwei unabhängigen Widgets löst Enter im Passwortfeld
    # zwar einen Rerun aus, aber der Button-Klick-Status bleibt in diesem Rerun False
    # (der Button wurde ja nicht geklickt), daher passierte vorher "nichts" bei Enter,
    # bis man zusätzlich klickte (User-Fund 2026-08-08). st.form löst bei Enter in
    # JEDEM enthaltenen Feld automatisch den form_submit_button aus — behebt das direkt.
    _, col, _ = st.columns([1, 2.2, 1])
    with col:
        with st.form("_login_form", clear_on_submit=False):
            pw = st.text_input(
                "Passwort",
                type="password",
                placeholder="Passwort eingeben",
                label_visibility="collapsed",
                key="_login_pw",
                autocomplete="current-password",
            )
            login_clicked = st.form_submit_button(
                "Anmelden", use_container_width=True, type="primary"
            )

    if login_clicked and pw:
        if pw == _PASSWORD:
            st.session_state["_edf_auth"] = True
            # Cookie setzen
            try:
                from extra_streamlit_components import CookieManager
                cm = CookieManager(key="edf_cookie_mgr_set")
                cm.set(_COOKIE_KEY, _fresh_token(), max_age=_COOKIE_EXP * 86400)
            except Exception:
                pass
            st.rerun()
        else:
            st.error("Falsches Passwort. Bitte erneut versuchen.")
    elif login_clicked:
        st.warning("Bitte Passwort eingeben.")


def logout_button():
    """Logout-Button für Sidebar."""
    if st.sidebar.button("🔓 Abmelden", use_container_width=True, key="_logout_btn"):
        st.session_state.pop("_edf_auth", None)
        try:
            from extra_streamlit_components import CookieManager
            cm = CookieManager(key="edf_cookie_mgr_del")
            cm.delete(_COOKIE_KEY)
        except Exception:
            pass
        st.rerun()
