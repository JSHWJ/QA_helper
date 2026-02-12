from dash_app import run_compare
import pandas as pd
source_paths={
'dictionary':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\dictionary_latest.xlsx',
'ko':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\ko_latest.json',
'ru':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\ru_latest.json',
'en':r'C:\Users\rotemSRS\Desktop\automatic_tool_storage\en_latest.json',
}
records,msg=run_compare(0,source_paths,['use_saved'],'Main Modulew','English','Korean','Russian')
df=pd.DataFrame(records)
print(df.loc[df['Dictionary English']=='Car',['Dictionary Korean','ko.json','KO_Match']].to_string(index=False))
