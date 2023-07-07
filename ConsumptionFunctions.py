import pandas as pd
import numpy as np
import time
import rasterio
import zipfile
import os
import requests
import polyline as pc
#from multiprocessing import cpu_count
#from multiprocessing.pool import ThreadPool
from rasterio.merge import merge
import glob
import math
from functools import lru_cache
from pathlib import Path
from numba import njit
import meteostat as mt
import json
from shapely.geometry.linestring import LineString
from shapely.geometry import Point


from ConstantsConsumption import (
    #WEATHER_FILES,
    #WEATHER_OPTIONS,
    #EVSPECS_FILE,
    #MG_EFFICIENCY_FILE,
    #COUNTRY_CODE_ZONES_FILE,
    #VEHICLE_NEEDED_PARAMETERS,
    COP,
    TARGET_TEMP,
    GRAVITY,
    #LAYER_NAMES,
    #ZONE_NAMES,
    ZONE_LAYERS,
    ZONE_SURFACE,
    LAYER_CONDUCTIVITY,
    LAYER_THICKNESS,
    #AIR_SPECIFIC_HEAT,
    
    PATH,
    FOLDER_DIR,
    URL,
    TILES_DIR,
    MOSAIC,
    TILE_SRTM,      
    #HEIGHT_VEHICLE,
    #WIDTH_VEHICLE,
    #MOTOR_POWER,
    #GEAR_RATIO,
    PASSENGER_SENSIBLE_HEAT,
    AIR_CABIN_HEAT_TRANSFER_COEF,
    AIR_FLOW,
    #ROAD_TYPE,
    WIND_SPEED,
    #ROAD_SLOPE,
    CABIN_VOLUME,
    
    #CURB_WEIGHT,
    BATTERY_CHARGE_EFF,
    BATTERY_DISCHARGE_EFF,
    TRANSMISSION_EFF,
    #PASSENGER_MASS,
    PASSENGER_NR,
    
    EFFMOT,
    PAUX,
    R,
    RHO,
    A,
    CD,
    EBATCAP,
    REGEN_RATIO,
    AUXILIARY_POWER,
    DRAG_COEFFICIENT,
    AIR_DENSITY,
    LOAD_FRACTION,
    MOTOR,
    GENERATOR,
    
    M_I,
    VEHICLE_MASS,
    FRONTAL_AREA,
    P_MAX,
    #TIME_FREQ,    
    #DEFAULT_DATA_DIR,
    #USER_PATH,
    #MODULE_DATA_PATH,
    #EVSPECS_FILE,
    #MG_EFFICIENCY_FILE, 
    T_RNG,
    CP_RNG,   
    S_RC,            
    
    
)

#GLOBAL VARIABLES
tile = os.path.join(TILES_DIR , MOSAIC)
dem_file = Path(tile)

#checks if the file exist
if dem_file.is_file():
    SRC = rasterio.open(tile)
    DEM_DATA = SRC.read(1)


#FUNCTIONS OF EMOBPY
#FUNCTIONS FOR MOTOR INPUT POWER Pm_IN
def _cop_and_target_temp(T_out):
        """        
        Args:
            T_out ([float]): [description]
        Returns:
            [type]: [description]
        """        
        if T_out < TARGET_TEMP["heating"]:
            T_targ = TARGET_TEMP["heating"]
            cop = COP["heating"]
            #flag = 1
        elif T_out > TARGET_TEMP["cooling"]:
            T_targ = TARGET_TEMP["cooling"]
            cop = COP["cooling"]
            #flag = -1
        else:
            T_targ = None
            cop = 1
            #flag = 0
        return T_targ, cop #,flag

@njit(cache=True,fastmath=True)
def rolling_resistance_coeff_M1(temp, v, road_type=0):
    """
    Returns calculated rolling resistance coeff for M1.
    Args:
        temp (float): Temperature in degree celsius. (the ambient temperature)
        v (float): Speed in km/h.
        road_type (int, optional): 
                0: ordinary car tires on concrete, new asphalt, cobbles small new, coeff: 0.01 - 0.015 (Default)
                1: car tires on gravel - rolled new, on tar or asphalt, coeff: 0.02
                2: car tires on cobbles  - large worn, coeff: 0.03
                3: car tire on solid sand, gravel loose worn, soil medium hard, coeff: 0.04 - 0.08
                4: car tire on loose sand, coeff: 0.2 - 0.4
            reference: Wang, J.; Besselink, I.; Nijmeijer, H. Electric Vehicle Energy Consumption Modelling and
            Prediction Based on Road Information.
            World Electr. Veh. J. 2015, 7, 447-458. https://doi.org/10.3390/wevj7030447
    
    Returns:
        int: Rolling resistance coefficient
    """
    factor = [1, 1.5, 2.2, 4, 20]
    return (1.9e-6 * temp ** 2 - 2.1e-4 * temp + 0.013 +
            5.4e-5 * v) * factor[road_type]

@njit(cache=True,fastmath=True)
def prollingresistance(rolling_resistance_coeff,
                       vehicle_mass,
                       g,                       
                       slop_angle=0):
    """
    Calculates and returns polling resistance.
    Args:
        rolling_resistance_coeff ([type]): [description]
        vehicle_mass ([type]): [description]
        g ([type]): [description]
        v ([type]): [description]
        slop_angle (int, optional): [description]. Defaults to 0.

    Returns:
        float: Polling resistance.
    """
    #return rolling_resistance_coeff * vehicle_mass * g * np.cos(np.deg2rad(slop_angle)) * v
    return rolling_resistance_coeff * vehicle_mass * g * np.cos(slop_angle) 
    #return rolling_resistance_coeff * vehicle_mass * g * np.cos(np.deg2rad(slop_angle))

@njit(cache=True,fastmath=True)
def pairdrag(air_density, frontal_area, drag_coeff, v, wind_speed=0):
    """
    Reference: Wang, J.; Besselink, I.; Nijmeijer, H. Electric Vehicle Energy Consumption Modelling and Prediction
    Based on Road Information.
    World Electr. Veh. J. 2015, 7, 447-458. https://doi.org/10.3390/wevj7030447
    Args:
        air_density ([type]): [description]
        frontal_area ([type]): [description]
        drag_coeff ([type]): [description]
        v ([type]): [description]
        wind_speed (int, optional): Wind speed in direction of the vehicle.. Defaults to 0.
    Returns:
        float: [description]
    """    
    return 0.5 * air_density * frontal_area * drag_coeff * (v - wind_speed)**2
    
@njit(cache=True,fastmath=True)
def p_gravity(vehicle_mass, g, slop_angle=0):
    """
    Args:
        vehicle_mass ([type]): [description]
        g ([type]): [description]
        v ([type]): [description]
        slop_angle (int, optional): [description]. Defaults to 0.
    Returns:
        [type]: [description]
    """
    #return vehicle_mass * g * np.sin(np.deg2rad(slop_angle)) * v
    return vehicle_mass * g * np.sin(slop_angle)
    #return vehicle_mass * g * np.sin(np.deg2rad(slop_angle))

@njit(cache=True,fastmath=True)
def pinertia(inertial_mass, vehicle_mass, acceleration):
    """
    Args:
        inertial_mass ([type]): [description]
        vehicle_mass ([type]): [description]
        acceleration ([type]): [description]
        v ([type]): [description]
    Returns:
        [type]: [description]
    """
    return (vehicle_mass + inertial_mass) * acceleration

