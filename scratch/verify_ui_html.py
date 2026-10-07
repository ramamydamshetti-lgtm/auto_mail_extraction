import urllib.request
from bs4 import BeautifulSoup

url = "http://127.0.0.1:5000/"
html = urllib.request.urlopen(url).read().decode('utf-8')
soup = BeautifulSoup(html, 'html.parser')

rows = soup.find_all('tr')
print(f"Total rows found: {len(rows)}")

for i, row in enumerate(rows[:10]):
    cols = [td.get_text(strip=True) for td in row.find_all(['th', 'td'])]
    links = [a['href'] for a in row.find_all('a', href=True)]
    print(f"Row {i}: {cols} | Links: {links}")
