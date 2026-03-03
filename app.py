"""DocuForge — Streamlit Frontend"""
import time, re, requests
import streamlit as st

API_BASE = "http://localhost:8000"
st.set_page_config(page_title="DocuForge", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap');
[data-testid="stAppViewContainer"]{background:#08080f;font-family:'Inter',sans-serif;}
[data-testid="stHeader"]{background:transparent;}
#MainMenu,footer,header{visibility:hidden;}
h1,h2,h3,h4{font-family:'Inter',sans-serif!important;color:#fff!important;}
p,li{color:#c8c5e0!important;}
.stTextInput>div>div>input{background:#0d0d18!important;border:1px solid #1c1c2e!important;border-radius:8px!important;color:#e8e6f0!important;font-family:'DM Mono',monospace!important;font-size:13px!important;padding:12px 16px!important;}
.stTextInput>div>div>input:focus{border-color:#7c6af7!important;box-shadow:0 0 0 2px rgba(124,106,247,0.2)!important;}
.stTextInput>label{color:#8885a0!important;font-size:11px!important;letter-spacing:0.1em;}
.stButton>button{background:#7c6af7!important;color:#fff!important;border:none!important;border-radius:8px!important;font-family:'Inter',sans-serif!important;font-weight:600!important;font-size:13px!important;letter-spacing:0.06em!important;width:100%;padding:10px 0!important;}
.stButton>button:hover{opacity:0.85!important;}
.stProgress>div>div>div{background:linear-gradient(90deg,#7c6af7,#a78bfa)!important;}
[data-testid="stProgressBar"]{background:#1c1c2e!important;border-radius:4px;}
.stTabs [data-baseweb="tab-list"]{background:#0d0d18!important;border-bottom:1px solid #1c1c2e!important;gap:0!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:#5a5870!important;font-size:12px!important;font-family:'DM Mono',monospace!important;letter-spacing:0.06em!important;border-radius:0!important;padding:10px 18px!important;border-bottom:2px solid transparent!important;}
.stTabs [aria-selected="true"]{color:#a78bfa!important;border-bottom:2px solid #7c6af7!important;background:#111120!important;}
.stTabs [data-baseweb="tab-panel"]{background:#08080f!important;padding:0!important;}
.streamlit-expanderHeader{background:#0d0d18!important;border:1px solid #1c1c2e!important;border-radius:8px!important;color:#8885a0!important;font-family:'DM Mono',monospace!important;font-size:12px!important;}
.streamlit-expanderContent{background:#07070f!important;border:1px solid #1c1c2e!important;border-top:none!important;border-radius:0 0 8px 8px!important;}
[data-testid="stDownloadButton"]>button{background:#111120!important;border:1px solid #1c1c2e!important;color:#8885a0!important;font-size:11px!important;padding:7px 14px!important;border-radius:6px!important;}
hr{border-color:#1c1c2e!important;}
.doc-wrap{background:#0a0a14;border:1px solid #1c1c2e;border-radius:12px;padding:36px 44px;font-family:'Inter',sans-serif;line-height:1.75;color:#c8c5e0;}
.doc-wrap h1{font-size:1.8rem;color:#fff;border-bottom:1px solid #1c1c2e;padding-bottom:12px;margin-bottom:24px;}
.doc-wrap h2{font-size:1.3rem;color:#eae8f8;margin-top:36px;margin-bottom:14px;}
.doc-wrap h3{font-size:1.1rem;color:#c5c2d8;margin-top:24px;margin-bottom:10px;}
.doc-wrap h4{font-size:1rem;color:#a8a5be;margin-top:18px;margin-bottom:8px;}
.doc-wrap code{background:#111120;border:1px solid #1c1c2e;border-radius:4px;padding:2px 7px;font-family:'DM Mono',monospace;font-size:12.5px;color:#a78bfa;}
.doc-wrap pre{background:#07070f;border:1px solid #1c1c2e;border-radius:8px;padding:18px;overflow-x:auto;margin:20px 0;}
.doc-wrap pre code{background:none;border:none;padding:0;color:#a78bfa;font-size:13px;}
.doc-wrap a{color:#7c6af7;}
.doc-wrap blockquote{border-left:3px solid #7c6af7;margin:16px 0;padding:10px 18px;background:#0d0d18;color:#6a6880;border-radius:0 6px 6px 0;}
.doc-wrap ul,.doc-wrap ol{padding-left:22px;}
.doc-wrap li{margin:6px 0;color:#b0adc8;}
.doc-wrap strong{color:#e0ddf0;}
.doc-wrap p{margin:0 0 14px;}
.doc-wrap table{width:100%;border-collapse:collapse;margin:20px 0;}
.doc-wrap th{background:#111120;color:#a78bfa;font-size:12px;letter-spacing:0.06em;padding:10px 14px;border:1px solid #1c1c2e;text-align:left;}
.doc-wrap td{padding:9px 14px;border:1px solid #1c1c2e;color:#c0bdd8;font-size:14px;}
.doc-wrap tr:nth-child(even) td{background:#0d0d18;}
.doc-wrap hr{border:none;border-top:1px solid #1c1c2e;margin:28px 0;}
</style>""", unsafe_allow_html=True)

for k,v in {"phase":"idle","job_id":None,"logs":[],"progress":0,"docs":None,"error":"","repo_url":""}.items():
    if k not in st.session_state: st.session_state[k]=v

def api_health():
    try: return requests.get(f"{API_BASE}/health",timeout=3).status_code==200
    except: return False

def api_start(url,token):
    r=requests.post(f"{API_BASE}/api/document",json={"repo_url":url,"github_token":token or None},timeout=15)
    r.raise_for_status(); return r.json()

def api_job(jid):
    r=requests.get(f"{API_BASE}/api/jobs/{jid}",timeout=10)
    r.raise_for_status(); return r.json()

def md_to_html(src):
    s=src
    def codeblock(m):
        lang=m.group(1) or "code"
        code=m.group(2).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f'<pre><code class="lang-{lang}">{code}</code></pre>'
    s=re.sub(r"```(\w*)\n?([\s\S]*?)```",codeblock,s)
    def tableblock(m):
        rows=[r.strip() for r in m.group(0).strip().split("\n") if r.strip()]
        html="<table>"; i=0
        for row in rows:
            if re.match(r"^\|?[\s\-:]+\|",row): continue
            cells=[c.strip() for c in row.strip("|").split("|")]
            tag="th" if i==0 else "td"
            html+="<tr>"+"".join(f"<{tag}>{c}</{tag}>" for c in cells)+"</tr>"; i+=1
        return html+"</table>"
    s=re.sub(r"(\|.+\|\n)+",tableblock,s)
    for n in range(6,0,-1): s=re.sub(rf"^{'#'*n} (.+)$",rf"<h{n}>\1</h{n}>",s,flags=re.MULTILINE)
    s=re.sub(r"^> (.+)$",r"<blockquote>\1</blockquote>",s,flags=re.MULTILINE)
    s=re.sub(r"^---$","<hr>",s,flags=re.MULTILINE)
    s=re.sub(r"\*\*\*(.+?)\*\*\*",r"<strong><em>\1</em></strong>",s)
    s=re.sub(r"\*\*(.+?)\*\*",r"<strong>\1</strong>",s)
    s=re.sub(r"\*(.+?)\*",r"<em>\1</em>",s)
    s=re.sub(r"`([^`]+)`",r"<code>\1</code>",s)
    s=re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",r'<img src="\2" alt="\1" style="max-width:100%">',s)
    s=re.sub(r"\[([^\]]+)\]\(([^)]+)\)",r'<a href="\2" target="_blank">\1</a>',s)
    def ul_block(m):
        items="".join(f"<li>{re.sub(r'^[-*]\\s','',l.strip())}</li>" for l in m.group(0).strip().split("\n") if l.strip())
        return f"<ul>{items}</ul>"
    s=re.sub(r"((?:^[-*]\s.+\n?)+)",ul_block,s,flags=re.MULTILINE)
    def ol_block(m):
        items="".join(f"<li>{re.sub(r'^\\d+\\.\\s','',l.strip())}</li>" for l in m.group(0).strip().split("\n") if l.strip())
        return f"<ol>{items}</ol>"
    s=re.sub(r"((?:^\d+\.\s.+\n?)+)",ol_block,s,flags=re.MULTILINE)
    out=[]
    for block in re.split(r"\n{2,}",s):
        block=block.strip()
        if not block: continue
        if re.match(r"^<(h[1-6]|ul|ol|pre|table|blockquote|hr)",block): out.append(block)
        else: out.append(f"<p>{block}</p>")
    return "\n".join(out)

def build_all(docs,name):
    parts=[f"# {name} Documentation\n\n",docs.get("main_readme",""),"\n\n---\n\n",docs.get("how_to_run",""),"\n\n---\n\n",docs.get("architecture_doc","")]
    if docs.get("api_reference"): parts+=["\\n\n---\n\n",docs["api_reference"]]
    if docs.get("contributing_guide"): parts+=["\\n\n---\n\n",docs["contributing_guide"]]
    for fr in (docs.get("folder_readmes") or []): parts+=[f"\n\n---\n\n## {fr['folder']}/\n\n",fr.get("content","")]
    return "".join(parts)

# HEADER
st.markdown("""<div style="padding:24px 0 20px;border-bottom:1px solid #1c1c2e;margin-bottom:28px;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;">
    <span style="font-size:26px;color:#7c6af7;">◈</span>
    <span style="font-size:20px;font-weight:700;letter-spacing:0.18em;color:#fff;font-family:'DM Mono',monospace;">DOCUFORGE</span>
    <span style="font-size:9px;letter-spacing:0.2em;background:#7c6af7;color:#fff;padding:3px 10px;border-radius:2px;font-family:'DM Mono',monospace;">AI AGENT</span>
  </div>
  <span style="font-size:12px;color:#3d3a52;letter-spacing:0.04em;">Autonomous codebase documentation · powered by Claude</span>
</div>""", unsafe_allow_html=True)

phase=st.session_state.phase

# ── IDLE ──────────────────────────────────────────────────────────────────────
if phase=="idle":
    L,R=st.columns([1.15,0.85],gap="large")
    with L:
        st.markdown("""<div style="padding-top:8px;">
          <div style="display:inline-block;background:#7c6af7;color:#fff;font-size:10px;font-weight:600;letter-spacing:0.2em;padding:3px 10px;border-radius:3px;margin-bottom:18px;font-family:'DM Mono',monospace;">AI AGENT v1.0</div>
          <div style="font-size:2.8rem;font-weight:700;color:#fff;letter-spacing:-0.02em;line-height:1.1;margin-bottom:16px;">Document any<br/>codebase,<br/><span style="color:#7c6af7;">autonomously.</span></div>
          <div style="font-size:15px;color:#5a5870;line-height:1.75;margin-bottom:28px;">Point DocuForge at any GitHub repo.<br/>The AI agent clones it, reads every file,<br/>maps dependencies, and writes complete<br/>professional documentation — automatically.</div></div>""",unsafe_allow_html=True)
        chips=["✓ git clone","✓ recursive analysis","✓ dependency mapping","✓ folder READMEs","✓ architecture doc","✓ how-to-run guide","✓ API reference","✓ contributing guide"]
        st.markdown('<div style="margin-bottom:32px;">'+" ".join(f'<span style="display:inline-block;background:#0d0d18;border:1px solid #1c1c2e;color:#5a5870;font-size:11px;padding:4px 10px;border-radius:4px;margin:3px;font-family:\'DM Mono\',monospace;">{c}</span>' for c in chips)+"</div>",unsafe_allow_html=True)
        for num,icon,text in [("01","🔗","Paste any public or private GitHub repository URL"),("02","🤖","Agent autonomously clones, explores, and maps the codebase"),("03","📝","Full docs generated — browse, copy, download as Markdown")]:
            st.markdown(f'<div style="background:rgba(124,106,247,0.1);border:1px solid rgba(124,106,247,0.22);border-radius:8px;padding:14px 18px;margin-bottom:10px;"><div style="color:#7c6af7;font-size:10px;font-weight:700;letter-spacing:0.12em;margin-bottom:4px;font-family:\'DM Mono\',monospace;">STEP {num}</div><div style="color:#c8c5e0;font-size:13px;">{icon} &nbsp;{text}</div></div>',unsafe_allow_html=True)
    with R:
        ok=api_health()
        if not ok: st.error("⚠️ Backend offline — start FastAPI on port 8000.")
        st.markdown('<div style="background:#0d0d18;border:1px solid #1c1c2e;border-radius:12px;padding:28px 28px 22px;margin-top:8px;"><div style="font-size:10px;color:#3d3a52;letter-spacing:0.15em;margin-bottom:20px;font-family:\'DM Mono\',monospace;">CONFIGURE</div>',unsafe_allow_html=True)
        repo_url=st.text_input("GITHUB REPOSITORY URL",placeholder="https://github.com/owner/repository",key="inp_url")
        with st.expander("🔑  GitHub Token — optional, for private repos"):
            github_token=st.text_input("Personal Access Token",placeholder="ghp_xxxxxxxxxxxxxxxxxxxx",type="password",key="inp_tok")
        st.markdown("<div style='height:8px'></div>",unsafe_allow_html=True)
        run=st.button("⚡  GENERATE DOCUMENTATION",disabled=not ok,use_container_width=True)
        st.markdown("</div>",unsafe_allow_html=True)
        st.markdown('<div style="margin-top:16px;padding:18px;background:#0a0a14;border:1px solid #1c1c2e;border-radius:10px;"><div style="font-size:10px;color:#3d3a52;letter-spacing:0.15em;margin-bottom:12px;font-family:\'DM Mono\',monospace;">TRY AN EXAMPLE REPO</div>',unsafe_allow_html=True)
        examples=[("FastAPI","https://github.com/tiangolo/fastapi"),("Pydantic","https://github.com/pydantic/pydantic"),("Requests","https://github.com/psf/requests"),("Rich","https://github.com/Textualize/rich")]
        ec=st.columns(2)
        for i,(name,eurl) in enumerate(examples):
            with ec[i%2]:
                if st.button(f"↗ {name}",key=f"ex_{i}",use_container_width=True):
                    st.session_state["inp_url"]=eurl; st.rerun()
        st.markdown("</div>",unsafe_allow_html=True)
        if run:
            url=(repo_url or st.session_state.get("inp_url","")).strip()
            if not url: st.error("Please enter a GitHub URL.")
            elif "github.com" not in url: st.error("Must be a github.com URL.")
            else:
                tok=(st.session_state.get("inp_tok") or "").strip() or None
                try:
                    res=api_start(url,tok)
                    st.session_state.update(job_id=res["job_id"],repo_url=url,phase="running",logs=[],progress=2)
                    st.rerun()
                except Exception as e: st.error(f"Failed: {e}")

# ── RUNNING ───────────────────────────────────────────────────────────────────
elif phase=="running":
    st.markdown(f'<div style="margin-bottom:24px;"><div style="font-size:11px;color:#7c6af7;letter-spacing:0.2em;font-family:\'DM Mono\',monospace;margin-bottom:6px;">AGENT RUNNING</div><div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px;">Documenting repository...</div><div style="font-size:13px;color:#5a5870;font-family:\'DM Mono\',monospace;">{st.session_state.repo_url}</div></div>',unsafe_allow_html=True)
    pct=st.session_state.progress
    st.progress(pct/100)
    st.markdown(f'<div style="text-align:right;font-size:13px;color:#7c6af7;font-family:\'DM Mono\',monospace;margin-top:-8px;margin-bottom:16px;">{pct}%</div>',unsafe_allow_html=True)
    steps=[("🔀","Cloning",20),("🔍","Exploring",50),("🧠","Analyzing",85),("✍️","Generating",101)]
    ai=next((i for i,(_,_,t) in enumerate(steps) if pct<t),3)
    ph=" &nbsp;→&nbsp; ".join(f'<span style="color:#7c6af7;font-weight:600;">{e} {l}</span>' if i==ai else f'<span style="color:#2a2838;">{e} {l}</span>' for i,(e,l,_) in enumerate(steps))
    st.markdown(f'<div style="font-size:12px;font-family:\'DM Mono\',monospace;margin-bottom:24px;">{ph}</div>',unsafe_allow_html=True)
    LOG_C={"system":"#8885a0","tool":"#60a5fa","success":"#6ee7b7","error":"#f87171"}
    logs=st.session_state.logs
    log_html="".join(f'<div style="margin-bottom:4px;line-height:1.5;"><span style="color:#3d3a52;margin-right:12px;font-size:11px;">{time.strftime("%H:%M:%S",time.localtime(e.get("ts",time.time())))}</span><span style="color:{LOG_C.get(e.get("type","system"),"#8885a0")};">{e.get("message","").replace("<","&lt;").replace(">","&gt;")}</span></div>' for e in logs[-80:]) or '<div style="color:#3d3a52;">Initializing agent...</div>'
    st.markdown(f'<div style="background:#04040a;border:1px solid #1c1c2e;border-radius:10px;overflow:hidden;font-family:\'DM Mono\',monospace;font-size:12px;"><div style="background:#0d0d18;border-bottom:1px solid #1c1c2e;padding:10px 16px;display:flex;align-items:center;gap:7px;"><span style="width:11px;height:11px;border-radius:50%;background:#f87171;display:inline-block;"></span><span style="width:11px;height:11px;border-radius:50%;background:#fbbf24;display:inline-block;"></span><span style="width:11px;height:11px;border-radius:50%;background:#6ee7b7;display:inline-block;"></span><span style="color:#3d3a52;font-size:11px;margin-left:8px;letter-spacing:0.12em;">AGENT LOG</span></div><div style="padding:16px 18px;max-height:380px;overflow-y:auto;">{log_html}<span style="color:#7c6af7;">▋</span></div></div>',unsafe_allow_html=True)
    st.markdown("<div style='height:16px'></div>",unsafe_allow_html=True)
    _,cc=st.columns([3,1])
    with cc:
        if st.button("✕  Cancel",use_container_width=True):
            st.session_state.phase="idle"; st.rerun()
    time.sleep(1.2)
    try:
        job=api_job(st.session_state.job_id)
        st.session_state.logs=job.get("logs",[]); st.session_state.progress=job.get("progress",pct)
        if job["status"]=="done":
            st.session_state.docs=job.get("docs",{}); st.session_state.phase="done"; st.rerun()
        elif job["status"]=="error":
            st.session_state.error=job.get("error","Unknown"); st.session_state.phase="error"; st.rerun()
        else: st.rerun()
    except Exception as e:
        st.warning(f"Polling error: {e}"); time.sleep(2); st.rerun()

# ── DONE ──────────────────────────────────────────────────────────────────────
elif phase=="done":
    docs=st.session_state.docs or {}
    repo_url=st.session_state.repo_url
    repo_name=repo_url.rstrip("/").split("/")[-1]
    tc,ac=st.columns([2,1])
    with tc:
        st.markdown(f'<div style="padding:4px 0 20px;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;"><span style="font-size:20px;color:#7c6af7;">◈</span><span style="font-size:15px;font-weight:700;color:#7c6af7;letter-spacing:0.1em;font-family:\'DM Mono\',monospace;">DOCS READY</span><span style="font-size:11px;color:#3d3a52;font-family:\'DM Mono\',monospace;">· {repo_name}</span></div><a href="{repo_url}" target="_blank" style="font-size:12px;color:#3d3a52;text-decoration:none;">{repo_url}</a></div>',unsafe_allow_html=True)
    with ac:
        st.markdown("<div style='padding-top:8px;'>",unsafe_allow_html=True)
        if st.button("← New Repository",use_container_width=True):
            st.session_state.phase="idle"; st.session_state.docs=None; st.rerun()
        st.markdown("</div>",unsafe_allow_html=True)
    folders=docs.get("folder_readmes") or []
    page_count=3+bool(docs.get("api_reference"))+bool(docs.get("contributing_guide"))+len(folders)
    word_count=sum(len((docs.get(k) or "").split()) for k in ["main_readme","how_to_run","architecture_doc","api_reference","contributing_guide"])+sum(len(fr.get("content","").split()) for fr in folders)
    s1,s2,s3,s4=st.columns(4)
    for col,(val,label) in zip([s1,s2,s3,s4],[(page_count,"PAGES GENERATED"),(len(folders),"FOLDER READMEs"),(f"~{word_count:,}","WORDS WRITTEN"),("100%","COMPLETE")]):
        with col: st.markdown(f'<div style="background:#0d0d18;border:1px solid #1c1c2e;border-radius:10px;padding:20px;text-align:center;margin-bottom:20px;"><div style="font-size:1.9rem;font-weight:700;color:#7c6af7;font-family:\'DM Mono\',monospace;">{val}</div><div style="font-size:10px;color:#5a5870;letter-spacing:0.1em;margin-top:4px;">{label}</div></div>',unsafe_allow_html=True)
    tab_defs=[("📄 README.md","main_readme"),("▶  How to Run","how_to_run"),("🏗  Architecture","architecture_doc")]
    if docs.get("api_reference"): tab_defs.append(("📡 API Reference","api_reference"))
    if docs.get("contributing_guide"): tab_defs.append(("🤝 Contributing","contributing_guide"))
    if docs.get("changelog"): tab_defs.append(("📋 Changelog","changelog"))
    for fr in folders: tab_defs.append((f"📁 {fr['folder']}",f"__f__{fr['folder']}"))
    tabs=st.tabs([t[0] for t in tab_defs])
    for tw,(tlabel,tkey) in zip(tabs,tab_defs):
        with tw:
            if tkey.startswith("__f__"):
                fn=tkey[5:]; content=next((fr["content"] for fr in folders if fr["folder"]==fn),"_No content._")
            else: content=docs.get(tkey) or "_No content generated._"
            bl,br=st.columns([3,1])
            with bl: st.markdown(f'<div style="font-size:10px;color:#3d3a52;font-family:\'DM Mono\',monospace;padding:10px 0 14px;letter-spacing:0.1em;">{tlabel.strip().upper()}</div>',unsafe_allow_html=True)
            with br:
                safe=tkey.replace("__f__","").replace("/","_")
                st.download_button("⬇ Download .md",data=content,file_name=f"{repo_name}-{safe or 'doc'}.md",mime="text/markdown",use_container_width=True,key=f"dl_{safe}")
            st.markdown(f'<div class="doc-wrap">{md_to_html(content)}</div>',unsafe_allow_html=True)
            st.markdown("<div style='height:12px'></div>",unsafe_allow_html=True)
            with st.expander("View raw Markdown"): st.code(content,language="markdown")
    st.divider()
    d1,d2,_=st.columns([1,1,2])
    with d1: st.download_button("⬇ Download All Docs",data=build_all(docs,repo_name),file_name=f"{repo_name}-full-docs.md",mime="text/markdown",use_container_width=True)
    with d2:
        if st.button("🔄 Document another repo",use_container_width=True):
            st.session_state.phase="idle"; st.session_state.docs=None; st.rerun()

# ── ERROR ─────────────────────────────────────────────────────────────────────
elif phase=="error":
    st.markdown('<div style="text-align:center;padding:60px 0 24px;"><div style="font-size:52px;margin-bottom:16px;">⚠</div><div style="font-size:22px;font-weight:700;color:#f87171;margin-bottom:10px;">Agent Failed</div></div>',unsafe_allow_html=True)
    st.error(st.session_state.error or "An unknown error occurred.")
    _,c,_=st.columns([1,1,1])
    with c:
        if st.button("← Try Again",use_container_width=True):
            st.session_state.phase="idle"; st.session_state.error=""; st.rerun()