@njit(cache=True,fastmath=True)
def p_wheel(p_rollingresistance, p_airdrag, p_gravity, p_inertia):
    """
    Args:
        p_rollingresistance ([type]): [description]
        p_airdrag ([type]): [description]
        p_gravity ([type]): [description]
        p_inertia ([type]): [description]
    Returns:
        [type]: [description]
    """
    return p_rollingresistance + p_airdrag + p_gravity + p_inertia

@njit(cache=True,fastmath=True)
def p_motorout(p_wheel, transmission_eff):
    """
    Args:
        p_wheel ([type]): [description]
        transmission_eff ([type]): [description]
    Returns:
        [type]: [description]
    """    
    #only_positive = p_wheel
    
    if p_wheel < 0.0 or transmission_eff == 0.0:
        result = 0.0
    else:
        result = p_wheel / transmission_eff
    
    return result

#@njit(cache=True,fastmath=True)
def _get_efficiency(load_fraction, load_fraction_values, column_values):
    """    
    Gets a one-dimensional linear interpolation of given arguments.

    Args:
        load_fraction ([type]): [description]
        load_fraction_values ([type]): [description]
        column_values ([type]): [description]

    Returns:
        float: Efficiency.
    """
    return np.interp(load_fraction, load_fraction_values, column_values)

@njit(cache=True,fastmath=True)
def p_motorin(p_motor_out, motor_eff):
    """
    Args:
        p_motor_out ([type]): [description]
        motor_eff ([type]): [description]
    Returns:
        [type]: [description]
    """  
    
    if(motor_eff == 0  or np.isnan(motor_eff)):
        result=0
    else:
        result = p_motor_out / motor_eff
    
    return result


#FUNCTIONS FOR GENERATOR OUTPUT POWER Pg_OUT
@njit(cache=True,fastmath=True)
def EFFICIENCYregenerative_braking(acceleration):
    """        
    Args:
        acceleration ([type]): [description]
    Returns:
        [type]: [description]
    """    
    if acceleration >= 0.0:        
        result = 0.0
    else:
        result = (np.exp(0.0411 / np.abs(acceleration))) ** (-1)

    return result    

@njit(cache=True,fastmath=True)
def p_generatorin(p_wheel, transmission_eff, regenerative_braking_eff):
    """        
    Args:
        p_wheel ([type]): [description]
        transmission_eff ([type]): [description]
        regenerative_braking_eff ([type]): [description]
    Returns:
        [type]: [description]
    """
    
    only_negative = p_wheel

    if only_negative > 0.0:
        only_negative = 0.0

    result = only_negative * transmission_eff * regenerative_braking_eff

    return result

@njit(cache=True,fastmath=True)
def p_generatorout(p_generator_in, generator_eff):
    """        
    Args:
        p_generator_in ([type]): [description]
        generator_eff ([type]): [description]
    Returns:
        [type]: [description]
    """
    result = p_generator_in * generator_eff
    
    return result


#FUNCTIONS FOR ELECTRICAL POWER (HEATING/COOLING) DEVICES
@njit(cache=True,fastmath=True)
#@staticmethod
def calc_dew_point(T, H):
        """
        Calculate dew point.
        Args:
            t (float): air temperature in degree Celsius.
            h (float): Relative humidity in percent.

        Returns:
            array:
        """
        Td = (
                243.04
                * (np.log(H / 100) + ((17.625 * T) / (243.04 + T)))
                / (17.625 - np.log(H / 100) - ((17.625 * T) / (243.04 + T)))
        )
        return Td

@njit(cache=True,fastmath=True)
def calc_vapor_pressure(t):
    """
    Calculate vapor pressure.

    Args:
        t (array): Dew point or air temperature in degree Celsius.

    Returns:
        array: Vapor pressure array
    """
    T = t  # dew point or air temp degC
    E = 6.11 * np.power(
        10, ((7.5 * T) / (237.3 + T))
    )  # saturated  vapor pressure (mb) if t is dewpoint
    return E
    

@njit(cache=True,fastmath=True)
def humidair_density(t, p, h):
            """
            Calculate humid air density.
    
            Args:
                t (array): Temperature in degree Celsius.
                p (array): Pressure in mbar.
                h (array, optional): Humidity in percent. Defaults to None.    
            Raises:
                Exception: Dp or h is missing.

            Returns:
                array: Humid air density.
            """  
            #pv = calc_vapor_pressure(calc_dew_point(t, h))  # mbar 
            T = calc_dew_point(t, h)
            pv = 6.11 * np.power( 10, ((7.5 * T) / (237.3 + T)))
            
            #pd = calc_dry_air_partial_pressure(p, pv)  # mbar
            pdd = p - pv  # mbar
    
            Pv = 100 * pv  # convert mb   => Pascals
            Pd = 100 * pdd  # convert mb   => Pascals
    
            Rd = 287.05  # specific gas constant for dry air [J/(kgK)]
            Rv = 461.495  # specific gas constant for water vapour [J/(kgK)]
            T = t + 273.15  # convert degC => degK
    
            AD = Pd / (Rd * T) + Pv / (Rv * T)  # density [kg/m3]
            return AD

#@delay
@njit(cache=True,fastmath=True)
def q_ventilation(density_air, flow_air, Cp_air, temp_air):
    """        
    Density_air: kg/m3, Flow_air: m3/s, Cp_air: J/(kg*K), Temp_air: degC
    Args:
        density_air ([type]): [description]
        flow_air ([type]): [description]
        Cp_air ([type]): [description]
        temp_air ([type]): [description]

    Returns:
        [type]: [description]
    """
    temp_kelvin = temp_air + 273.15
    return density_air * flow_air * Cp_air * temp_kelvin

@njit(cache=True,fastmath=True)
def htc_air_out(vehicle_speed, limit=5):
    """        
    Args:
        vehicle_speed ([type]): [description]
        limit (int, optional): [description]. Defaults to 5.
    Returns:
        [type]: [description]
    """    
    if vehicle_speed < limit:
        h = 6.14 * np.power(limit, 0.78)
    else:
        h = 6.14 * np.power(vehicle_speed, 0.78)
    return h


@njit(cache=True,fastmath=True)
def resistances(zone_layer, zone_area, layer_conductivity, layer_thickness,
                vehicle_speed, air_cabin_heat_transfer_coef):
    """[summary]        
    Args:
        zone_layer ([type]): [description]
        zone_area ([type]): [description]
        layer_conductivity ([type]): [description]
        layer_thickness ([type]): [description]
        vehicle_speed ([type]): [description]
        air_cabin_heat_transfer_coef ([type]): [description]

    Returns:
        [type]: [description]
    """
    #x_z = zone_layer * layer_thickness
    
    h_i = air_cabin_heat_transfer_coef
    #FORMULA (26)
    h_o = htc_air_out(vehicle_speed)
    #FORMULA (24)
    #R_c = x_z / layer_conductivity
    #S_rc = R_c.sum(axis=1)
    
    R_hz = 1 / h_i + S_RC + 1 / h_o
    R_z = zone_area / R_hz
    return R_z.sum()

