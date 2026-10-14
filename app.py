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

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
CRITIQUE_ROUNDS = 3
INSIGHTS_PER_SECTION = 5
REPORT_SECTIONS = (
    "Executive Summary",
    "Market Landscape",
    "Consumer Insights",
    "Competitor Analysis",
    "Trends & PESTEL",
    "SWOT Analysis",
    "Strategic Opportunities",
    "Recommendations",
    "Limitations & Data Gaps",
)
REPORT_FORMAT_GUIDE = """
ĐỊNH DẠNG BẮT BUỘC CHO MỌI MỤC CỦA BÁO CÁO:
- Phải có ĐỦ 9 mục theo ĐÚNG tên và thứ tự của REPORT_SECTIONS, mỗi mục dùng heading Markdown cấp 2: '## 1. Executive Summary', '## 2. Market Landscape', ... '## 9. Limitations & Data Gaps'.
- TRONG MỖI MỤC: tiêu đề '**Research Insights**', sau đó TỐI THIỂU 5 insight KHÁC NHAU (nghĩa là hơn 4 ý). Viết đúng mẫu mỗi ý trên một dòng:
- **Insight 1:** [Fact / Inference / Evidence Gap] nội dung cụ thể.
- **Insight 2:** [Fact / Inference / Evidence Gap] nội dung cụ thể.
...
- **Insight 5:** [Fact / Inference / Evidence Gap] nội dung cụ thể.
- KẾT THÚC MỖI MỤC bằng MỘT dòng '**Key Takeaway:**' chứa ĐÚNG MỘT CÂU kết luận đắt giá, súc tích, có ý nghĩa chiến lược; không thêm nội dung sau takeaway trong cùng mục.
- Có thể thêm bảng, dữ liệu định lượng và giải thích NGẮN trước Research Insights; đối với đối thủ nên thêm bảng comparison nếu chứng cứ cho phép.
- Mỗi insight có thể kèm mã nguồn [S#] HỢP LỆ nếu có bằng chứng. Không tự tạo URL/mã nguồn/số liệu, không biến assumption thành fact, không lặp ý chỉ để đủ 5. Khi thiếu chứng cứ, phân tích 5 góc độ GIỚI HẠN thông tin khác nhau, ghi rõ [Evidence Gap] thay vì tưởng tượng.
- Key Takeaway không phải một ý Research Insight mới. Không được gộp các mục, không được bỏ mục vì thiếu dữ liệu.
Tên 9 mục: Executive Summary; Market Landscape; Consumer Insights; Competitor Analysis; Trends & PESTEL; SWOT Analysis; Strategic Opportunities; Recommendations; Limitations & Data Gaps.
"""
PREFERRED_MODELS = ("gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash")

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
QUAN TRỌNG: chỉ đánh dấu nguồn bằng [S1], [S2], ... từ danh mục có thật trong evidence. Không tạo nguồn, URL, tỷ lệ hay thị phần. Mọi số liệu quan trọng cần kèm nguồn hợp lệ. Phân biệt fact / inference / hypothesis. Khi không có đủ chứng cứ, ghi rõ thiếu dữ liệu. TUÂN THỦ REPORT_FORMAT_GUIDE và đủ 5 insight khác nhau + một Key Takeaway cuối mỗi mục."""
AUDIT = """Bạn là Evidence Auditor độc lập. Kiểm tra tối thiểu 5 kết luận và số liệu quan trọng. Đánh dấu Supported / Weak / Unverified; nói rõ các trường hợp thiếu năm, khu vực, định nghĩa, lỗi suy luận, sai mã nguồn. Không tự nhận đã mở toàn bộ tài liệu. Kết luận cần kiểm tra gì trước khi pitching."""

CRITIC = """Bạn là Critical Reviewer Agent, độc lập và có nhiệm vụ CHẤT VẤN bản báo cáo market research trước khi phát hành.
Hãy đóng vai người phản biện khó tính, KHÔNG mặc định đồng ý với báo cáo.
Kiểm tra: (1) sự đúng đắn của số liệu, định nghĩa, mốc thời gian và địa lý; (2) mã nguồn [S#] có nằm trong danh mục nguồn cung cấp không, có khớp với khẳng định không; (3) phân biệt evidence và suy luận; (4) logic nhân-quả, sự thiên lệch, đối thủ bị bỏ sót; (5) customer insights có đủ bằng chứng; (6) tính khả thi, hạn chế và ưu tiên của khuyến nghị.
Không sáng tạo nguồn, URL hoặc số liệu; không tuyên bố đã trực tiếp kiểm tra website hay tài liệu gốc. Nếu không có grounding, nêu rõ giới hạn xác minh.
Trả về tiếng Việt, gồm: Verdict (Ready / Needs revision / High risk), Các vấn đề xếp hạng P0/P1/P2 với trích đoạn báo cáo cần sửa, lý do, hành động sửa cụ thể, Các luận điểm có đủ chứng cứ, Những gì vẫn chưa thể xác minh.
BẮT BUỘC phản biện chất lượng cấu trúc theo từng mục: báo cáo có đúng 9 headings, tối thiểu 5 Research Insights khác biệt trong MỖI mục, và đúng một câu Key Takeaway ở cuối MỖI mục không? Nếu thiếu, ghi lỗi P1 kèm tên mục, số lượng thiếu và cách khắc phục, không tự bịa thêm số liệu.
Đây là vòng phản biện bắt buộc: ngay cả khi không thấy lỗi nghiêm trọng, hãy nêu các giả định cần làm rõ. Đánh giá BẢN HIỆN TẠI, không phải bản nháp cũ."""

REVISE = """Bạn là Strategy Synthesizer được giao sửa bản báo cáo sau phản biện độc lập.
Viết lại TOÀN BỘ báo cáo tiếng Việt đã chỉnh sửa, giữ cấu trúc Executive Summary, Market Landscape, Consumers, Competitor Comparison, Trends, SWOT, Strategic Opportunities, Recommendations, Limitations.
Giải quyết từng vấn đề P0/P1/P2 hợp lý; nếu thiếu dữ liệu để khắc phục thì hạ mức khẳng định và đưa vào Limitations, TUYỆT ĐỐI không sáng tác thông tin, số liệu hay nguồn.
Chỉ sử dụng chứng cứ research được cung cấp, chỉ trích nguồn bằng [S#] có trong danh mục. Không biến giả thuyết thành dữ kiện. Không đổi phạm vi ngành, địa lý, target hoặc giai đoạn. Báo cáo cần hoàn chỉnh và có thể đứng độc lập; không trả về danh sách thay đổi hoặc nhận xét về việc sửa. Giữ ĐÚNG đủ 9 mục, mỗi mục có ÍT NHẤT 5 Research Insights khác nhau và kết thúc bằng MỘT câu **Key Takeaway:** đúng REPORT_FORMAT_GUIDE."""


def validate_report_structure(report):
    """Mechanical format QA; checks headings, insight count/order, and one takeaway per section."""
    issues = []
    header_matches = list(re.finditer(r"(?m)^##\s*(?:\d+\s*[.)]\s*)?([^\n#]+?)\s*$", report))
    found = {}
    for idx, hit in enumerate(header_matches):
        title = hit.group(1).strip()
        if title in REPORT_SECTIONS:
            end = header_matches[idx + 1].start() if idx + 1 < len(header_matches) else len(report)
            if title in found:
                issues.append("Mục '" + title + "' xuất hiện nhiều lần.")
            else:
                found[title] = report[hit.end():end]

    for title in REPORT_SECTIONS:
        if title not in found:
            issues.append("Thiếu mục: " + title)
            continue
        content = found[title]
        marker = re.search(r"(?mi)^\s*\*\*Research Insights\*\*\s*$", content)
        takeaway_lines = re.findall(
            r"(?mi)^\s*\*\*Key Takeaway:\*\*\s*(.*?)\s*$", content
        )
        if not marker:
            issues.append(title + ": thiếu heading **Research Insights**.")
            continue
        # Only count properly numbered insights between the insights header and takeaway.
        endpos = re.search(r"(?mi)^\s*\*\*Key Takeaway:\*\*", content)
        if endpos is None:
            issues.append(title + ": thiếu dòng **Key Takeaway:**.")
            insight_text = content[marker.end():]
        else:
            insight_text = content[marker.end():endpos.start()]
        insight_numbers = [int(n) for n in re.findall(
            r"(?mi)^\s*[-*]\s+\*\*Insight\s+(\d+):\*\*\s*\S.+$", insight_text
        )]
        if len(insight_numbers) < INSIGHTS_PER_SECTION or insight_numbers != list(range(1, len(insight_numbers) + 1)):
            issues.append(
                title + ": Research Insights phải có ít nhất " + str(INSIGHTS_PER_SECTION)
                + " ý đánh số liên tục theo mẫu '- **Insight N:**'; hiện là "
                + str(insight_numbers) + "."
            )
        if len(takeaway_lines) != 1 or not takeaway_lines[0].strip():
            issues.append(title + ": cần đúng một Key Takeaway không rỗng.")
        elif endpos is not None:
            after = content[endpos.end():].strip()
            # The takeaway must be the last nonempty line of its section.
            if len(after.splitlines()) > 1:
                issues.append(title + ": Key Takeaway chưa nằm ở cuối mục.")
            takeaway = takeaway_lines[0].strip()
            if not takeaway.endswith((".", "!", "?")):
                issues.append(title + ": Key Takeaway cần là một câu hoàn chỉnh kết thúc bằng dấu câu.")
            # Multiple sentence boundaries are usually a sign of an overly long takeaway.
            if re.search(r"[.!?]\s+\S", takeaway):
                issues.append(title + ": Key Takeaway dài hơn một câu.")
    return issues


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
    progress("1/7 — Research Planner...")
    _, plan = request(client, selected_model, PLAN + "\n\n" + context, max_tokens=1500)
    progress("2/7 — 4 Research Agents (song song tối đa 2)...")
    def do_role(name, directive):
        prompt = ("Vai trò: " + name + ". " + directive
                  + "\nTrình bày tối thiểu 5 Research Insights DISTINCT có evidence, giới hạn và implications theo mẫu '- **Insight 1:** ...', ... '- **Insight 5:** ...'; chốt bằng một câu **Key Takeaway:**."
                  + " Nếu không biết hoặc thiếu nguồn, ghi CHƯA KIỂM CHỨNG và mô tả đúng research gap. KHÔNG sáng tác số liệu."
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
    progress("3/7 — Strategy Synthesizer tạo báo cáo ban đầu...")
    combined = "\n\n".join(evidence)
    _, report = request(client, selected_model, SYNTH + "\n" + REPORT_FORMAT_GUIDE + "\n" + context + "\n" + combined[:45000], max_tokens=11000)
    original_report = report
    refs = "\n".join("[" + s["id"] + "] " + s["title"] + " " + s["url"] for s in sources)
    # Strictly sequential: Critic_i -> Revise_i -> Critic_(i+1). Never finalize an unchecked revision.
    review_history = []
    for iteration in range(1, CRITIQUE_ROUNDS + 1):
        progress(f"{iteration + 3}/7 — Critical Reviewer: vòng {iteration}/{CRITIQUE_ROUNDS}...")
        history = "\n\n".join(
            f"Vòng {entry['round']}:\n{entry['critique'][:2600]}"
            for entry in review_history
        )
        critic_prompt = (
            CRITIC + "\n\n" + REPORT_FORMAT_GUIDE + "\n\nRESEARCH BRIEF:\n" + context
            + "\n\nEVIDENCE GỐC (chỉ dữ liệu này làm căn cứ):\n" + combined[:38000]
            + "\n\nDANH MỤC MÃ NGUỒN HỢP LỆ:\n" + (refs or "KHÔNG CÓ")
            + "\n\nNHỮNG PHẢN BIỆN VÒNG TRƯỚC (để không lặp máy móc):\n"
            + (history[:6000] or "Chưa có")
            + "\n\nBÁO CÁO CẦN PHẢN BIỆN VÒNG NÀY:\n" + report[:28000]
        )
        _, critique = request(client, selected_model, critic_prompt, max_tokens=4500)
        progress(f"{iteration + 3}/7 — Strategy Synthesizer chỉnh sửa sau vòng {iteration}/{CRITIQUE_ROUNDS}...")
        revision_prompt = (
            REVISE + "\n\n" + REPORT_FORMAT_GUIDE + "\n\nRESEARCH BRIEF:\n" + context
            + "\n\nEVIDENCE GỐC:\n" + combined[:38000]
            + "\n\nDANH MỤC MÃ NGUỒN HỢP LỆ:\n" + (refs or "KHÔNG CÓ")
            + "\n\nBÁO CÁO HIỆN TẠI:\n" + report[:28000]
            + "\n\nPHẢN BIỆN CẦN XỬ LÝ:\n" + critique[:15000]
        )
        _, revised_report = request(client, selected_model, revision_prompt, max_tokens=11000)
        if not revised_report.strip():
            raise RuntimeError(f"Vòng phản biện {iteration}: model không trả về báo cáo sửa. Dừng, không finalize.")
        report = revised_report
        review_history.append({"round": iteration, "critique": critique, "revised_report": report})
    # Exactly three critique/revision loops have finished; formatting repair is NOT another critique round.
    format_issues = validate_report_structure(report)
    for repair_number in range(1, 3):
        if not format_issues:
            break
        progress(f"Kiểm tra bố cục: đang sửa {len(format_issues)} lỗi (lượt {repair_number}/2)...")
        repair_prompt = (
            "Bạn là Report Structure Formatter, không phải Critical Reviewer. Không thêm một vòng phản biện."
            + "\nSửa TOÀN BỘ Markdown báo cáo theo layout BẮT BUỘC sau. Trả về chỉ toàn bộ báo cáo, không giải thích."
            + "\n\n" + REPORT_FORMAT_GUIDE
            + "\n\nNHỮNG LỖI ĐỊNH DẠNG TỰ ĐỘNG PHÁT HIỆN:\n- " + "\n- ".join(format_issues)
            + "\n\nRESEARCH BRIEF:\n" + context
            + "\n\nEVIDENCE VÀ NGUỒN GỐC (CHỈ DÙNG NHỮNG DỮ LIỆU NÀY):\n" + combined[:34000]
            + "\n\nDANH MỤC SOURCE ID HỢP LỆ:\n" + (refs or "KHÔNG CÓ")
            + "\n\nREPORT HIỆN TẠI:\n" + report[:32000]
        )
        _, candidate_report = request(client, selected_model, repair_prompt, max_tokens=11000)
        report = candidate_report
        format_issues = validate_report_structure(report)
    if format_issues:
        raise RuntimeError(
            "Báo cáo chưa đạt yêu cầu 5 Research Insights + 1 Key Takeaway cho từng mục sau 3 vòng phản biện. "
            + "Không finalize để tránh thiếu thông tin. Lỗi: " + " | ".join(format_issues)[:1100]
        )
    progress("7/7 — Evidence Auditor kiểm tra bản cuối sau 3 vòng phản biện...")
    _, audit = request(client, selected_model, AUDIT + "\nBRIEF:\n" + context
                       + "\nREPORT FINAL SAU 3 VÒNG PHẢN BIỆN:\n" + report[:28000]
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
            "model": selected_model, "available_models": permitted_models,
            "plan": plan, "agents": results, "initial_report": original_report,
            "review_history": review_history, "critique_rounds_completed": len(review_history),
            "report": report, "report_structure_valid": True,
            "insights_required_per_section": INSIGHTS_PER_SECTION,
            "report_sections": list(REPORT_SECTIONS),
            "audit": audit, "sources": sources, "warnings": warnings}

def linked(text, sources):
    by_id = {s["id"]: s["url"] for s in sources}
    return re.sub(r"\[(S\d+)\](?!\()", lambda m: "[" + m.group(1) + "](" + by_id[m.group(1)] + ")" if m.group(1) in by_id else m.group(0), text)

st.set_page_config(page_title="Market Research AI Lab", page_icon="📊", layout="wide")
st.title("📊 Market Research AI Lab")
st.caption("8 Gemini agents · 3 vòng phản biện · Mỗi mục ≥5 Research Insights + 1 Key Takeaway")
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
    st.caption("Mặc định Free Tier: Gemini 3.5 Flash-Lite. Nếu API key không hỗ trợ, hệ thống sẽ tự chọn model khả dụng khác.")
    model = st.selectbox("Gemini model", options=["gemini-3.5-flash-lite", "Auto", "gemini-3.6-flash", "gemini-3.8-flash"], index=0)
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
    t1, t2, t3, t4, t5 = st.tabs(["📄 Final report", "🔁 Phản biện (3 vòng)", "🤖 Agents", "🛡️ Audit", "🔗 Sources"])
    with t1:
        st.success(f"Đã hoàn tất {result.get('critique_rounds_completed', 0)}/3 vòng phản biện; mỗi mục ≥{result.get('insights_required_per_section', 5)} Research Insights + một câu Key Takeaway (đã kiểm tra format).")
        st.markdown(linked(result["report"], result["sources"]))
    with t2:
        st.markdown("### Critical Reviewer Agent — 3 vòng phản biện độc lập")
        st.caption("Mỗi vòng xem xét phiên bản mới nhất, đưa phản biện rồi Strategy Synthesizer sửa toàn bộ báo cáo.")
        with st.expander("Báo cáo ban đầu (trước phản biện)"):
            st.markdown(linked(result.get("initial_report", ""), result["sources"]))
        for entry in result.get("review_history", []):
            with st.expander(f"Vòng {entry['round']}/3 — Phản biện và bản sửa", expanded=False):
                st.markdown("**Nhận xét từ Critical Reviewer**")
                st.markdown(linked(entry["critique"], result["sources"]))
                st.divider()
                st.markdown(f"**Báo cáo sau khi sửa vòng {entry['round']}**")
                st.markdown(linked(entry["revised_report"], result["sources"]))
    with t3:
        with st.expander("Research Planner"):
            st.markdown(result["plan"])
        for name, agent in result["agents"].items():
            with st.expander(name):
                st.markdown(agent["answer"] or agent["error"])
    with t4:
        st.markdown(linked(result["audit"], result["sources"]))
        st.caption("Evidence Auditor kiểm tra bản sau vòng phản biện thứ 3; không thay thế việc đọc báo cáo gốc.")
    with t5:
        for src in result["sources"]:
            st.markdown("**" + src["id"] + "** — [" + src["title"] + "](" + src["url"] + ") · " + src["role"])
    md = "# Market Research: " + result["topic"] + "\n\n" + result["report"]
    md += "\n\n## Evidence Audit\n\n" + result["audit"]
    md += "\n\n## Critical review log (3 vòng)"
    for entry in result.get("review_history", []):
        md += "\n\n### Vòng " + str(entry["round"]) + " — phản biện\n\n" + entry["critique"]
    md += "\n\n## Sources\n" + "\n".join("- [" + s["id"] + "] " + s["title"] + ": " + s["url"] for s in result["sources"])
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Markdown", md, "market_research.md", "text/markdown", use_container_width=True)
    with c2:
        st.download_button("⬇️ JSON", json.dumps(result, ensure_ascii=False, indent=2),
                           "market_research.json", "application/json", use_container_width=True)
st.caption("Desk research dựa trên nguồn công khai; chưa thay thế khảo sát hoặc phỏng vấn thực địa.")