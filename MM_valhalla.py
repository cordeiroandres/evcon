import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import ConsumptionFunctions as cb

data = pd.read_csv('lucca_small_100per.csv',dtype={"uid": np.int64 ,"lon": np.float32,"lat": np.float32,"speed": np.float16},parse_dates=["ts"],usecols=["uid","lon","lat","speed","ts"])
df1 = pd.DataFrame(data)

dj = cb.pre_process(df1,1200,50,4)

lst_inter = dj[dj['distance'] == 0.0].index.tolist()

results = list()    
wayids = [] 
for i in range(len(lst_inter)-1):    
    df=dj.iloc[lst_inter[i]:lst_inter[i+1]].reset_index(drop=True)    
    djr=cb.MapMatching_traj(df)
    if len(djr) > 0:
        dist = djr['distance'].sum()/1000
        con = djr['emob_con'].sum()+10
        group_wayid = djr.groupby('way_id',sort=False).agg({'emob_con': 'sum','distance':'sum','ts_dif':'sum'}).reset_index()
        ts=djr.ts[0]
        group_wayid['ts']=ts
        group_wayid['distance'] = group_wayid['distance']/1000    
        uid = djr.uid[0]
        dfj=[uid,djr.ts[0],djr.ts[len(djr)-1],dist,con ]
        results.append(dfj)
        wayids.append(group_wayid)                     
        with open('lst_wayid.txt', 'a') as f:
            for line in wayids:
                f.write(f"{line}\n")
        f.close()

    with open('consumption_day.txt', 'a') as f:
        for line in results:
            f.write(f"{line}\n")
    f.close()

lst_wi = pd.concat(wayids, ignore_index=True)     

lst_wi.to_csv('lst_way_ids.csv', index=False)
