import requests
import os
import base64

# Тест главной страницы
try:
    r = requests.get('http://localhost:5000/')
    print("Main page:", r.status_code)
except Exception as e:
    print("Error connecting to main page:", e)

# Тест XML API
try:
    r = requests.get('http://localhost:5000/apixml')
    print("XML API:", r.status_code)
    if r.status_code != 200:
        exit(1)
except Exception as e:
    print("Error XML API:", e)
    exit(1)