import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import datetime
import pandas as pd
import json
import os

# --- CONFIGURATION ---
# The name of the secret key in Streamlit Cloud "Advanced Settings > Secrets"
SECRET_KEY_NAME = "gcp_service_account"
# The name of the local file for development
LOCAL_SERVICE_ACCOUNT_FILE = 'service_account.json'
SPREADSHEET_NAME = 'AVL_Quote_Database'

def connect_to_sheets():
    """Establishes connection to the Google Sheet using Secrets or Local File."""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    try:
        # 1. Try to load from Streamlit Cloud Secrets first
        if SECRET_KEY_NAME in st.secrets:
            # Parse the JSON string from secrets
            creds_info = json.loads(st.secrets[SECRET_KEY_NAME])
            credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        
        # 2. Fallback to local file if secrets aren't found (for local testing)
        elif os.path.exists(LOCAL_SERVICE_ACCOUNT_FILE):
            credentials = Credentials.from_service_account_file(
                LOCAL_SERVICE_ACCOUNT_FILE, scopes=scopes
            )
        
        else:
            st.error("Credential Error: 'service_account.json' not found locally, and 'gcp_service_account' not found in Streamlit Secrets.")
            return None
            
        gc = gspread.authorize(credentials)
        return gc.open(SPREADSHEET_NAME).sheet1
        
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
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

def main():
    st.set_page_config(page_title="AVL Quote Tool", page_icon="🔊", layout="centered")

    st.title("🔊 AVL Quote Tool")
    st.markdown("---")

    # Connect to database
    sheet = connect_to_sheets()
    if not sheet:
        st.info("💡 Pro Tip: If you just added secrets, you may need to 'Reboot App' in the Streamlit Cloud dashboard.")
        return

    # Sidebar: Project Info
    with st.sidebar:
        st.header("Project Details")
        client_name = st.text_input("Client Name")
        project_name = st.text_input("Project Name")
        tax_rate = st.number_input("Tax Rate (%)", value=10.0, step=0.01)
        discount_rate = st.number_input("Discount (%)", value=0.0, step=0.5)

    # Main Area: Itemized Entry
    st.subheader("🛠 Equipment / Parts")
    parts_data = st.data_editor(
        pd.DataFrame([{"Description": "", "Qty": 1, "Price": 0.0}]),
        num_rows="dynamic",
        key="parts_editor",
        use_container_width=True
    )

    st.markdown("---")
    
    st.subheader("👷 Labor / Services")
    labor_data = st.data_editor(
        pd.DataFrame([{"Service": "", "Hours": 1.0, "Rate": 95.0}]),
        num_rows="dynamic",
        key="labor_editor",
        use_container_width=True
    )

    # Calculations
    parts_subtotal = (parts_data["Qty"] * parts_data["Price"]).sum()
    labor_subtotal = (labor_data["Hours"] * labor_data["Rate"]).sum()
    
    subtotal = parts_subtotal + labor_subtotal
    discount_val = subtotal * (discount_rate / 100)
    taxable_amount = subtotal - discount_val
    tax_val = taxable_amount * (tax_rate / 100)
    grand_total = taxable_amount + tax_val

    # Summary Card
    st.markdown("---")
    res_col1, res_col2 = st.columns([1.5, 1])
    
    with res_col1:
        st.subheader("Quote Summary")
        summary_df = pd.DataFrame({
            "Category": ["Parts Subtotal", "Labor Subtotal", f"Discount ({discount_rate}%)", f"Tax ({tax_rate}%)", "Grand Total"],
            "Amount": [
                f"${parts_subtotal:,.2f}", 
                f"${labor_subtotal:,.2f}", 
                f"-${discount_val:,.2f}", 
                f"${tax_val:,.2f}", 
                f"${grand_total:,.2f}"
            ]
        })
        st.table(summary_df)

    with res_col2:
        st.write("### Actions")
        if st.button("🚀 Save Quote to Google Sheets", use_container_width=True):
            if not client_name or not project_name:
                st.error("Please enter Client and Project names before saving.")
            else:
                with st.spinner("Syncing with Google Sheets..."):
                    quote_num = get_next_quote_number(sheet)
                    date_str = datetime.date.today().strftime("%Y-%m-%d")
                    
                    new_row = [quote_num, date_str, client_name, project_name, grand_total]
                    sheet.append_row(new_row)
                    
                    st.success(f"Quote {quote_num} saved successfully!")
                    st.balloons()

        # Export to CSV
        full_export = pd.concat([
            parts_data.assign(Type="Part"), 
            labor_data.rename(columns={"Service": "Description", "Hours": "Qty", "Rate": "Price"}).assign(Type="Labor")
        ])
        
        csv = full_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Export Current Quote as CSV",
            data=csv,
            file_name=f"AVL_Quote_{client_name.replace(' ', '_')}_{datetime.date.today()}.csv",
            mime='text/csv',
            use_container_width=True
        )

    # View History
    with st.expander("📊 View Recent Saved Quotes"):
        if st.button("Refresh Data"):
            data = sheet.get_all_records()
            if data:
                st.dataframe(pd.DataFrame(data).tail(10), use_container_width=True)
            else:
                st.write("No data found.")

if __name__ == "__main__":
    main()

if __name__ == "__main__":

    main()
