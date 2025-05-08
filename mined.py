import streamlit as st
import json
import pdfplumber
import re
import google.generativeai as genai
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
from datetime import datetime
import tempfile
import matplotlib.pyplot as plt

API_KEY = st.secrets["API_KEY"]

genai.configure(api_key=API_KEY)

# Financial term dictionaries
RT = {
    "revenue from operations": 1, "Total Revenue": 2, "Turnover": 3, "Net Sales": 4,
    "Gross Revenue": 5, "Operating Revenue": 6, "Revenues": 7, "Receipts": 8,
    "Income from Operations": 9, "Business Income": 10, "Gross Sales": 11
}
OPT = {
    "Operating Profit": 1, "EBIT": 2, "Earnings Before Interest and Tax": 3, "Profit Before Tax": 4,
    "PBIT": 5, "Operating Income": 6, "Operating Earnings": 7, "Core Earnings": 8,
    "NOP": 9, "NOPAT": 10, "Operating Margin": 11, "Pre-Tax Operating Profit": 12
}
NPT = {
    "Net Profit": 1, "Net Income": 2, "Profit After Tax": 3, "PAT": 4,
    "Earnings After Tax": 5, "Final Profit": 6, "Net Earnings": 7,
    "Total Comprehensive Income": 8, "Post-Tax Profit": 9
}

def extract_dates_from_text(text):
    """Extract all dates from text and determine the latest quarter."""
    date_pattern = r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"
    dates = re.findall(date_pattern, text)
    formatted_dates = []
    
    for date_str in dates:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
            try:
                formatted_dates.append(datetime.strptime(date_str, fmt))
                break
            except ValueError:
                continue
    
    if not formatted_dates:
        return None, None
    
    sorted_dates = sorted(formatted_dates, reverse=True)
    
    latest_date = sorted_dates[0]
    latest_quarter = (latest_date.month - 1) // 3 + 1
    latest_year = latest_date.year
    
    previous_date = sorted_dates[1] if len(sorted_dates) > 1 else None
    previous_quarter = (previous_date.month - 1) // 3 + 1 if previous_date else None
    previous_year = previous_date.year if previous_date else None
    
    return f"Q{latest_quarter} {latest_year}", f"Q{previous_quarter} {previous_year}" if previous_date else None

