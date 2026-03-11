import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import datetime
import pandas as pd
import json
import os
import re
from fpdf import FPDF

# --- CONFIGURATION ---
SECRET_KEY_NAME = "gcp_service_account"
LOCAL_SERVICE_ACCOUNT_FILE = 'service_account.json'
# Updated to match your actual Google Sheet name
SPREADSHEET_NAME = 'AVL_Quote_Database'

def clean_json_string(json_str):
    """Removes control characters and invisible formatting from JSON strings."""
    return re.sub(r'[\x00-\x1F\x7F]', '', json_str)

def connect_to_sheets():
    """Establishes connection to the Google Sheet using Secrets or Local File."""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    try:
        if SECRET_KEY_NAME in st.secrets:
            raw_json = st.secrets[SECRET_KEY_NAME]
            cleaned_json = clean_json_string(raw_json)
            creds_info = json.loads(cleaned_json)
            credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        elif os.path.exists(LOCAL_SERVICE_ACCOUNT_FILE):
            credentials = Credentials.from_service_account_file(
                LOCAL_SERVICE_ACCOUNT_FILE, scopes=scopes
            )
        else:
            return None
        gc = gspread.authorize(credentials)
        return gc.open(SPREADSHEET_NAME).sheet1
    except Exception:
        return None

def get_next_quote_number(sheet):
    """Calculates the next AVL number based on the sheet history."""
    try:
        column_values = sheet.col_values(1)
        if len(column_values) <= 1:
            return "AVL-1000"
        last_entry = column_values[-1]
        if '-' in last_entry:
            last_num = int(last_entry.split('-')[1])
            return f"AVL-{last_num + 1}"
        return "AVL-1000"
    except:
        return "AVL-1000"

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'D&L AV - QUOTE', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def create_pdf(quote_num, client, project, parts_df, labor_df, totals):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Header Info
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Quote #: {quote_num}", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Date: {datetime.date.today().strftime('%B %d, %Y')}", ln=True)
    pdf.cell(0, 10, f"Client: {client}", ln=True)
    pdf.cell(0, 10, f"Project: {project}", ln=True)
    pdf.ln(10)

    # Equipment Table
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Parts & Equipment", ln=True)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(100, 8, "Description", 1)
    pdf.cell(20, 8, "Qty", 1)
    pdf.cell(35, 8, "Unit Price", 1)
    pdf.cell(35, 8, "Total", 1)
    pdf.ln()

    pdf.set_font("Arial", size=10)
    for _, row in parts_df.iterrows():
        desc = str(row.get('Description', ''))
        if desc.strip():
            qty = float(row.get('Qty', 0))
            price = float(row.get('Price', 0))
            line_total = qty * price
            pdf.cell(100, 8, desc, 1)
            pdf.cell(20, 8, str(qty), 1)
            pdf.cell(35, 8, f"${price:,.2f}", 1)
            pdf.cell(35, 8, f"${line_total:,.2f}", 1)
            pdf.ln()

    pdf.ln(5)
    # Labor Table
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Labor & Services", ln=True)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(100, 8, "Service", 1)
    pdf.cell(20, 8, "Hours", 1)
    pdf.cell(35, 8, "Rate", 1)
    pdf.cell(35, 8, "Total", 1)
    pdf.ln()

    pdf.set_font("Arial", size=10)
    for _, row in labor_df.iterrows():
        service = str(row.get('Service', ''))
        if service.strip():
            hours = float(row.get('Hours', 0))
            rate = float(row.get('Rate', 0))
            line_total = hours * rate
            pdf.cell(100, 8, service, 1)
            pdf.cell(20, 8, str(hours), 1)
            pdf.cell(35, 8, f"${rate:,.2f}", 1)
            pdf.cell(35, 8, f"${line_total:,.2f}", 1)
            pdf.ln()

    # Totals Summary
    pdf.ln(10)
    pdf.set_x(120)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 8, "Subtotal:")
    pdf.cell(30, 8, f"${totals['subtotal']:,.2f}", ln=True)
    
    if totals['discount'] > 0:
        pdf.set_x(120)
        pdf.cell(40, 8, f"Discount ({totals['discount_rate']}%):")
        pdf.cell(30, 8, f"-${totals['discount']:,.2f}", ln=True)

    pdf.set_x(120)
    pdf.cell(40, 8, f"Tax ({totals['tax_rate']}%):")
    pdf.cell(30, 8, f"${totals['tax']:,.2f}", ln=True)
    
    pdf.set_x(120)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(40, 10, "GRAND TOTAL:")
    pdf.cell(30, 10, f"${totals['grand_total']:,.2f}", ln=True)

    return bytes(pdf.output())

