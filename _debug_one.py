import pandas as pd
from app import compare_records_from_sources

source_paths={
'dictionary':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\dictionary_latest.xlsx',
'ko':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\ko_latest.json',
'ru':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\ru_latest.json',
'en':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\en_latest.json',
}
records, msg = compare_records_from_sources(
    source_paths=source_paths,
    include_en_keys=False,
    module_col='Main Modulew',
    english_col='English',
    korean_col='Korean',
    russian_col='Russian',
)
df=pd.DataFrame(records)
print(df.loc[df['Dictionary English']=='Car',['Dictionary Korean','ko.json','KO_Match']].to_string(index=False))