#@delay
@njit(cache=True,fastmath=True)
def q_transfer(zone_layer,
               zone_area,
               layer_conductivity,
               layer_thickness,
               t_air_cabin,
               t_air_out,
               vehicle_speed,
               air_cabin_heat_transfer_coef=10):
    """
    Args:
        zone_layer ([type]): [description]
        zone_area ([type]): [description]
        layer_conductivity ([type]): [description]
        layer_thickness ([type]): [description]
        t_air_cabin ([type]): [description]
        t_air_out ([type]): [description]
        vehicle_speed ([type]): [description]
        air_cabin_heat_transfer_coef (int, optional): [description]. Defaults to 10.

    Returns:
        [type]: [description]
    """
    t_air_cabin_K = t_air_cabin + 273.15
    t_air_out_K = t_air_out + 273.15        
    R = resistances(zone_layer, zone_area, layer_conductivity, layer_thickness,
                    vehicle_speed, air_cabin_heat_transfer_coef)    
    return (t_air_cabin_K - t_air_out_K) * R

@njit(cache=True,fastmath=True)
def cp(T):    
    """
    Args:
        T ([type]): [description]

    Returns:
        [type]: [description]
    """
    return np.interp(T, T_RNG, CP_RNG)



@njit(cache=True,fastmath=True)
def vehicle_mass(curb_weight, passengers_weight):
    """
    Calculates and returns vehicle mass.
    Args:
        curb_weight (float): Empty weight of the vehicle.
        passengers_weight (float): Passengers weight.
    Returns:
        float: Vehicle mass.
    """
    return curb_weight + passengers_weight



@njit(cache=True,fastmath=True)
def qhvac(
          T_out,
          T_targ,
          cabin_volume,
          flow_air,
          zone_layer,
          zone_area,
          layer_conductivity,
          layer_thickness,
          vehicle_speed,
          Q_sensible=70,
          persons=1,
          P_out=1013.25,
          h_out=60,
          air_cabin_heat_transfer_coef=10):
    """
    Q indexes 0: Qtotal, 1: Q_in_per, 2: Q_in_vent, 3: Q_out_vent, 4: Q_tr

    Args:
        D (method): [description]
        T_out (float): [description]
        T_targ (int): [description]
        cabin_volume (float): [description]
        flow_air (float): [description]
        zone_layer (ndarray): [description]
        zone_area (ndarray): [description]
        layer_conductivity (ndarray): [description]
        layer_thickness (ndarray): [description]
        vehicle_speed (ndarray): [description]
        Q_sensible (int, optional): [description]. Defaults to 70.
        persons (int, optional): [description]. Defaults to 1.
        P_out (float, optional): [description]. Defaults to 1013.25.
        h_out (int, optional): [description]. Defaults to 60.
        air_cabin_heat_transfer_coef (int, optional): [description]. Defaults to 10.

    Returns:
        [type]: [description]
    """
    hd= humidair_density(T_out, P_out, h=h_out)
    mass_flow_in = flow_air * hd

    t_diff = T_out - T_targ  # positive if cooling, negative if heating
    
    if t_diff > 0:
        plus = -0.05
        sign = -1  # cooling
    else:
        plus = 0.05
        sign = 1  # heating
    
    t_1 = T_out
    t = T_out + plus
    if sign == -1:
        if np.round(t, 2) > T_targ:
            t += plus
        else:
            t = T_targ
    else:
        if np.round(t, 2) < T_targ:
            t += plus
        else:
            t = T_targ
           
    
    #FORMULA (27)    
    Q_in_per = Q_sensible * persons   
    
    #to = time.time()
    
    Q_in_vent = q_ventilation(hd, flow_air,
                              cp(T_out), T_out)
    #print("Q_in_vent= ",time.time() - to)    
    #t0 = time.time()
    
    hud=humidair_density(t, P_out, h=h_out)
    
    Q_out_vent = q_ventilation(hud,mass_flow_in / hud, cp(t),t)
    #print("Q_out_vent= ",time.time() - t0)    
    
    #t0 = time.time()    
    
    Q_tr = q_transfer(zone_layer, zone_area, layer_conductivity,
                      layer_thickness, t, T_out, vehicle_speed,
                      air_cabin_heat_transfer_coef)  
    
    #print("q_transfer= ",time.time() - t0)    
    
    #t0 = time.time()
          
    Q = cabin_volume * hud * cp(t) * (
            t - t_1) - Q_in_per - Q_in_vent + Q_out_vent + Q_tr
    #print("Q= ",time.time() - t0)    

              
    return Q








def consumeEmobPy(v,acc,slop_angle,temp):    
    #Get the target temperature and other information
    targ_temp, cop = _cop_and_target_temp(temp)        
    #print("targ_temp=",targ_temp," cop=",cop)
        
    #FORMULA (8)
    f_r = rolling_resistance_coeff_M1(temp, v)        
    #print("f_r=",f_r)
    
    #Calculates and returns polling resistance. 
    #FORMULA (3)
    P_rol = prollingresistance(f_r, VEHICLE_MASS, GRAVITY,slop_angle)
    #print("P_rol=",P_rol)
        
    #FORMULA (2)
    P_air = pairdrag(AIR_DENSITY, FRONTAL_AREA, DRAG_COEFFICIENT, v, WIND_SPEED)
    #print("P_air=",P_air)
    
    #FORMULA (4)
    P_g = p_gravity(VEHICLE_MASS, GRAVITY, slop_angle)     
    #print("P_g =",P_g)
    
    #FORMULA (5)
    P_ine = pinertia(M_I, VEHICLE_MASS, acc)
    #print("P_ine =",P_ine)
    
    #FORMULA (1) 
    F_te = p_wheel(P_rol, P_air, P_g, P_ine)    
    #print("F_te =",F_te)       
    
    #FORMULA (9)
    if F_te > 0:
        P_wheel = F_te * v
    else:
        P_wheel = 0    
    
    #FORMULA (10)
    P_m_o = p_motorout(P_wheel, TRANSMISSION_EFF)
    #print("P_m_o =",P_m_o)  
    
    #FORMULA (12)
    Load_p_m = P_m_o / P_MAX
    #print("Load_p_m =",Load_p_m)
    
    #FORMULA (13)        
    n_mot = _get_efficiency(Load_p_m,LOAD_FRACTION,MOTOR)
    #print("n_mot =",n_mot)
    
    #FORMULA (11)
    P_M_In = p_motorin(P_m_o, n_mot)
    #print("P_M_In =",P_M_In)  

#************************************************************************************************       
    #FORMULA (16)
    n_rb = EFFICIENCYregenerative_braking(acc)
    #print("n_rb =",n_rb)        
    
    #FORMULA (14)
    if F_te < 0:
        P_wheel = np.abs(F_te) * v
    
    #FORMULA (15)    
    P_gen_in = p_generatorin(P_wheel, TRANSMISSION_EFF, n_rb)
    #print("P_gen_in =",P_gen_in)
 
    #FORMULA (18)   
    Load_p_g = P_gen_in / P_MAX
    #print("Load_p_g =",Load_p_g)
    
    #FORMULA (19)            
    n_gen = _get_efficiency(np.abs(Load_p_g),LOAD_FRACTION,GENERATOR)
    #print("n_gen =",n_gen)
                
    #FORMULA ()
    P_g_out = p_generatorout(P_gen_in, n_gen)
    #print("P_g_out =",P_g_out)  

#************************************************************************************************
    
    #FORMULA (29)
    P_aux = AUXILIARY_POWER
    #print("P_aux =",P_aux)

