# -*- coding: utf-8 -*-
"""
Created on Tue Apr  4 06:03:26 2023
@author: deiro
"""
import pandas as pd
import numpy as np
import ConsumptionFunctions as cb
import glob
import os
import rasterio
from pathlib import Path
import time
import re

if __name__ == '__main__':
    #the maximum period of time (in seconds) between two consecutive points, otherwise the trajectory will be cut and another one will start
    temporal_thr = 1200.0 # seconds 20 minutes 
    #the minimum length (in meters) allowed between two consecutive points, otherwise the point will be removed
    spatial_thr = 50 # meters    
    #the minimum number of points in a trajectory
    minpoints = 4 # number of points in the trayectorie
        
    search_criteria = "*.csv.gz"    
    TILES_DIR = '/home/mirco/octo_gps/Emilia/'
    files = os.path.join(TILES_DIR, search_criteria)
    list_csv = glob.glob(files)
    list_csv.sort()
    
    df_traj = []
    
    results = list()    
    wayids = list() 
    
    traj_new = list()    
    traj = list()
    first_iteration = True  
    i = 1 
    
    t0 = time.time()

    for i in range(len(list_csv)):
    #for dt in list_csv:
        data = pd.read_csv(list_csv[i],dtype={"ID_ANONYMOUS": np.int64 ,"LONGITUDE": np.float32,"LATITUDE": np.float32,"SPEED": np.float16},
                           parse_dates=[["DAY","HH24"]],
                           usecols=["ID_ANONYMOUS","DAY","HH24","LONGITUDE","LATITUDE","SPEED"])
        df_list = pd.DataFrame(data)
        
        if len(df_list) == 0:
            continue
            
        txt = list_csv[i]
        text = re.sub(r'^/home/mirco/octo_gps/Emilia/', '', txt)
        title_day = re.sub(r'\.csv\.gz$', '', text)
        title_day = title_day +'.txt'
        print(title_day)
        
        df_list.columns = ['ts','uid','lat','lon','speed']
        df_list['user_progressive'] = 0  
        df_list['lon'] = df_list['lon']/ 10**6
        df_list['lat'] = df_list['lat']/ 10**6
        
        cb.srtm_assign(df_list)
        
        df = df_list.to_numpy()  
        print(df[0])
        break
        """
        for row in df:                       
            next_p = row        
            if first_iteration:
                uid = row[1]            
                p = row
                p[5] = i
                traj = [p]              
                first_iteration = False 
            else: 
                #calculates the time difference 
                temporal_dist = (next_p[0]-p[0]).total_seconds()            
                #calculates distance between two points        
                spatial_dist = cb.spherical_distance(p[3],p[2],next_p[3],next_p[2])
                print(p[3],p[2],next_p[3],next_p[2])
                print('dist=',spatial_dist)
                if uid!=next_p[0]:
                    i = 1
                    uid = next_p[0]
                    
                if temporal_dist > temporal_thr:                                    
                    if len(traj) >= minpoints:  
                        print(len(traj))
                        
                        traj_new.extend(traj)                                            
                        
                        col = ['ts','uid','lat','lon','speed','user_progressive']
                        df_traj = pd.DataFrame(traj, columns=col)    
                        print(df_traj)
                        #dfa=[uid,df_traj.ts[0],df_traj.lon[0], df_traj.lat[0], df_traj.ts[len(df_traj)-1], len(df_traj), df_traj.lon[len(df_traj)-1], df_traj.lat[len(df_traj)-1] ]
                        dfa = cb.MapMatching_traj(df_traj)
                        print(len(dfa))                                                
                        
                        if len(dfa) > 0:
                            dist = dfa['distance'].sum()/1000
                            con = dfa['j_con'].sum()
                            dfj=[uid,df_traj.ts[0],df_traj.ts[len(df_traj)-1],dist,con ]
                            results.append(dfj)                        
                            
                            with open(title_day, 'a') as f:
                                f.write(f"{dfj}\n")                                
                            f.close()
                            
                            group_wayid = dfa.groupby('way_id',sort=False).agg({'j_con': 'sum','distance':'sum','ts_dif':'sum'}).reset_index()                        
                            group_wayid['ts']=df_traj.ts[0]
                            group_wayid['distance'] = group_wayid['distance']/1000
                                                                            
                            wayids.append(group_wayid)
                            ct='wayid-'+title_day
                            with open(ct, 'a') as f:
                                for line in group_wayid:
                                    f.write(f"{line}\n")
                            f.close()
                            break
                                                    
                        traj=[]                                         
                        uid = traj_new[-1][1]                     
                        if uid==next_p[1]:
                            i += 1                                      
                            next_p[5] = i
                            p = next_p 
                            traj.append(p) 
                            continue
                        else:                    
                            #insufficient number of points
                            traj=[]    
                            next_p[5] = i                                                  
                            traj.append(next_p)
                            p = next_p                 
                            continue        
                    
                if spatial_dist > spatial_thr:                                                        
                    next_p[5] = i
                    p = next_p                
                    traj.append(p)  
        
        
    t=time.time()-t0
    with open('time.txt', 'w') as f: 
        f.write("total time:")
        f.write(f"{t}\n ")
    f.close()
    """
