from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import pdfplumber
import io
import re

app = Flask(__name__)

# 🔍 Extract sections between headings in PDF
def extract_section_lines(start_keyword, stop_keywords, lines):
    content = []
    capture = False
    for line in lines:
        if start_keyword.lower() in line.lower():
            capture = True
            continue
        if capture:
            if any(stop.lower() in line.lower() for stop in stop_keywords):
                break
            content.append(line.strip())
    return "\n".join(content).strip()

# 📊 Extract sales specification table rows
def extract_sales_spec_table(lines):
    capture = False
    table_data = []
    for line in lines:
        if 'sales specification' in line.lower():
            capture = True
            continue
        if capture:
            if any(h in line.lower() for h in ['handling', 'regulatory', 'storage']):
                break
            table_data.append(line.strip())

    rows = []
    for i in range(1, len(table_data), 4):
        if i + 2 < len(table_data):
            row = {
                "Characteristic": table_data[i - 1],
                "Unit": table_data[i],
                "Specification": table_data[i + 1],
                "Method": table_data[i + 2]
            }
            rows.append(row)
    return rows

# 🧠 Extract product details from website and PDF
def get_product_details(product_name):
    slug = product_name.lower().replace(" ", "_")
    url = f'https://www.perstorp.com/en/products/{slug}'

    response = requests.get(url)
    if response.status_code != 200:
        return {"error": "❌ Product page not found."}

    soup = BeautifulSoup(response.text, 'html.parser')
    pdf_link = None
    for link in soup.find_all('a', href=True):
        if link['href'].lower().endswith('.pdf'):
            pdf_link = link['href']
            break

    if not pdf_link:
        return {"error": "❌ PDF datasheet not found."}

    if not pdf_link.startswith('http'):
        pdf_link = 'https://www.perstorp.com' + pdf_link

    pdf_response = requests.get(pdf_link)
    if pdf_response.status_code != 200:
        return {"error": "❌ Failed to download PDF."}

    with pdfplumber.open(io.BytesIO(pdf_response.content)) as pdf:
        text = ''
        for page in pdf.pages:
            text += page.extract_text() + '\n'

    text_lines = text.split('\n')

    description = extract_section_lines("Product Description", ["Segment Applications", "Delivery Forms", "Handling", "Sales"], text_lines)
    applications = extract_section_lines("Segment Applications", ["Delivery Forms", "Handling", "Sales"], text_lines)
    delivery = extract_section_lines("Delivery Forms", ["Handling", "Sales", "Purity"], text_lines)

    purity = ''
    for line in text_lines:
        if 'purity' in line.lower():
            match = re.search(r'purity.*?(\d{2,3}\.?\d*)\s*%', line, re.IGNORECASE)
            if match:
                purity = match.group(1) + '%'
                break

    sales_spec = extract_sales_spec_table(text_lines)
    sales_spec_str = '\n'.join(
        f"{r['Characteristic']} | {r['Unit']} | {r['Specification']} | {r['Method']}"
        for r in sales_spec
    )

    return {
        "Product Name": product_name,
        "Description": description,
        "Applications": applications,
        "Delivery Form": delivery,
        "Purity": purity,
        "Sales Specification": sales_spec_str,
        "PDF URL": pdf_link,
        "Product Page": url
    }

# 🔁 API Route to access product details
@app.route('/product', methods=['GET'])
def product_api():
    product_name = request.args.get('name')
    if not product_name:
        return jsonify({"error": "❗ Missing product name."}), 400

    result = get_product_details(product_name)
    return jsonify(result)

# ▶️ Run the server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