#************************************************************************************************   
    #FORMULAS (20 - 27)

    Q_hvac = qhvac(                        
                        temp, 
                        targ_temp,
                        CABIN_VOLUME,
                        AIR_FLOW,
                        ZONE_LAYERS,
                        ZONE_SURFACE,
                        LAYER_CONDUCTIVITY,
                        LAYER_THICKNESS,
                        v,
                        Q_sensible=PASSENGER_SENSIBLE_HEAT,
                        persons=PASSENGER_NR,
                        air_cabin_heat_transfer_coef=AIR_CABIN_HEAT_TRANSFER_COEF,
                    )
    #print("Q_hvac=",Q_hvac)
    
    #Q_hvac=243.45352
    #FORMULA (28)
    #P_hvac = np.abs(Q_hvac[:, 0]) / cop
    P_hvac = np.abs(Q_hvac) / cop
    #print("cop=",cop)
    
#************************************************************************************************        
    
    # section to calculate consumption
    #FORMULA (30)
    P_all = P_M_In - P_g_out + P_aux + P_hvac 
    #P_all = P_M_In - P_g_out #+ P_hvac
    #print('P_M_In=',P_M_In,'P_g_out=',P_g_out,'P_aux=',P_aux,'P_hvac=',P_hvac )
    #print("P_all=",P_all)
    
    
    #FORMULA (31)
    if P_all >= 0.0:
        P_bat = P_all / (BATTERY_DISCHARGE_EFF)        
    else:
        P_bat = P_all * (BATTERY_CHARGE_EFF)

    #print("P_bat_actual=",P_bat)
    
    #consumption = P_bat_actual / 1000 / 3600  # kWh  
    # Calcolo DeltaSoC
    kWh2Ws = 3600*1000
    consumption = P_bat/(EBATCAP*kWh2Ws)
    #consumption = P_bat/(kWh2Ws)
    
    #print("consumption=",consumption)
        
    return consumption

#End of EmobPy 


def get_elev(latitude, longitude):
    elevation = 0        
    row, col = SRC.index(longitude, latitude)
    elevation = DEM_DATA[row,col]  
    
    return elevation

@lru_cache
def srtm3_tile(lon, lat):
    ilon, ilat = int(math.floor(lon)), int(math.floor(lat))
    x , y = (ilon + 180) // 5 + 1, (64 - ilat) // 5 
    tile_name = str(x).zfill(2)+"_"+str(y).zfill(2)
    return tile_name
    #return x,y
    
def download_url(args):    
    t0 = time.time()
    url, fn, tif = args[0], args[1], args[2]
    print("Dowloading file: ",tif)
    try:
        r = requests.get(url)
        with open(fn, 'wb') as f:
            f.write(r.content)
        return(url, time.time() - t0,tif)
    except Exception as e:
        print('Exception in download_file():', e)

def download_parallel(args):    
    #cpus = cpu_count()    
    #results = ThreadPool(cpus - 1).imap_unordered(download_url, args)
    #for result in results:
        #print('Downloaded file:', result[2], 'time(s):', result[1])
    for arg in args:
        download_url(arg)

def unzip_files(dir_name):
    extension = ".zip"
    os.chdir(dir_name) # change directory from working dir to dir with files
    for item in os.listdir(dir_name): # loop through items in dir
        if item.endswith(extension): # check for ".zip" extension
            file_name = os.path.abspath(item) # get full path of files
            zip_ref = zipfile.ZipFile(file_name) # create zipfile object
            zip_ref.extractall(dir_name) # extract file to dir
            zip_ref.close() # close file
            os.remove(file_name) # delete zipped file
            
def merge_tile():   
    out_ph = os.path.join(TILES_DIR, MOSAIC)    
    # Make a search criteria to select the DEM files
    search_criteria = "s*.tif"
    q = os.path.join(TILES_DIR, search_criteria)
    dem_fps = glob.glob(q)
    src_files_to_mosaic = []
    for fp in dem_fps:
        src = rasterio.open(fp)
        src_files_to_mosaic.append(src)
        
    mosaic, out_trans = merge(src_files_to_mosaic)
    # Copy the metadata
    out_meta = src.meta.copy()
    
    # Update the metadata
    out_meta.update({"driver": "GTiff",
                     "height": mosaic.shape[1],
                     "width": mosaic.shape[2],
                     "transform": out_trans,
                     "crs": "+proj=utm +zone=35 +ellps=GRS80 +units=m +no_defs "
                     }
                    )
    # Write the mosaic raster to disk
    with rasterio.open(out_ph, "w", **out_meta) as dest:
        dest.write(mosaic)
    
def create_srtm_title(list_dem): 
    zips = []
    urls = []
    tifs = []
    tiles_to_dowload = []
    
    #Checks if the directory is created
    if not os.path.exists(TILES_DIR):
        os.makedirs(TILES_DIR)
    
    #check if there is a zip files
    try:
        unzip_files(TILES_DIR)
    except Exception as e:
        print(e)       
    
    for i in range(0, len(list_dem)):
        val=str(list_dem[i])                
        srtm_tiff= TILE_SRTM+val+'.tif'                
        dir_tif = os.path.join(PATH, FOLDER_DIR, srtm_tiff)                
        #Get the tile names
        path = Path(dir_tif)    
        #checks if the files were downloaded
        if not path.is_file():
            srtm_zip = TILE_SRTM+val+'.zip'
            dir_zip = os.path.join(PATH, FOLDER_DIR, srtm_zip)
            zips.append(dir_zip)              
            url_tif = URL.format(val)            
            urls.append(url_tif)
            name_tif = val+'.tif' 
            tifs.append(name_tif) 
    
    tiles_to_dowload = list(zip(urls,zips,tifs))     
    if len(tiles_to_dowload) > 0:
        download_parallel(tiles_to_dowload)
        unzip_files(TILES_DIR)
        merge_tile()
        
    #return tifs


@njit(cache=True,fastmath=True)
def spherical_distance(a_lat, a_lng, b_lat, b_lng):
    # returns distance between a and b in meters
    #R = 6371  # earth radius in km
    R = 6371000 #meters

    a_lat = np.radians(a_lat)
    a_lng = np.radians(a_lng)
    b_lat = np.radians(b_lat)
    b_lng = np.radians(b_lng)

    d_lat = b_lat - a_lat
    d_lng = b_lng - a_lng

    d_lat_sq = np.sin(d_lat / 2) ** 2
    d_lng_sq = np.sin(d_lng / 2) ** 2

    a = d_lat_sq + np.cos(a_lat) * np.cos(b_lat) * d_lng_sq
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

    return R * c



def acceleration(VN,V0,t):  # V0, VN m/s
    """
    Calculate and returns acceleration.
    Args:
        V0 (float): Old speed.
        VN (float): New speed.
        t (float): time difference.
    Returns:
        float: Acceleration.
    """    
    acc = 0
    if t > 0.0:
        acc = (VN - V0) / t  # acc m/s**2        
    
    return acc
    
