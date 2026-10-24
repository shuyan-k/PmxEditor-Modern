import json,sys
d=json.load(open('tests/report.json',encoding='utf8'))
lim=int(sys.argv[1]) if len(sys.argv)>1 else 400
for l in d['log']: print(l[:lim])
print("=== ANOM", len(d['anomalies']))
for a in d['anomalies'][:int(sys.argv[2]) if len(sys.argv)>2 else 30]:
    print("-",a['kind'],'|',a['detail'][:lim].replace("\n"," / "))
