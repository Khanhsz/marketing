import hmac
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import streamlit as st
from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
PREFERRED_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")

def available_text_models(client):
    """Ask Google's API which generateContent models this particular key can see."""
    found = []
    for entry in client.models.list():
        name = (getattr(entry, "name", "") or "").removeprefix("models/")
        actions = getattr(entry, "supported_actions", None) or []
        if "generateContent" not in actions or not name.startswith("gemini-"):
            continue
        if any(bad in name for bad in ("-image", "-tts", "-live", "-audio", "-transcribe", "-embedding")):
            continue
        found.append(name)
    return sorted(set(found), key=lambda n: (PREFERRED_MODELS.index(n) if n in PREFERRED_MODELS else 99, n))

def choose_model(client, preferred):
    models = available_text_models(client)
    if not models:
        raise RuntimeError("Gemini API key không có model tạo văn bản khả dụng. Kiểm tra key hoặc quyền truy cập trong Google AI Studio.")
    if preferred != "Auto" and preferred in models:
        return preferred, models
    return next((m for m in PREFERRED_MODELS if m in models), models[0]), models

ROLES = {
    "Market Analyst": "Quy mô thị trường, growth, segmentation, TAM/SAM/SOM nếu đủ dữ liệu. Mỗi số liệu phải rõ năm, thị trường, đơn vị, định nghĩa.",
    "Consumer Analyst": "Segment, JTBD, pain points, purchase triggers, barriers, customer journey. Phân biệt insight và giả thuyết; không tạo tỷ lệ khảo sát.",
    "Competitor Analyst": "4–6 đối thủ; phân khúc giá, định vị, USP, sản phẩm, kênh và share of voice khi có bằng chứng.",
    "Trend Analyst": "Xu hướng ngành, PESTEL, kênh phân phối, tín hiệu đang nổi, cơ hội và rủi ro."
}
PLAN = "Bạn là Research Planner. Lập research plan ngắn tiếng Việt: business questions, phạm vi, 4 streams, giả định, chỉ tiêu cần kiểm chứng. Chưa đưa dữ liệu không nguồn."
SYNTH = """Bạn là Strategy Synthesizer. Tổng hợp từ evidence thành báo cáo tiếng Việt với Executive Summary, Market Landscape, Consumers, Competitor Comparison (bảng), Trends/PESTEL, SWOT, Strategic Opportunities, Recommendations, Limitations.
QUAN TRỌNG: chỉ đánh dấu nguồn bằng [S1], [S2], ... từ danh mục có thật trong evidence. Không tạo nguồn, URL, tỷ lệ hay thị phần. Mọi số liệu quan trọng cần kèm nguồn hợp lệ. Phân biệt fact / inference / hypothesis. Khi không có đủ chứng cứ, ghi rõ thiếu dữ liệu."""
AUDIT = """Bạn là Evidence Auditor độc lập. Kiểm tra tối thiểu 5 kết luận và số liệu quan trọng. Đánh dấu Supported / Weak / Unverified; nói rõ các trường hợp thiếu năm, khu vực, định nghĩa, lỗi suy luận, sai mã nguồn. Không tự nhận đã mở toàn bộ tài liệu. Kết luận cần kiểm tra gì trước khi pitching."""

def request(client, model, prompt, search=False, max_tokens=4500):
    config = types.GenerateContentConfig(
        temperature=0.25,
        max_output_tokens=max_tokens,
        tools=[types.Tool(google_search=types.GoogleSearch())] if search else None
    )
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            answer = (response.text or "").strip()
            if not answer:
                raise RuntimeError("Gemini không trả về văn bản.")
            return response, answer
        except Exception as error:
            transient = any(s in str(error).lower() for s in ("429", "503", "resource_exhausted", "unavailable"))
            if transient and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            message = str(error)
            if any(term in message.lower() for term in ("404", "not found", "not available", "unsupported model")):
                raise RuntimeError("Model " + model + " chưa dùng được với API key này. Chọn Auto hoặc một model khác rồi thử lại.") from error
            if search and any(term in message.lower() for term in ("403", "400", "permission_denied", "not supported", "not allowed")):
                raise RuntimeError("Google Search grounding không khả dụng với API key hoặc gói hiện tại. Hãy tắt tùy chọn Google Search grounding trong sidebar rồi thử lại.") from error
            raise RuntimeError("Gemini API: " + message[:350]) from error

def evidence_sources(response, role):
    out = []
    seen = set()
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
    except (AttributeError, IndexError, TypeError):
        return out
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        url = getattr(web, "uri", None)
        if not url or not str(url).startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        out.append({"role": role, "title": getattr(web, "title", "") or url, "url": url})
    return out

