import pandas as pd
from pathlib import Path
from app_modules.dash_logic import build_compare_dataframe, read_dictionary, read_json_map

base = Path(r"C:\Users\rotemSRS\Desktop\automatic_tool_storage")
d, _ = read_dictionary(base / "dictionary_latest.xlsx")
ko = read_json_map(base / "ko_latest.json")
ru = read_json_map(base / "ru_latest.json")
en = read_json_map(base / "en_latest.json")
out, _ = build_compare_dataframe(d,ko,ru,en,False,'Main Modulew','English','Korean','Russian')
for key in ['Car','Train/Car Management','List','Project','Code','w']:
    x = out[out['Dictionary English']==key]
    if x.empty:
        print(key, 'NOT FOUND')
    else:
        r=x.iloc[0]
        print(key, 'ko=',repr(r['ko.json']), 'ru=',repr(r['ru.json']), 'en=',repr(r['en.json']), 'KM=',r['KO_Match'],'RM=',r['RU_Match'],'EM=',r['EN_Match'])