def extract_table_or_text(pdf_path):
    """Extracts table data from PDF using pdfplumber. If no table, uses OCR."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    if any("Particulars" in str(cell) for cell in table[0] if cell):
                        print(f"Table found on page {page.page_number}")
                        return table
            print(f"No table found on page {page.page_number}. Using OCR...")
            text = extract_text_from_image(pdf_path, page.page_number)
            return text if text.strip() else None
    print("No tables or text found in the PDF.")
    return None

def extract_text_from_image(pdf_path, page_number):
    """Extracts text from an image-based PDF page using OCR."""
    images = convert_from_path(pdf_path, first_page=page_number, last_page=page_number)
    extracted_text = ""
    for img in images:
        text = pytesseract.image_to_string(img.convert("L"), config='--psm 6')
        extracted_text += text + "\n"
    return extracted_text.strip()

def extract_financial_values(table):
    """Extract financial values for current quarter and annual data."""
    extracted_data = {
        "Current Quarter": {"Revenue": None, "Operating Profit": None, "Net Profit": None},
        "Annual Data": {"Revenue": None, "Operating Profit": None, "Net Profit": None}
    }
    if not table:
        return extracted_data
    
    header = table[0]
    current_quarter_col_index = None
    annual_col_index = None
    
    for i, cell in enumerate(header):
        if cell and "Particular" in str(cell):
            current_quarter_col_index = i + 1
        if cell and "year ended" in str(cell).lower():
            annual_col_index = i
    
    if current_quarter_col_index is None or annual_col_index is None:
        return extracted_data
    
    def select_highest_priority(term_dict, row_text):
        if row_text is None:
            return None
        matches = [(term, priority) for term, priority in term_dict.items() if term.lower() in row_text.lower()]
        return min(matches, key=lambda x: x[1])[0] if matches else None
    
    for row in table:
        if not row or row[0] is None:
            continue
        
        revenue_match = select_highest_priority(RT, row[0])
        op_profit_match = select_highest_priority(OPT, row[0])
        net_profit_match = select_highest_priority(NPT, row[0])
        
        if revenue_match:
            extracted_data["Current Quarter"]["Revenue"] = float(row[current_quarter_col_index].replace(",", "")) if current_quarter_col_index < len(row) and row[current_quarter_col_index] else None
            extracted_data["Annual Data"]["Revenue"] = float(row[annual_col_index].replace(",", "")) if annual_col_index < len(row) and row[annual_col_index] else None
        if op_profit_match:
            extracted_data["Current Quarter"]["Operating Profit"] = float(row[current_quarter_col_index].replace(",", "")) if current_quarter_col_index < len(row) and row[current_quarter_col_index] else None
            extracted_data["Annual Data"]["Operating Profit"] = float(row[annual_col_index].replace(",", "")) if annual_col_index < len(row) and row[annual_col_index] else None
        if net_profit_match:
            extracted_data["Current Quarter"]["Net Profit"] = float(row[current_quarter_col_index].replace(",", "")) if current_quarter_col_index < len(row) and row[current_quarter_col_index] else None
            extracted_data["Annual Data"]["Net Profit"] = float(row[annual_col_index].replace(",", "")) if annual_col_index < len(row) and row[annual_col_index] else None
    
    return extracted_data

def use_gemini_extraction(text):
    """Use Gemini AI to extract financial data dynamically."""
    prompt = f"""
    Identify the latest quarters' financial data and annual data, and extract values for:
    1. Revenue
    2. Operating Profit
    3. Net Profit
    4. Financial Unit (Crores, Lakhs, Millions, Billions)
    5. Company Name
    Search for heading "Statement of" and find the latest quarter and annual financial data (column marked with 'year ended').
    Financial unit will be mentioned above the table.
    Provide output in JSON:
    {{
      "Company Name": "Detected company name",
      "Current Quarter": {{
        "Revenue": X,
        "Operating Profit": Y,
        "Net Profit": Z,
        "Unit": "Detected financial unit"
      }},
      "Annual Data": {{
        "Year": "YYYY",
        "Revenue": D,
        "Operating Profit": E,
        "Net Profit": F,
        "Unit": "Detected financial unit"
      }}
    }}
    Text to analyze:
    {text}
    """
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    
    try:
        json_match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        return None
    return None

def detect_fin_unit(text):
    """Detect financial unit from the extracted text."""
    units = ["Crores", "Lakhs", "Millions", "Billions"]
    for unit in units:
        if unit.lower() in text.lower():
            return unit
    return "Unknown"

def extract_company_name(text):
    """Attempts to extract the company name from the document."""
    match = re.search(r"(?i)(?:Company Name|Statement of|Financial Report of)\s*[:\-\s]*([A-Za-z0-9&.,\s]+)", text)
    return match.group(1).strip() if match else "Unknown Company"

def extract_fin_data(pdf_path):
    """Main function to extract financial data."""
    extracted_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            extracted_text += page.extract_text() or ""
    
    st.session_state.full_financial_text = extracted_text
    
    if not extracted_text.strip():
        return {"error-status": 404, "message": "No financial data found in the document."}
    
    current_quarter, previous_quarter = extract_dates_from_text(extracted_text)
    fin_unit = detect_fin_unit(extracted_text)
    
    table = extract_table_or_text(pdf_path)
    fin_data = extract_financial_values(table)
    
    company_name = extract_company_name(extracted_text)
    
    if not any(fin_data["Current Quarter"].values()):
        ai_data = use_gemini_extraction(extracted_text) or {}
        fin_data["Current Quarter"].update(ai_data.get("Current Quarter", {}))
        fin_data["Annual Data"].update(ai_data.get("Annual Data", {}))
        company_name = ai_data.get("Company Name", company_name)
    
    if not any(fin_data["Current Quarter"].values()) and not any(fin_data["Annual Data"].values()):
        return {"error-status": 404, "message": "No financial data found in the document."}
    
    fin_data["Annual Data"]["Year"] = re.search(r"\b\d{4}\b", extracted_text).group() if re.search(r"\b\d{4}\b", extracted_text) else "Unknown Year"
    fin_data["Current Quarter"]["Unit"] = fin_unit
    fin_data["Annual Data"]["Unit"] = fin_unit
    fin_data["Company Name"] = company_name
    
    return fin_data

def plot_comparison(data):
    """Plot a comparison bar chart and trend line for financial data."""
    metrics = ["Revenue", "Operating Profit", "Net Profit"]
    current_values = [data["Current Quarter"].get(metric, 0) or 0 for metric in metrics]
    annual_values = [data["Annual Data"].get(metric, 0) or 0 for metric in metrics]
    
    fig, ax = plt.subplots(2, 1, figsize=(8, 10))
    
    x = range(len(metrics))
    ax[0].bar(x, current_values, width=0.4, label="Current Quarter", align="center", color="blue")
    ax[0].bar(x, annual_values, width=0.4, label="Annual Data", align="edge", color="green")
    ax[0].set_xticks(x)
    ax[0].set_xticklabels(metrics)
    ax[0].set_ylabel("Amount")
    ax[0].set_title("Comparison: Current Quarter vs Annual Data")
    ax[0].legend()
    
    try:
        time_periods = ["Q1", "Q2", "Q3", "Q4", "Annual"]
        revenue_trend = [100, 120, 140, 160, data["Annual Data"].get("Revenue", 0) or 0]
        profit_trend = [20, 25, 30, 35, data["Annual Data"].get("Operating Profit", 0) or 0]
        net_profit_trend = [10, 12, 14, 18, data["Annual Data"].get("Net Profit", 0) or 0]
        
        ax[1].plot(time_periods, revenue_trend, marker="o", linestyle="-", color="blue", label="Revenue Trend")
        ax[1].plot(time_periods, profit_trend, marker="o", linestyle="-", color="green", label="Operating Profit Trend")
        ax[1].plot(time_periods, net_profit_trend, marker="o", linestyle="-", color="red", label="Net Profit Trend")
        
        ax[1].set_ylabel("Amount")
        ax[1].set_title("Financial Performance Trend Over Quarters")
        ax[1].legend()
    except Exception as e:
        print(f"Error generating trend chart: {e}")
    
    return fig

def generate_chatbot_response(user_query, financial_data, full_text):
    """Generate chatbot responses based on financial data and PDF text."""
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    context = f"""
    Financial data for {financial_data.get('Company Name', 'Unknown Company')}:
    
    Current Quarter Data:
    - Revenue: {financial_data['Current Quarter'].get('Revenue')} {financial_data['Current Quarter'].get('Unit')}
    - Operating Profit: {financial_data['Current Quarter'].get('Operating Profit')} {financial_data['Current Quarter'].get('Unit')}
    - Net Profit: {financial_data['Current Quarter'].get('Net Profit')} {financial_data['Current Quarter'].get('Unit')}
    
    Annual Data:
    - Year: {financial_data['Annual Data'].get('Year')}
    - Revenue: {financial_data['Annual Data'].get('Revenue')} {financial_data['Annual Data'].get('Unit')}
    - Operating Profit: {financial_data['Annual Data'].get('Operating Profit')} {financial_data['Annual Data'].get('Unit')}
    - Net Profit: {financial_data['Annual Data'].get('Net Profit')} {financial_data['Annual Data'].get('Unit')}
    
    Relevant text from financial statement (truncated):
    {full_text[:2000]}
    """
    
    prompt = f"""
    You are a financial assistant. Based on the following financial data and the user's question, provide a concise, informative answer.
    
    {context}
    
    User Question: {user_query}
    
    If the answer is not available in the data, indicate so and suggest what information is needed.
    """
    
    response = model.generate_content(prompt)
    return response.text

def main():
    st.set_page_config(
        page_title="Wealth$cribe",
        layout="wide",
        page_icon="logo1.png"
    )
    
    st.markdown(
        """
        <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .navbar {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                background-color: white;
                color: black;
                padding: 15px 20px;
                font-size: 22px;
                font-weight: bold;
                z-index: 1000;
                box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                display: flex;
                align-items: center;
            }
            .logo-container {
                position: relative;
                font-weight: bold;
                font-size: 24px;
                margin-left: 20px;
                display: flex;
                align-items: center;
                flex-direction: column;
            }
            .spikes {
                display: flex;
                justify-content: center;
                gap: 4px;
                width: fit-content;
                margin: 0 auto;
            }
            .spike {
                width: 6px;
                background-color: green;
                transform-origin: bottom;
                animation: spike-grow 2s cubic-bezier(0.45, 0, 0.55, 1) infinite alternate;
            }
            .spike-container {
                display: flex;
                justify-content: center;
                align-items: center;
                width: fit-content;
                margin: auto;
                margin-bottom: -5px;
            }
            .spike:nth-child(1) { animation-delay: -1.2s; }
            .spike:nth-child(2) { animation-delay: -0.5s; }
            .spike:nth-child(3) { animation-delay: -0.8s; }
            .spike:nth-child(4) { animation-delay: -1.1s; }
            .spike:nth-child(5) { animation-delay: -1.4s; }
            .spike:nth-child(6) { animation-delay: -1.7s; }
            .spike:nth-child(7) { animation-delay: -2.0s; }
            .spike:nth-child(8) { animation-delay: -2.3s; }
            .spike:nth-child(9) { animation-delay: -2.6s; }
            .spike:nth-child(10) { animation-delay: -2.9s; }
            .spike:nth-child(11) { animation-delay: 0.1s; }
            @keyframes spike-grow {
                0% { height: 20px; transform: scaleY(1); }
                50% { height: 20px; transform: scaleY(0.6); }
                100% { height: 20px; transform: scaleY(0.9); }
            }
            .grass-container {
                position: absolute;
                bottom: 0;
                left: 0;
                width: 100%;
                height: 8px;
                overflow: hidden;
            }
            .grass {
                position: absolute;
                bottom: 0;
                left: 0;
                width: 100%;
                height: 8px;
                background: linear-gradient(90deg, transparent, green, transparent);
                animation: grass-move 2s linear forwards;
            }
            @keyframes grass-move {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(0%); }
            }
            .chat-container {
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                padding: 15px;
                background-color: #f9f9f9;
                max-height: 500px;
                overflow-y: auto;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }
            .user-message {
                background-color: #dcf8c6;
                padding: 10px;
                border-radius: 10px;
                margin: 5px 0;
                text-align: right;
                max-width: 80%;
                margin-left: auto;
            }
            .bot-message {
                background-color: white;
                padding: 10px;
                border-radius: 10px;
                margin: 5px 0;
                max-width: 80%;
            }
            .chat-input {
                border: 2px solid #4CAF50 !important;
                border-radius: 5px !important;
                padding: 8px !important;
                width: 100% !important;
                margin-top: 10px !important;
            }
            .content-container {
                margin-top: 60px;
            }
        </style>
        <div class="navbar">
            <div class="logo-container">
                <div class="spike-container">
                    <div class="spikes">
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                        <div class="spike"></div>
                    </div>
                </div>
                Wealth$cribe
            </div>
            <div class="grass-container">
                <div class="grass"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <style>
            h1 {
                font-size: 32px !important;
                color: rgb(0, 0, 0) !important;
                text-align: center !important;
                text-decoration: none !important;
                pointer-events: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    st.title("Financial Data Extractor")
    
    if "uploaded_file_path" not in st.session_state:
        st.session_state.uploaded_file_path = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "full_financial_text" not in st.session_state:
        st.session_state.full_financial_text = ""
    if "financial_data" not in st.session_state:
        st.session_state.financial_data = None
    if "page" not in st.session_state:
        st.session_state.page = "upload"
    
    if st.session_state.page == "upload":
        st.markdown(
            """
            <style>
                .custom-text {
                    font-size: 18px;
                    font-weight: bold;
                    color: #2E7D32;
                    text-align: center;
                    background-color: #f0fff0;
                    padding: 10px;
                    border-radius: 8px;
                }
                button[data-testid="stBaseButton-secondary"],
                div[data-testid="stFileUploaderDropzoneInstructions"] {
                    display: none !important;
                }
                section[data-testid="stFileUploaderDropzone"] {
                    border: 3px dashed #4CAF50 !important;
                    padding: 30px !important;
                    border-radius: 12px !important;
                    background-color: rgb(255, 255, 255) !important;
                    width: 80% !important;
                    min-height: 180px !important;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: auto;
                    transition: all 0.3s ease-in-out;
                    position: relative;
                    text-align: center;
                }
                section[data-testid="stFileUploaderDropzone"]:hover {
                    background-color: #e6ffe6 !important;
                    border-color: #2E7D32 !important;
                }
                section[data-testid="stFileUploaderDropzone"]::before {
                    content: "";
                    display: block;
                    width: 80px;
                    height: 80px;
                    background-image: url('https://www.svgrepo.com/show/324032/leaf-upload.svg');
                    background-size: cover;
                    background-repeat: no-repeat;
                    margin: auto;
                    position: absolute;
                    top: 20px;
                }
                section[data-testid="stFileUploaderDropzone"]::after {
                    content: "Drag & Drop your Financial PDF here or Click to Upload";
                    font-size: 18px;
                    font-weight: bold;
                    color: #2E7D32;
                    display: block;
                    margin-top: 80px;
                }
            </style>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown('<p class="custom-text">Upload a financial statement PDF to extract and analyze data.</p>', unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader("", type="pdf")
        
        if uploaded_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getbuffer())
                st.session_state.uploaded_file_path = tmp_file.name
            st.session_state.page = "results"
            st.rerun()
    
    elif st.session_state.page == "results":
        if not st.session_state.uploaded_file_path:
            st.error("No file uploaded! Please upload a PDF first.")
            return
        
        if st.session_state.financial_data is None:
            st.session_state.financial_data = extract_fin_data(st.session_state.uploaded_file_path)
        
        extracted_data = st.session_state.financial_data
        
        if "error-status" in extracted_data:
            st.error(extracted_data["message"])
            return
        
        # Create two columns for results and chatbot
        col1, col2 = st.columns([3, 2])
        
        with col1:
            st.markdown('<div class="content-container">', unsafe_allow_html=True)
            company_name = extracted_data.get("Company Name", "Unknown Company")
            st.write(f"### Company Name: {company_name}")
            
            net_profit = extracted_data["Current Quarter"].get("Net Profit")
            if net_profit is not None:
                try:
                    if float(net_profit) >= 0:
                        st.success(f"{company_name} is in Profit")
                    else:
                        st.error(f"{company_name} is in Loss")
                except ValueError:
                    st.warning("Unable to determine profit/loss due to invalid Net Profit value.")
            else:
                st.warning("Net Profit data is missing.")
            
            st.write("### Current Quarter Data")
            st.table(extracted_data["Current Quarter"])
            
            st.write("### Annual Data")
            st.table(extracted_data["Annual Data"])
            
            st.write("### Comparison: Current Quarter vs Annual Data")
            fig = plot_comparison(extracted_data)
            st.pyplot(fig)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="content-container">', unsafe_allow_html=True)
            st.write("### Financial Assistant")
            st.write("Ask questions about the financial data:")
            
            chat_container = st.container()
            with chat_container:
                st.markdown('<div class="chat-container">', unsafe_allow_html=True)
                for message in st.session_state.chat_history:
                    if message["role"] == "user":
                        st.markdown(f'<div class="user-message">{message["content"]}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="bot-message">{message["content"]}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
            user_query = st.text_input("", placeholder="Type your question here...", key="chat_input", help="Ask about revenue, profit, etc.")

            # Initialize the flag
            if "last_handled_query" not in st.session_state:
                st.session_state.last_handled_query = ""

            # Process only if the query is new
            if user_query and user_query != st.session_state.last_handled_query:
                st.session_state.chat_history.append({"role": "user", "content": user_query})
                response = generate_chatbot_response(user_query, extracted_data, st.session_state.full_financial_text)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.session_state.last_handled_query = user_query
                st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown(
        """
        <style>
            .footer {
                position: relative;
                width: 100%;
                margin-top: 10px;
                height: auto;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .footer-text {
                font-size: 14px;
                font-weight: bold;
                color: #2E7D32;
                text-align: center;
            }
        </style>
        <div class="footer">
            <div class="footer-text">
                © 2025 Wealth$cribe. All Rights Reserved.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()