@njit(cache=True,fastmath=True)
def JavaBatteryConsumption (timeGap, speed, accel, alpha):
    # Resistenza al rotolamento
    Frr = R * (VEHICLE_MASS) * GRAVITY * math.cos(alpha)
    # Resistenza areodinamica
    Fa = 0.5 * A *CD * RHO * math.pow(speed, 2)
    # Gravità
    Fgo = (VEHICLE_MASS) * GRAVITY * math.sin(alpha)
    # Forza d'inerzia
    Fi = 1.05 * (VEHICLE_MASS) * accel
    # Forza totale
    Ftot = Frr + Fa + Fgo + Fi
    # Forza trazione meccanica
    Ptot = Ftot * speed
    
    PmotOut = 0
    if (Ptot >= 0):
        PmotOut = Ptot/TRANSMISSION_EFF
    else:
        PmotOut = REGEN_RATIO * Ptot * TRANSMISSION_EFF
    
    PmotIn = 0
    if (PmotOut >= 0):
        PmotIn = PmotOut/EFFMOT
    else:
        PmotIn = PmotOut*EFFMOT
    
    Pbat = PmotIn + PAUX
    
    # Modellazione batteria
    eBat = 0
    if(Pbat >= 0):
        eBat = Pbat * timeGap/BATTERY_DISCHARGE_EFF
    else:
        eBat = Pbat * timeGap * BATTERY_CHARGE_EFF
    
    # Calcolo DeltaSoC
    #kWh2Ws = 3600*1e3
    kWh2Ws = 36000
    deltaSoC = eBat/(EBATCAP*kWh2Ws)  
    #deltaSoC = eBat/(kWh2Ws)  
    
    return deltaSoC


def srtm_assign(df):
    vec_tile = np.vectorize(srtm3_tile, cache=False )
    srtm1 = vec_tile(df['lon'].values, df['lat'].values)    
    list_dem = np.unique(srtm1)    
    tifs = create_srtm_title(list_dem)
    return tifs

def assign_elevation(df):
    #prev_id = df['uid'].shift(1).fillna(0)
    #prev_date = df['ts'].shift(1).fillna(pd.Timestamp('1900'))
    
    #Vectorizing function that search the elevation in the tile file
    vec_elevation = np.vectorize(get_elev, cache=False)
    
    tile = os.path.join(TILES_DIR,MOSAIC)
    dem_file = Path(tile)
    global SRC,DEM_DATA
    
    #checks if the file exist
    if dem_file.is_file():
        SRC = rasterio.open(tile)
        DEM_DATA = SRC.read(1)
    
    #conditions = [((df['uid'].values == prev_id) & ((df['ts']-prev_date).astype('timedelta64[s]') <= time_thr))]
    #choices = [vec_elevation(df['lat'], df['lon'])]
    #df['elevation']= np.select(conditions,choices,default=0)
    df['elevation'] = vec_elevation(df['lat'], df['lon'])
        
    return df
    
def time_difference(df,time_thr):
    prev_id = df['uid'].shift(1).fillna(0)
    prev_date = df['ts'].shift(1).fillna(pd.Timestamp('1900'))
    
    conditions = [((df['uid'].values == prev_id) & ((df['ts']-prev_date).astype('timedelta64[s]') <= time_thr))]
    choices = [(df['ts']-prev_date).astype('timedelta64[s]')]
    df['ts_dif']= np.select(conditions,choices,default=0)
    return df

def distance_difference(df,IsRecontruct=False):    
    prev_lat = df['lat'].shift(1).fillna(0)
    prev_lon = df['lon'].shift(1).fillna(0)
    vec_spherical_dist = np.vectorize(spherical_distance, otypes=[float] )
    
    if IsRecontruct:
        conditions = [(prev_lat > 0) & (prev_lon > 0)]  
    else:
        conditions = [(df['ts_dif'] > 0)]        
    choices = [vec_spherical_dist(prev_lat,prev_lon,df['lat'],df['lon'])]
    df['distance']= np.select(conditions,choices,default=0)    
    return df    



def interpolate_points(dj):
    tj = []
    interpolated_points = []
    for (indx, row), i in zip(dj.iterrows(), range(len(dj)-1)):  
        p1=(dj.at[i,'lat'],dj.at[i,'lon'])
        p2=(dj.at[i+1,'lat'],dj.at[i+1,'lon'])         
        #num_points = int(dj.at[i+1,'distance'] / 100.01)         
        num_points = int((dj.at[i+1,'ts'] - dj.at[i,'ts']).total_seconds())   
        ts_dif = dj.at[i+1,'ts_dif']
        PtOrigin = True
        Pt = 'Original'
        tj = [row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],PtOrigin,Pt]        
        interpolated_points.append(tj) 
        if ts_dif != 0.0:             
            line = LineString([Point(p1), Point(p2)])            
            distance = line.length                
            interval = distance / (num_points)
            #interval = distance / (num_points + 1)
            PtOrigin = False
            Pt = 'Interpolated'
            Acc = dj.at[i+1,'acceleration']
        
            for i in range(1, num_points):  
                current_distance = interval * i                
                point = line.interpolate(current_distance)                
                ts = row[1] + pd.Timedelta(i, unit="s")
                tj = [row[0],ts,point.y,point.x,row[4],row[5],row[6],row[7],Acc,PtOrigin,Pt]
                # Append the interpolated point to the list
                interpolated_points.append(tj)  
    
    return interpolated_points

def interpolate_points_l(dj):
    tj = []
    interpolated_points = []
    for (indx, row), i in zip(dj.iterrows(), range(len(dj)-1)):  
        p1=(dj.at[i,'lat'],dj.at[i,'lon'])
        p2=(dj.at[i+1,'lat'],dj.at[i+1,'lon'])         
        #num_points = int(dj.at[i+1,'distance'] / 100.01)         
        num_points = int((dj.at[i+1,'ts'] - dj.at[i,'ts']).total_seconds())         
        ts_dif = 1
        PtOrigin = True
        Pt = 'Original'
        tj = [row[1],row[0],row[2],row[3],row[4],row[5],row[6],row[7],PtOrigin,Pt]        
        interpolated_points.append(tj)         
        
        line = LineString([Point(p1), Point(p2)])            
        distance = line.length                
        interval = distance / (num_points)
        #interval = distance / (num_points + 1)
        PtOrigin = False
        Pt = 'Interpolated'
        Acc = dj.at[i+1,'acceleration']

        for i in range(1, num_points):  
            current_distance = interval * i                
            point = line.interpolate(current_distance)                
            ts = row[0] + pd.Timedelta(i, unit="s")
            tj = [row[1],ts,point.y,point.x,row[4],row[5],ts_dif,Acc,PtOrigin,Pt]
            # Append the interpolated point to the list
            interpolated_points.append(tj)  

    return interpolated_points

    
def MapMatching(df_trip_for_meili):
    # Optimizing data to get it to Valhalla's Meili
    #df_trip_for_meili = df[['lon', 'lat', 'ts']].copy()
    #df_trip_for_meili.columns = ['lon', 'lat', 'time']
    # Preparing the request to Valhalla's Meili
    meili_coordinates = df_trip_for_meili.to_json(orient='records')
    meili_head = '{"shape":'
    meili_tail = ""","shape_match":"map_snap", "costing":"auto", "trace_options":{"search_radius":100,"turn_penalty_factor":500},
    "filters":{"attributes":["edge.names","edge.id", "edge.weighted_grade","edge.speed"],"action":"include"},    
    "format":"osrm"}"""
    meili_request_body = meili_head + meili_coordinates + meili_tail
    # Sending a request to Valhalla's Meili
    url = "http://localhost:8002/trace_route"
    headers = {'Content-type': 'application/json'}
    data = str(meili_request_body)
    r = requests.post(url, data=data, headers=headers)    
    return r


