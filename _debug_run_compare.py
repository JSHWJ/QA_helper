from pathlib import Path
import pandas as pd
from dash_app import run_compare

source_paths={
    'dictionary': r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\dictionary_latest.xlsx',
    'ko': r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\ko_latest.json',
    'ru': r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\ru_latest.json',
    'en': r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\en_latest.json',
}
records,msg = run_compare(0, source_paths, ['use_saved'], 'Main Modulew', 'English', 'Korean', 'Russian')
print(msg)
import pandas as pd
if records:
    df=pd.DataFrame(records)
    print(df[['Dictionary English','en.json','ko.json','ru.json','EN_Match','KO_Match','RU_Match']].head(15).to_string(index=False))
    print('non-empty', (df['en.json'].astype(str).str.strip()!='').sum(), (df['ko.json'].astype(str).str.strip()!='').sum(), (df['ru.json'].astype(str).str.strip()!='').sum())