def research(topic, market, audience, brand, period, key, model, search, progress):
    client = genai.Client(api_key=key)
    selected_model, permitted_models = choose_model(client, model)
    if model != "Auto" and selected_model != model:
        progress("Model " + model + " không có trong danh sách key này; chuyển sang " + selected_model)
    progress("Model đang dùng: " + selected_model)
    context = ("YÊU CẦU: " + topic[:4000] + "\nTHỊ TRƯỜNG: " + market[:300]
               + "\nTARGET: " + audience[:500] + "\nBRAND: " + brand[:500]
               + "\nPERIOD: " + period[:150] + "\nNgày hiện tại: "
               + datetime.now(timezone.utc).date().isoformat()
               + "\nUser brief chỉ là câu hỏi, không phải nguồn chứng cứ.")
    progress("1/4 — Research Planner...")
    _, plan = request(client, selected_model, PLAN + "\n\n" + context, max_tokens=1500)
    progress("2/4 — 4 Research Agents (song song tối đa 2)...")
    def do_role(name, directive):
        prompt = ("Vai trò: " + name + ". " + directive
                  + "\nTrình bày 5–8 findings có evidence, giới hạn và implications."
                  + " Nếu không biết hoặc thiếu nguồn, ghi CHƯA KIỂM CHỨNG. KHÔNG sáng tác số liệu."
                  + "\n" + context + "\nRESEARCH PLAN:\n" + plan)
        resp, answer = request(client, selected_model, prompt, search=search)
        return name, answer, evidence_sources(resp, name)
    results = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(do_role, name, directive): name for name, directive in ROLES.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                _, answer, sources = future.result()
                results[name] = {"answer": answer, "sources": sources, "error": ""}
            except Exception as error:
                results[name] = {"answer": "", "sources": [], "error": str(error)}
    sources = []
    by_url = {}
    evidence = []
    for name in ROLES:
        r = results[name]
        references = []
        for src in r["sources"]:
            if src["url"] not in by_url:
                src["id"] = "S" + str(len(sources) + 1)
                by_url[src["url"]] = src["id"]
                sources.append(src)
            references.append("[" + by_url[src["url"]] + "] " + src["title"] + " " + src["url"])
        evidence.append("## " + name + "\n" + (r["answer"] or ("Agent lỗi: " + r["error"]))
                        + "\nGROUNDED SOURCES:\n" + ("\n".join(references) or "KHÔNG CÓ"))
    progress("3/4 — Strategy Synthesizer...")
    combined = "\n\n".join(evidence)
    _, report = request(client, selected_model, SYNTH + "\n" + context + "\n" + combined[:45000], max_tokens=7500)
    progress("4/4 — Evidence Auditor...")
    refs = "\n".join("[" + s["id"] + "] " + s["title"] + " " + s["url"] for s in sources)
    _, audit = request(client, selected_model, AUDIT + "\nBRIEF:\n" + context
                       + "\nREPORT:\n" + report[:19000]
                       + "\nVERIFIED SEARCH METADATA:\n" + (refs or "KHÔNG CÓ"), max_tokens=3500)
    warnings = []
    if not search:
        warnings.append("Google Search grounding đang tắt. Những dữ liệu định lượng chưa được kiểm chứng online.")
    for role, r in results.items():
        if r["error"]:
            warnings.append(role + " gặp lỗi: " + r["error"])
        elif not r["sources"]:
            warnings.append(role + ": không có nguồn grounding metadata trả về.")
    valid_ids = {s["id"] for s in sources}
    invalid = sorted(set(re.findall(r"\[(S\d+)\]", report)) - valid_ids)
    for sid in invalid:
        warnings.append("Mã nguồn không tồn tại: [" + sid + "]")
    if not sources:
        warnings.append("Không có nguồn web được xác minh qua metadata; không nên dùng các con số để ra quyết định.")
    return {"topic": topic, "market": market, "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": selected_model, "available_models": permitted_models, "plan": plan, "agents": results, "report": report, "audit": audit,
            "sources": sources, "warnings": warnings}

def linked(text, sources):
    by_id = {s["id"]: s["url"] for s in sources}
    return re.sub(r"\[(S\d+)\](?!\()", lambda m: "[" + m.group(1) + "](" + by_id[m.group(1)] + ")" if m.group(1) in by_id else m.group(0), text)