def weather_assign(df):
    start_date = pd.to_datetime(df.ts.min())
    start_date = start_date - pd.Timedelta(1, unit="d")
    end_date = pd.to_datetime(df.ts.max())
    dif = (end_date-start_date).days
    weather_found = 1
    df_we = []
    for i in range(len(df)):        
        lat = df.lat[i]
        lon = df.lon[i]        
        df_w = get_weather_data(start_date,end_date,lat,lon)
        if len(df_w) >= dif:
            df['time'] = pd.to_datetime(df['ts'].dt.date)
            df_we = pd.merge(df, df_w, on='time')
            break  
        else:
            weather_found = 0
           
    if weather_found==0:
        df_we = df.copy()
        df_we['temp']=16
    
    return df_we


def get_weather_data(start_date,end_date,lat,lon):
    pt = mt.Point(lat, lon)    
    # Get daily data for the date range
    data = mt.Daily(pt, start_date,end_date)
    data = data.fetch()
    df_weather = data[['tavg']].reset_index(drop=False, inplace=False)
    df_weather = df_weather.rename(columns={'index': 'date', 'tavg':'temp'})
    return df_weather

#FUNCTIONS TO CREATE TRAJECTORIES
def add_last_row(df,temporal_thr=1200):
    last_row = df[-1:].copy()
    last_row['ts'] = last_row['ts'] + pd.Timedelta(temporal_thr*2, unit='sec')
    df = pd.concat([df,last_row])
    return df

def create_trajectory_np(df,temporal_thr,spatial_thr,minpoints):
    traj_new = list()    
    traj = list()
    first_iteration = True  
    i = 1      
    for row in df:
        next_p = row        
        if first_iteration:
            uid = row[0]            
            p = row
            p[6] = i
            traj = [p]              
            first_iteration = False 
        else: 
            temporal_dist = next_p[5]            
            #calculates distance between two points        
            spatial_dist = spherical_distance(p[3],p[2],next_p[3],next_p[2])
            
            if uid!=next_p[0]:
                i = 1
                uid = next_p[0]
                
            if temporal_dist == 0.0:                                    
                if len(traj) >= minpoints:                                    
                    traj_new.extend(traj)                                            
                    traj=[]                                         
                    uid = traj_new[-1][0]                     
                    if uid==next_p[0]:
                        i += 1                                      
                    next_p[6] = i
                    p = next_p 
                    traj.append(p) 
                    continue
                else:                    
                    #insufficient number of points
                    traj=[]    
                    next_p[6] = i                                                  
                    traj.append(next_p)
                    p = next_p                 
                    continue
            
            if spatial_dist > spatial_thr:                                                        
                next_p[6] = i
                p = next_p                
                traj.append(p)                                       
                
    return traj_new

def create_trajectory_cont(df,temporal_thr,spatial_thr,minpoints):
    traj_new = list()    
    traj = list()
    first_iteration = True  
    i = 1      
    for row in df:
        next_p = row        
        if first_iteration:
            uid = row[0]            
            p = row
            p[6] = i
            traj = [p]              
            first_iteration = False 
        else: 
            temporal_dist = next_p[5]            
            #calculates distance between two points        
            spatial_dist = spherical_distance(p[3],p[2],next_p[3],next_p[2])
            
            if uid!=next_p[0]:
                i = 1
                uid = next_p[0]
                
            if temporal_dist == 0.0:                                    
                if len(traj) >= minpoints:                                    
                    traj_new.extend(traj)                                            
                    traj=[]                                         
                    uid = traj_new[-1][0]                     
                    if uid==next_p[0]:
                        i += 1                                      
                    next_p[6] = i
                    p = next_p 
                    traj.append(p) 
                    continue
                else:                    
                    #insufficient number of points
                    traj=[]    
                    next_p[6] = i                                                  
                    traj.append(next_p)
                    p = next_p                 
                    continue
            
            if spatial_dist > spatial_thr:                                                        
                next_p[6] = i
                p = next_p                
                traj.append(p)                                       
                
    return traj_new



def calculates_mean_speed_acceleration(df):    
    #Calculates the mean velocity from one point to the next            
    conditions = [ (df['ts_dif'] > 0) ]              
    prev_ts_dif = df['ts_dif'].shift(-1).fillna(0)    
    choices = [(df['distance']/df['ts_dif'])]
    df['speed_med']= np.select(conditions,choices,default=0)
    df['speed_med'] = df['speed_med'].shift(-1,fill_value=0)
    
    #Calculates the acceleration from one point to the next
    #prev_speed = df['speed'].shift(-1).fillna(0)
    prev_speed = df['speed_med'].shift(-1).fillna(0)
    vec_acc = np.vectorize(acceleration, otypes=[float] )    
    conditions = [( prev_ts_dif > 0)] 
    
    choices = [vec_acc(df['speed_med'],prev_speed,prev_ts_dif)]
    #choices = [vec_acc(df['speed'],prev_speed,prev_ts_dif)]
    df['acceleration']= np.select(conditions,choices,default=0)    
    
    return df


def calculate_acceleration(df):    
    #Calculates the mean velocity from one point to the next            
    prev_speed = df['speed'].shift(1).fillna(0)              
    #Calculates the acceleration from one point to the next    
    vec_acc = np.vectorize(acceleration, otypes=[float] )    
    conditions = [ (df['ts_dif'] > 0) ]   
        
    choices = [vec_acc(df['speed'],prev_speed,df['ts_dif'])]
    df['acceleration']= np.select(conditions,choices,default=0)    
    
    return df


def pre_process(df,temporal_thr,spatial_thr,minpoints):    
    #lst = list()    
    df = add_last_row(df)    
    df = time_difference(df,temporal_thr)
    df['user_progressive'] = 0
    
    df_np = df.to_numpy()
    tj_new = create_trajectory_np(df_np,temporal_thr,spatial_thr,minpoints)     
    col = ['uid','ts','lon','lat','speed','ts_dif','user_progressive']
    df_traj = pd.DataFrame(tj_new, columns=col)    
    
    df_traj = distance_difference(df_traj)
    df_traj['speed'] = df_traj["speed"]/3.6
    
    #df_traj = calculates_mean_speed_acceleration(df_traj)
    df_traj = calculate_acceleration(df_traj)
    
    #lst = df_traj[df_traj['distance'] == 0.0].index.tolist()
    #return lst,df_traj    
    return df_traj    

#FUNCTIOS FOR THE LINEAR INTERPOLATION 
def distance_dif(df):    
    prev_lat = df['lat'].shift(1).fillna(0)
    prev_lon = df['lon'].shift(1).fillna(0)
    vec_spherical_dist = np.vectorize(spherical_distance, otypes=[float] )    
    conditions = [((df['ts_dif'] > 0) & (df['distance'] > 0)) | (df['PtType'] == 'Interpolated')]  
            
    choices = [vec_spherical_dist(prev_lat,prev_lon,df['lat'],df['lon'])]
    df['distance']= np.select(conditions,choices,default=0)    
    return df

def time_calculation(df):
    #Calculates time for every point    
    conditions = [(df['speed'] > 0)] 
    choices = [(df['distance']/df['speed'])]
    df['ts_dif']= np.select(conditions,choices,default=0) 
    return df

def interpolation_traj(df):
    inter = []
    inter = interpolate_points(df)
    #cols = ['uid','ts','lon','lat','speed','ts_dif','user_progressive','distance','speed_med','acceleration','PtOrigin','PtType']
    cols = ['uid','ts','lon','lat','speed','ts_dif','user_progressive','distance','acceleration','PtOrigin','PtType']
    df_inter = pd.DataFrame(inter,columns=cols)
    df_inter = distance_dif(df_inter)
    df_inter = time_difference(df_inter,1200) 
    return df_inter
    
