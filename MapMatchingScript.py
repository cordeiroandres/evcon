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

if __name__ == '__main__':
    #the maximum period of time (in seconds) between two consecutive points, otherwise the trajectory will be cut and another one will start
    temporal_thr = 1200.0 # seconds 20 minutes 
    #the minimum length (in meters) allowed between two consecutive points, otherwise the point will be removed
    spatial_thr = 50 # meters    
    #the minimum number of points in a trajectory
    minpoints = 4 # number of points in the trayectorie
    
    #search_criteria = "*.csv"
    search_criteria = "*.csv.gz"
    #TILES_DIR = "C:\\Users\\deiro\\Documents\\Thesis\\datasets\\data"
    TILES_DIR = '/home/mirco/octo_gps/Emilia/'
    files = os.path.join(TILES_DIR, search_criteria)
    list_csv = glob.glob(files)
    list_csv.sort()
    
    PATH = os.getcwd()    
    FOLDER_DIR = 'srtm_files'    
    TILES_DIR = os.path.join(PATH, FOLDER_DIR)
    MOSAIC = 'Mosaic.tif'
    
    df_traj = []
    
    results = list()    
    
    traj_new = list()    
    traj = list()
    first_iteration = True  
    i = 1 
    
    t0 = time.time()
    
    for dt in list_csv:        
        data = pd.read_csv(dt,dtype={"ID_ANONYMOUS": np.int64 ,"LONGITUDE": np.float32,"LATITUDE": np.float32,"SPEED": np.float16},
                           parse_dates=[["DAY","HH24"]],
                           usecols=["ID_ANONYMOUS","DAY","HH24","LONGITUDE","LATITUDE","SPEED"])
        df_list = pd.DataFrame(data)
        with open('list_dt.txt', 'a') as f:                   
             f.write(f"{dt}\n")
        f.close()
        
        if len(df_list) == 0:
            continue
            
        df_list.columns = ['ts','uid','lat','lon','speed']
        df_list['user_progressive'] = 0  
        df_list['lon'] = df_list['lon']/ 10**6
        df_list['lat'] = df_list['lat']/ 10**6
        
        #cb.srtm_assign(df_list)
        #GLOBAL VARIABLES
        tile = os.path.join(TILES_DIR , MOSAIC)        
        dem_file = Path(tile)

        #checks if the file exist
        if dem_file.is_file():
            SRC = rasterio.open(tile)
            DEM_DATA = SRC.read(1)

        
        df = df_list.to_numpy()
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
                
                if uid!=next_p[0]:
                    i = 1
                    uid = next_p[0]
                    
                if temporal_dist > temporal_thr:                                    
                    if len(traj) >= minpoints:                      
                        traj_new.extend(traj)                                            
                        
                        col = ['ts','uid','lon','lat','speed','user_progressive']
                        df_traj = pd.DataFrame(traj, columns=col)                                                             
                        #dfa = cb.consumption_traj(df_traj)
                        #dfa = cb.consumption_lin(df_traj)
                        dfa=[uid,df_traj.ts[0],df_traj.ts[len(df_traj)-1], len(df_traj) ]
                        results.append(dfa)
                        
                        with open('mapmat.txt', 'a') as f:
                            for line in results:
                                f.write(f"{line}\n")
                        f.close()
                        
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
         f.write(f"{t} total time\n ")
    f.close()
    
        
        
        
