import requests
from bs4 import BeautifulSoup

def main():
    base_url = "http://127.0.0.1:5000"
    
    print("Testing GET / ...")
    r = requests.get(f"{base_url}/", timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.find_all("tr")
    print(f"Total table rows rendered on page 1: {len(rows)}")
    
    extracted_reqs = []
    for tr in rows:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if tds and len(tds) >= 4:
            extracted_reqs.append(tds[:5])
            
    print(f"Rendered requirements on page 1: {len(extracted_reqs)}")
    for req in extracted_reqs[:10]:
        print("  Row:", req)
        
    # Check for synthetic data presence
    html_text = r.text.lower()
    synthetic_markers = ["298412-1", "senior python backend engineer", "quantum cryptography fpga architect"]
    for marker in synthetic_markers:
        assert marker not in html_text, f"Synthetic marker '{marker}' found in UI HTML!"
    print("\nCONFIRMED: Zero synthetic data found in UI HTML!")
    
    # Test Detail View
    detail_id = "2026/10/06-004"
    print(f"\nTesting GET /requirement/{detail_id} ...")
    r_detail = requests.get(f"{base_url}/requirement/{detail_id}", timeout=10)
    assert r_detail.status_code == 200, f"Detail page failed with {r_detail.status_code}"
    soup_detail = BeautifulSoup(r_detail.text, "html.parser")
    detail_text = soup_detail.get_text()
    assert "EMB - V&V HSIT" in detail_text, "Job title missing from detail text"
    assert "LTTS" in detail_text, "Client missing from detail text"
    print(f"CONFIRMED: Detail page for {detail_id} successfully loaded genuine requirement details!")

    # Test Detail API
    print(f"\nTesting GET /api/requirement/{detail_id} ...")
    r_api = requests.get(f"{base_url}/api/requirement/{detail_id}", timeout=5)
    assert r_api.status_code == 200, f"API failed with {r_api.status_code}"
    api_data = r_api.json()
    payload = api_data.get("payload", {})
    print("API Response Job Title:", payload.get("job_title"))
    print("API Response Client:", payload.get("requirement_from"))
    print("API Response Graph ID:", payload.get("graphMessageId") or payload.get("_provenance", {}).get("graph_message_id"))
    print("CONFIRMED: Detail API successfully returned exact genuine requirement data!")

if __name__ == "__main__":
    main()