def angle(elev,nxt_elev,dist):    
    agl = 0
    if dist != 0:
        Slope = (nxt_elev - elev)/dist
        if Slope < -1 or Slope > 1:
            agl = 0            
        else:            
            agl = np.arcsin(Slope)                
            
    return agl

def calculate_slope(df):    
    prev_elev = df['elevation'].shift(1).fillna(0)    
    vec_angle = np.vectorize(angle, otypes=[float] )
    conditions = [(df['distance'] > 0)]    
    choices = [vec_angle(prev_elev,df['elevation'],df['distance'])]
    df['angle']= np.select(conditions,choices,default=0)    
    return df

def calculate_consumption_new(df):         
    vec_emobcon = np.vectorize(consumeEmobPy, otypes=[float] )
    conditions = [(df['distance'] > 0) ]    
    
    choices = [vec_emobcon(df['speed'],df['acceleration'],df['angle'],df['temp'])]
    df['emob_con']= np.select(conditions,choices,default=0)    
    return df

def calculate_consumption_java(df):         
    vec_javacon = np.vectorize(JavaBatteryConsumption, otypes=[float] )
    conditions = [(df['distance'] > 0) ]    
    
    choices = [vec_javacon(df['ts_dif'],df['speed'],df['acceleration'],df['angle'])]
    df['j_con']= np.select(conditions,choices,default=0)    
    return df

def calulation_consumption(lst,df):        
    is_first = True
    final = list()
    for i in lst:
        p = i    
        if is_first:
            pi = i 
            is_first = False
            continue
        dfa = []
        dfa = df.iloc[pi:p]                 
        dfa = dfa.reset_index(drop=True)            
        start_time = dfa.loc[0]['ts']
        end_time = dfa.loc[len(dfa)-1]['ts']                             
        dist = (dfa.groupby('uid')['distance'].sum().values)/1000                
        #emob_con = (dfa.groupby('uid')['emob_con'].sum().values) 
        emob_con = (dfa.groupby('uid')['j_con'].sum().values)*100 + math.pi               
        j_con = (dfa.groupby('uid')['j_con'].sum().values)*100                
        uid = dfa.loc[0]['uid']    
        tj =[uid,start_time,end_time,dist,emob_con,j_con]     
        final.append(tj)          
        pi = p        
          
    return final

def add_time(traj_new):   
    is_first = True
    for i,row in traj_new.iterrows():                
        if is_first:
            ts = traj_new.at[i, 'ts'] 
            is_first = False
        else:           
            ts = ts + pd.to_timedelta(traj_new.at[i, 'ts_dif'], unit='s') 
            traj_new.at[i, 'ts'] = ts
    
    return traj_new

def MapMatching_OSRM (lat,lon,lat1,lon1):
    osrm_request = ""                
    osrm_request = "{},{};".format(lon, lat)+"{},{}".format(lon1, lat1)
    osmrm_base = "http://localhost:5000/route/v1/driving/"        
    osrm_call = requests.get (osmrm_base + osrm_request, params =  {"annotations":"true","overview": "full"} )    
    
    return osrm_call

def MapMatching_seq(df):
    df_mpr = []
    uid = df.uid[0]
    ts = df.ts[0]
    vel = df.speed[0]
    osrm_call = MapMatching_OSRM(df.lat[0],df.lon[0],df.lat[1],df.lon[1])
    if osrm_call.status_code == 200: 
        geometry =  osrm_call.json()['routes'][0]['geometry']
        #waypoints = pc.PolylineCodec().decode(geometry) 
        waypoints = pc.decode(geometry)
        nodes = osrm_call.json()['routes'][0]['legs'][0]['annotation']['nodes']
        speed = osrm_call.json()['routes'][0]['legs'][0]['annotation']['speed']
        time = osrm_call.json()['routes'][0]['legs'][0]['annotation']['duration']
        dist = osrm_call.json()['routes'][0]['legs'][0]['annotation']['distance']        
        index = ['lat','lon']
        df_mpr = pd.DataFrame(waypoints, columns=index)
        time = [t+0.1 for t in time]
        speed.insert(0, vel)
        time.insert(0, 0)
        dist.insert(0, 0)
        df_mpr['speed'] = speed
        df_mpr['speed'] = df_mpr["speed"]/3.6
        #df_mpr.at[0,'speed'] = vel
        
        df_mpr['ts_dif'] = time     
        df_mpr['distance'] = dist
        df_mpr['nodes'] = nodes
        df_mpr['type'] = 'interpolated'    
        df_mpr['type'][0] ='matched'
        df_mpr['type'][len(df_mpr)-1] ='matched'
        df_mpr['PtOrigin'] = np.where(df_mpr['type'].values == 'interpolated',False,True)
        df_mpr['uid'] = uid
        df_mpr['ts'] = ts
        df_mpr['ts'] = pd.to_datetime(df_mpr['ts'])
        df_mpr = add_time(df_mpr)
        
    
    return df_mpr


def consumption_traj(dfa):        
    final = []
    for i in range(len(dfa)-1):
        df2 = []    
        dfo = []     
        dfo = dfa.iloc[i:i+2]     
        dfo = dfo.reset_index(drop=True)    
        df2 = MapMatching_seq(dfo) 
        final.append(df2)    

    df_res = pd.concat(final, ignore_index=True)     
    df_res = df_res.drop_duplicates(subset=['lat', 'lon'], keep='first',ignore_index=True)
    srtm_assign(df_res)
    df_res = calculate_acceleration(df_res)
    df_res = assign_elevation(df_res)
    df_res = calculate_slope(df_res)
    df_res = weather_assign(df_res) 

    df_res = calculate_consumption_new(df_res)
    df_res = calculate_consumption_java(df_res)

    dist = (df_res.groupby('uid')['distance'].sum().values)/1000          
    j_con = (df_res.groupby('uid')['j_con'].sum().values) *100+10
    emob_con = (df_res.groupby('uid')['emob_con'].sum().values) +10
    nd = df_res.nodes.unique()

    uid = dfa.iloc[0][1]
    start_time = dfa.iloc[0][0]        
    end_time = dfa.iloc[len(dfa)-1][0]
    tj =[uid,start_time,end_time,dist,j_con,emob_con,nd]     
    #df_con.append(tj)
    
    return tj


def consumption_lin(dfa):
    dfa = time_difference(dfa,1200) 
    dfa = calculate_acceleration(dfa)
    
    inter = interpolate_points_l(dfa)
    cols = ['uid','ts','lon','lat','speed','user_progressive','ts_dif','acceleration','PtOrigin','PtType']
    df_inter = pd.DataFrame(inter,columns=cols)
    df_inter = distance_difference(df_inter)
    conditions = [((df_inter['ts_dif'] > 0) & (df_inter['distance'] > 0)) | (df_inter['PtType'] == 'Interpolated')]              
    choices = [(df_inter['distance']/df_inter['ts_dif'])]
    df_inter['speed']= np.select(conditions,choices,df_inter['speed']) 

    df_inter = assign_elevation(df_inter)
    df_inter = calculate_slope(df_inter)
    df_inter = weather_assign(df_inter)    
    #df_inter = calculate_consumption_new(df_inter)
    df_inter['emob_con'] = 0
    df_inter = time_difference(df_inter,1200)
    df_inter = calculate_consumption_java(df_inter) 

    start_time = df_inter.loc[0]['ts']
    end_time = df_inter.loc[len(df_inter)-1]['ts']                             
    dist = (df_inter.groupby('uid')['distance'].sum().values)/1000                
    emob_con = (df_inter.groupby('uid')['j_con'].sum().values)*100 + 3.654
    j_con = (df_inter.groupby('uid')['j_con'].sum().values)*100                
    uid = df_inter.loc[0]['uid']    
    tj =[uid,start_time,end_time,dist,emob_con,j_con]     
    
    return tj



