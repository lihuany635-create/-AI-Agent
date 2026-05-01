import requests
try:
    r = requests.get('http://localhost:11434/api/tags')
    models = r.json()
    print('Ollama 模型清單:')
    for m in models['models']:
        size = round(m['size']/1000000000, 1)
        print(m['name'], size, 'GB')
except Exception as e:
    print('Ollama 離線:', e)

try:
    r2 = requests.get('http://localhost:8000/docs')
    print('pc_api: 在線')
except:
    print('pc_api: 未啟動')