def main():
    st.set_page_config(page_title="D&L AV Quote Tool", page_icon="🔊", layout="centered")

    st.title("🔊 D&L AV Quote Tool")
    st.markdown("---")

    sheet = connect_to_sheets()
    if not sheet:
        st.info(f"💡 Connect to Google Sheets (Target: {SPREADSHEET_NAME}) to enable saving.")
    
    with st.sidebar:
        st.header("Project Details")
        client_name = st.text_input("Client Name", value="Client Name")
        project_name = st.text_input("Project Name", value="Project Title")
        # Default Tax Rate 10%
        tax_rate = st.number_input("Tax Rate (%)", value=10.0, step=0.01)
        discount_rate = st.number_input("Discount (%)", value=0.0, step=0.5)

    st.subheader("🛠 Equipment / Parts")
    parts_data = st.data_editor(
        pd.DataFrame([{"Description": "", "Qty": 1, "Price": 0.0}]),
        num_rows="dynamic", key="parts_editor", use_container_width=True
    )

    st.markdown("---")
    st.subheader("👷 Labor / Services")
    # Default Labor Rate 40.0
    labor_data = st.data_editor(
        pd.DataFrame([{"Service": "", "Hours": 1.0, "Rate": 40.0}]),
        num_rows="dynamic", key="labor_editor", use_container_width=True
    )

    # Calculations
    parts_subtotal = (pd.to_numeric(parts_data["Qty"], errors='coerce').fillna(0) * pd.to_numeric(parts_data["Price"], errors='coerce').fillna(0)).sum()
    labor_subtotal = (pd.to_numeric(labor_data["Hours"], errors='coerce').fillna(0) * pd.to_numeric(labor_data["Rate"], errors='coerce').fillna(0)).sum()
    
    subtotal = parts_subtotal + labor_subtotal
    discount_val = subtotal * (discount_rate / 100)
    taxable_amount = subtotal - discount_val
    tax_val = taxable_amount * (tax_rate / 100)
    grand_total = taxable_amount + tax_val

    totals_dict = {
        "subtotal": subtotal, "discount": discount_val, "discount_rate": discount_rate,
        "tax": tax_val, "tax_rate": tax_rate, "grand_total": grand_total
    }

    st.markdown("---")
    res_col1, res_col2 = st.columns([1.5, 1])
    
    with res_col1:
        st.subheader("Quote Summary")
        summary_df = pd.DataFrame({
            "Category": ["Parts Subtotal", "Labor Subtotal", f"Discount ({discount_rate}%)", f"Tax ({tax_rate}%)", "Grand Total"],
            "Amount": [f"${parts_subtotal:,.2f}", f"${labor_subtotal:,.2f}", f"-${discount_val:,.2f}", f"${tax_val:,.2f}", f"${grand_total:,.2f}"]
        })
        st.table(summary_df)

    with res_col2:
        st.write("### Actions")
        
        if sheet and st.button("🚀 Save Quote to Google Sheets", use_container_width=True):
            if not client_name or not project_name:
                st.error("Please enter Client and Project names.")
            else:
                with st.spinner("Saving..."):
                    quote_num = get_next_quote_number(sheet)
                    new_row = [quote_num, datetime.date.today().strftime("%Y-%m-%d"), client_name, project_name, grand_total]
                    sheet.append_row(new_row)
                    st.success(f"Saved to {SPREADSHEET_NAME} as {quote_num}!")
                    st.session_state['last_quote_num'] = quote_num

        current_q_num = st.session_state.get('last_quote_num', "DRAFT")
        
        try:
            pdf_bytes = create_pdf(current_q_num, client_name, project_name, parts_data, labor_data, totals_dict)
            st.download_button(
                label="📄 Download PDF Quote",
                data=pdf_bytes,
                file_name=f"DL_AV_Quote_{client_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as pdf_err:
            st.error(f"Error generating PDF: {pdf_err}")

        csv = pd.concat([parts_data.assign(Type="Part"), labor_data.assign(Type="Labor")]).to_csv(index=False).encode('utf-8')
        st.download_button(label="📊 Export CSV", data=csv, file_name="dl_av_quote_export.csv", mime='text/csv', use_container_width=True)

    with st.expander("📊 View Recent Saved Quotes"):
        if sheet and st.button("Refresh Data"):
            data = sheet.get_all_records()
            if data: st.dataframe(pd.DataFrame(data).tail(10), use_container_width=True)

if __name__ == "__main__":
    main()