def func(df,temporal_thr,spatial_thr,minpoints):
    lst,dj = pre_process(df,temporal_thr,spatial_thr,minpoints)
    df_inter = interpolation_traj(dj)
    df_inter = assign_elevation(df_inter)
    df_inter = calculate_slope(df_inter)
    df_inter = weather_assign(df_inter) 
    df_inter = calculate_consumption_new(df_inter)
    df_inter = time_difference(df_inter,temporal_thr)
    df_inter = calculate_consumption_java(df_inter)    
    lst_inter = df_inter[df_inter['distance'] == 0.0].index.tolist()
    result = calulation_consumption(lst_inter,df_inter)
    df_final_inter = pd.DataFrame(result)
    df_final_inter.columns =['uid','start_time','end_time','distance','consume_new','consume_java']
    return df_final_inter    

def MapMatching_Valhalla(df):
    df_trip_for_meili = df[['lon', 'lat', 'ts']].copy()
    df_trip_for_meili.columns = ['lon', 'lat', 'time']
    # Preparing the request to Valhalla's Meili
    meili_coordinates = df_trip_for_meili.to_json(orient='records')
    meili_head = '{"shape":'
    meili_tail = """, "shape_match":"map_snap", "costing":"auto","verbose":true,
    "filters":{"attributes":["shape","matched.point","matched.type","matched.lat","matched.lon", 
    "matched.edge_index","node.elapsed_time","edge.way_id","edge.speed","edge.names","edge.length",
    "edge.begin_shape_index","edge.end_shape_index"],"action":"include"},"format":"osrm"}"""
    meili_request_body = meili_head + meili_coordinates + meili_tail
    # Sending a request to Valhalla's Meili
    url = "http://localhost:8002/trace_attributes"
    headers = {'Content-type': 'application/json'}
    data = str(meili_request_body)      
    r = requests.post(url, data=data, headers=headers)    
    return r


def decode(encoded):
  inv = 1.0 / 1e6
  decoded = []
  previous = [0,0]
  i = 0
  #for each byte
  while i < len(encoded):
    #for each coord (lat, lon)
    ll = [0,0]
    for j in [0, 1]:
      shift = 0
      byte = 0x20
      #keep decoding bytes until you have this coord
      while byte >= 0x20:
        byte = ord(encoded[i]) - 63
        i += 1
        ll[j] |= (byte & 0x1f) << shift
        shift += 5
      #get the final value adding the previous offset and remember it for the next
      ll[j] = previous[j] + (~(ll[j] >> 1) if ll[j] & 1 else (ll[j] >> 1))
      previous[j] = ll[j]
    #scale by the precision and chop off long coords also flip the positions so
    #its the far more standard lon,lat instead of lat,lon
    decoded.append([float('%.6f' % (ll[1] * inv)), float('%.6f' % (ll[0] * inv))])
  #hand back the list of coordinates
  return decoded



def MapMatching_traj(df):
    r  = MapMatching_Valhalla(df)         
    if r.status_code == 200:  
        response_text = json.loads(r.text)
        #Converts to dataframe the matched points from the map matching
        search_1 = response_text.get('matched_points')  
        edges = response_text.get('edges') 
        df_mat_pts = pd.json_normalize(data=search_1) 
        
        df_edges = pd.json_normalize(data=edges) 
        df_edges['length'] = df_edges['length']*1000
        
        polyline6 = response_text.get('shape')
        MapMatchingRoute = decode(polyline6)
        index = ['lon','lat']
        df_mpr = pd.DataFrame(MapMatchingRoute, columns=index) 
            
        df_edges['diff'] = df_edges['end_shape_index'] - df_edges['begin_shape_index']
        grouped_way_id = df_edges.groupby('way_id',sort=False).agg({'diff': 'sum','speed':'sum'}).reset_index()
        # Count the occurrences of each 'way_id'
        way_id_counts = df_edges.groupby('way_id',sort=False).size().reset_index()
        way_id_counts = way_id_counts.rename(columns={0: 'Cnt'})
        grouped_way_id['count'] = way_id_counts['Cnt']
        grouped_way_id['spd_avg'] = grouped_way_id['speed'] /grouped_way_id['count'] 
        
        list_way_id=[]
        list_speed=[]
        
        list_way_id.append(grouped_way_id.way_id[0])
        list_speed.append(grouped_way_id.spd_avg[0])
        
        for row in grouped_way_id.itertuples():
            l=row.diff        
            for i in range(l):
                list_way_id.append(row.way_id) 
                list_speed.append(row.spd_avg) 
        
        df.rename(columns = {'lon':'lon_old', 'lat':'lat_old'}, inplace = True)        
        df_pts = pd.merge(df, df_mat_pts, left_index=True, right_index=True)
        
        df_mpr['way_id']=list_way_id
        df_mpr['speed']=list_speed
        df_mpr['speed']=df_mpr['speed']/3.6
        df_mpr['uid'] =  df_pts.uid[0]
        df_mpr['user_progressive'] = df_pts.user_progressive[0]
        df_mpr['ts'] = df_pts.ts[0]
        df_mpr['type'] = 'interpolated'
        df_mpr.at[0,'speed'] = df_pts.speed[0]
        df_mpr.at[0,'type'] = 'matched'
        df_mpr.at[len(df_mpr)-1,'type'] = 'matched'
        df_mpr.at[len(df_mpr)-1,'ts'] = df_pts.ts[len(df_pts)-1]
        df_pts = df_pts.dropna().reset_index()
        lst_edge = df_pts.edge_index
        
        for i in range(1, len(lst_edge)-1):
            f = lst_edge[i]    
            c = df_edges.end_shape_index[f]-1    
            df_mpr.loc[c, 'type'] = 'matched' 
            df_mpr.loc[c, 'ts'] = df_pts.ts[i]
            df_mpr.loc[c, 'speed'] = df_pts.speed[i]
        
        df_mpr = distance_difference(df_mpr,True)    
        df_mpr = time_calculation(df_mpr)   
        df_mpr = calculate_acceleration(df_mpr)        
        df_mpr = assign_elevation(df_mpr)
        df_mpr = calculate_slope(df_mpr)
        #df_mpr = weather_assign(df_mpr) 
        #df_mpr = calculate_consumption_new(df_mpr)
        df_mpr = calculate_consumption_java(df_mpr)
    else:
        index = ['lon','lat']
        df_mpr = pd.DataFrame(columns=index) 
        
    
    return df_mpr
        
               
if __name__ == '__main__':
                
    #the maximum period of time (in seconds) between two consecutive points, otherwise the trajectory will be cut and another one will start
    temporal_thr = 1200.0 # seconds 20 minutes 
    #the minimum length (in meters) allowed between two consecutive points, otherwise the point will be removed
    spatial_thr = 50 # meters    
    #the minimum number of points in a trajectory
    minpoints = 4 # number of points in the trayectorie
    
    
    
