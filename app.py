import streamlit as st
import requests
import time

API_BASE = "http://localhost:8000"

# Make page wide
st.set_page_config(page_title="Auto-Gherkin Generator", layout="wide")

st.title("🧪 Auto-Gherkin / UI Scenario Generator")

# Sidebar for inputs
with st.sidebar:
    st.header("Input")
    url = st.text_input("Website URL", value="https://example.com")
    submit = st.button("Generate Scenarios")

if submit:
    if not url.strip():
        st.sidebar.error("Please enter a valid URL")
    else:
        st.sidebar.info("Job started…")
        resp = requests.post(f"{API_BASE}/start_job", json={"url": url})
        if resp.status_code != 200:
            st.sidebar.error("Failed to start job")
        else:
            job_id = resp.json()["job_id"]
            st.sidebar.success(f"Job ID: {job_id}")

            # Show spinner while waiting
            with st.spinner("Generating scenarios, please wait…"):
                while True:
                    status = requests.get(f"{API_BASE}/job_status/{job_id}").json().get("status")
                    if status == "done":
                        break
                    elif status == "error":
                        st.sidebar.error("Job failed")
                        break
                    time.sleep(2)

            # Fetch and display result
            result_resp = requests.get(f"{API_BASE}/get_result/{job_id}")
            if result_resp.status_code == 200:
                content = result_resp.text

                # Show results in two tabs: Gherkin and JSON (if JSON)
                tab1, tab2 = st.tabs(["📄 Gherkin", "📦 Raw / JSON"])
                with tab1:
                    st.subheader("Generated Scenarios (Gherkin)")
                    st.code(content)
                with tab2:
                    st.subheader("Raw Output")
                    st.text_area("Full result", content, height=400)

                # Also allow download of result as .feature or .json
                # Decide filename based on content type
                download_filename = "scenarios.feature"
                st.download_button(
                    label="Download result",
                    data=content,
                    file_name=download_filename,
                    mime="text/plain"
                )
            else:
                st.sidebar.error("Could not fetch result")


# Optionally show instructions or help text
with st.expander("ℹ️ How to use"):
    st.write("""
    1. Enter the full URL of the website you want to analyze.  
    2. Click **Generate Scenarios**.  
    3. Wait for the backend to finish processing — progress is shown in the sidebar.  
    4. Once done, download or copy the generated Gherkin scenarios.  
    """)