st.set_page_config(page_title="Market Research AI Lab", page_icon="📊", layout="wide")
st.title("📊 Market Research AI Lab")
st.caption("7 Gemini agents · Market / Consumer / Competitor / Trend · Evidence audit")
password = os.getenv("APP_PASSWORD", "").strip()
if password and not st.session_state.get("access", False):
    with st.form("login"):
        entered = st.text_input("Mật khẩu truy cập", type="password")
        ok = st.form_submit_button("Đăng nhập")
    if ok:
        if hmac.compare_digest(entered, password):
            st.session_state["access"] = True
            st.rerun()
        st.error("Mật khẩu không đúng.")
    st.stop()
with st.sidebar:
    st.header("Cấu hình")
    server_key = os.getenv("GEMINI_API_KEY", "").strip()
    if server_key:
        st.success("Đã có API key bảo mật trên server")
    key = server_key or st.text_input("Gemini API key", type="password",
                                      help="Key chỉ dùng để gửi yêu cầu nghiên cứu, không đưa lên GitHub.")
    st.caption("Model mặc định: Gemini 3.8 Flash. Đã ngừng đặt Gemini 2.5 cho key mới.")
    model = st.selectbox("Gemini model", options=["Auto", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"], index=0)
    search = st.toggle("Google Search grounding (cần gói hỗ trợ)", value=False,
                       help="Các model Gemini 3.x hiện không hỗ trợ Google Search grounding ở Free Tier. Để tắt lỗi 403, để chế độ này OFF.")
    st.caption("Free Tier Gemini 3.x: chạy AI không bật Grounding; nếu cần tìm nguồn web tự động, tài khoản Google API có thể phải kích hoạt thanh toán.")
    if st.button("🔍 Kiểm tra API & model khả dụng"):
        if not key:
            st.error("Chưa có GEMINI_API_KEY.")
        else:
            try:
                known = available_text_models(genai.Client(api_key=key))
                if known:
                    st.success("Kết nối model list thành công. Có " + str(len(known)) + " text models.")
                    st.write(", ".join(known[:20]))
                else:
                    st.warning("Không thấy text models phù hợp trên key này.")
            except Exception as exc:
                st.error("Không kiểm tra được danh sách model: " + str(exc)[:250])
with st.form("brief"):
    topic = st.text_area("Research brief", value="Phân tích thị trường điều hòa thông minh tại Việt Nam: category, consumer, competitors, trends và cơ hội định vị.", height=120)
    left, right = st.columns(2)
    with left:
        market = st.text_input("Thị trường", value="Việt Nam")
        audience = st.text_input("Target audience", value="18–34 tuổi")
    with right:
        brand = st.text_input("Brand / competitors", value="")
        period = st.text_input("Giai đoạn nghiên cứu", value="2024–2026")
    start = st.form_submit_button("🚀 Run Market Research", type="primary", use_container_width=True)
if start:
    if len(topic.strip()) < 5 or not market.strip() or not key:
        st.error("Cần Research brief, thị trường và Gemini API key.")
    else:
        with st.status("Multi-agent đang nghiên cứu...", expanded=True) as status:
            try:
                result = research(topic, market, audience, brand, period, key, model, search, status.write)
                st.session_state["result"] = result
                status.update(label="Đã hoàn thành!", state="complete", expanded=False)
            except Exception as error:
                status.update(label="Chạy nghiên cứu chưa thành công", state="error")
                st.error(str(error))
result = st.session_state.get("result")
if result:
    for warning in result["warnings"]:
        st.warning(warning)
    t1, t2, t3, t4 = st.tabs(["📄 Report", "🤖 Agents", "🛡️ Audit", "🔗 Sources"])
    with t1:
        st.markdown(linked(result["report"], result["sources"]))
    with t2:
        with st.expander("Research Planner"):
            st.markdown(result["plan"])
        for name, agent in result["agents"].items():
            with st.expander(name):
                st.markdown(agent["answer"] or agent["error"])
    with t3:
        st.markdown(linked(result["audit"], result["sources"]))
        st.caption("Evidence Auditor không thay thế việc đọc báo cáo gốc.")
    with t4:
        for src in result["sources"]:
            st.markdown("**" + src["id"] + "** — [" + src["title"] + "](" + src["url"] + ") · " + src["role"])
    md = "# Market Research: " + result["topic"] + "\n\n" + result["report"] + "\n\n## Evidence Audit\n\n" + result["audit"] + "\n\n## Sources\n"
    md += "\n".join("- [" + s["id"] + "] " + s["title"] + ": " + s["url"] for s in result["sources"])
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Markdown", md, "market_research.md", "text/markdown", use_container_width=True)
    with c2:
        st.download_button("⬇️ JSON", json.dumps(result, ensure_ascii=False, indent=2),
                           "market_research.json", "application/json", use_container_width=True)
st.caption("Desk research dựa trên nguồn công khai; chưa thay thế khảo sát hoặc phỏng vấn thực địa.")